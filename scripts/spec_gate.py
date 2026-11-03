"""git commit-msg hook: a source commit on the default branch must cite a building or shipped work item.

    python spec_gate.py <commit-msg-file>     (pre-commit framework passes the message file)

Runs inside the real commit, so it reads git's own staged index and final message: no shell parsing. The work item,
its tests, its configs and DECISIONS.md are all read from the index (spec_check.IndexTree), never the working tree.
Exit 0 lets the commit land; exit 1 rejects it with the reason on stderr. Any git error, tool failure or timeout
rejects (fails closed). A detached HEAD is gated like the default branch. A commit cites exactly one `Spec:` trailer.
Work item: docs/work/spec-gate/ (Work-Item Standard v2, CK-26). A legacy `Spec: docs/specs/<slug>.md` trailer is still
accepted until migration ends.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spec_check  # noqa: E402
import spec_v3  # noqa: E402
import yaml  # noqa: E402

SOURCE = re.compile(r"(\.(py|[cm]?[jt]sx?|ps1|psm1|lua|go|rs|sh|bat|cmd|rb|java|cs|php|sql|vbs|vue|svelte|html|css|"
                    r"c|cc|cpp|h|hpp|kt|kts|swift|scala|ex|exs|ipynb|m|r|pl|tf)|(^|/)Dockerfile)$", re.I)
# Tests (one definition, shared with the checker's CK-20), build output at the repo root only, vendored and generated files.
NOT_SOURCE = re.compile(spec_check.TEST_PATH.pattern + r"|^(dist|build|out|coverage)/|(^|/)node_modules/|\.d\.ts$|"
                        r"\.min\.(js|css)$", re.I)
FRONTMATTER_BLOCK = re.compile(r"^---\r?\n(.*?)\r?\n---", re.S)
ITEM_FILE = re.compile(r"^docs/work/(?!\.\.?/)([\w.-]+)/")
WORK_ITEM = re.compile(r"^docs/work/(?!\.\.?/)[\w.-]+/README\.md$")
REVIEW_RECORD = re.compile(r"^docs/work/(?!\.\.?/)[\w.-]+/reviews/[^/]+\.md$")
RECORDED_STATES = ("spec-locked", "shipped")  # moves into these need a fresh passing review record (FR-8)
REVERTS = re.compile(r"^This reverts commit ([0-9a-f]{7,40})\b", re.M)
IN_PROGRESS = ("MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD")
GIT_TIMEOUT_S = 10
STANDARD = "~/.claude/skills/dark-factory/WORK-ITEM-STANDARD.md"


class GateError(Exception):
    pass


def git(*args: str, ok_codes: tuple[int, ...] = (0,)) -> str:
    spec_check.require_index_file()
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=GIT_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GateError(f"git {args[0]} failed: {e}") from e
    if r.returncode not in ok_codes:
        raise GateError(f"git {' '.join(args[:2])} exited {r.returncode}: {r.stderr.strip()[:200]}")
    return r.stdout


def default_branch() -> str | None:
    """origin/HEAD, else a local main or master; None when it cannot be resolved (the caller then gates: never guess)."""
    head = git("symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD", ok_codes=(0, 1)).strip()
    if head:
        return head.split("/", 1)[1]
    branches = set(git("branch", "--format=%(refname:short)").split())
    return next((b for b in ("main", "master") if b in branches), None)


LIFECYCLE = json.loads((spec_check.CLAUDE / "contracts" / "work-item.lifecycle.v1.json").read_text(encoding="utf-8"))
LEADING = re.compile(r"^## (References|Operating envelope)\s*$", re.M | re.I)
WARNINGS: list[str] = []  # printed by main; a warning never blocks the commit


MERGING = ("MERGE_HEAD", "SQUASH_MSG")  # a merge or squash commit carries several commits' moves at once


def frontmatter_of(text: str | None) -> dict | None:
    """The frontmatter read the same way the checker reads it (yaml); None when absent or unreadable."""
    m = re.match(r"^---\r?\n(.*?)\r?\n---", text or "", re.S)
    try:
        fm = yaml.safe_load(m.group(1)) if m else None
    except yaml.YAMLError:
        return None
    return fm if isinstance(fm, dict) else None


def status_of(text: str | None) -> str | None:
    fm = frontmatter_of(text)
    return str(fm["status"]) if fm and fm.get("status") is not None else None


def ref_text(ref: str, path: str) -> str | None:
    """A file as `ref` (a commit, `HEAD` or `MERGE_HEAD`) holds it; None when the ref or the file is absent, or the
    object cannot be read."""
    if subprocess.run(["git", "cat-file", "-e", f"{ref}:{path}"], capture_output=True, timeout=GIT_TIMEOUT_S).returncode:
        return None
    try:
        return git("show", f"{ref}:{path}")
    except GateError:
        return None  # an unreadable version counts as absent, so a commit that repairs it is not blocked


def head_text(path: str) -> str | None:
    """The HEAD version of a file; None when it is absent, HEAD is unborn, or the object cannot be read."""
    return ref_text("HEAD", path)


def head_live() -> bool:
    """Whether HEAD's repo CLAUDE.md declares `deploymentTier: live`. HEAD's copy, never the staged one: a commit cannot
    drop the declaration and lock under the lighter rule in the same breath (spec-standard-v3, FR-3)."""
    return spec_v3.live_of(head_text("CLAUDE.md"))


def live_kwargs(v3_item: bool) -> dict[str, bool]:
    """`live=` for a call that judges a v3 item; no keyword at all for a v2 item, so v2 calls stay as they were."""
    return {"live": head_live()} if v3_item else {}


def reachable(frm: str, item_type: str) -> set[str]:
    """Every state a chain of allowed moves reaches from `frm`, `frm` included."""
    edges = LIFECYCLE["edges"] + LIFECYCLE["typeEdges"].get(item_type, [])
    seen, todo = {frm}, [frm]
    while todo:
        here = todo.pop()
        for a, b in edges:
            if a == here and b not in seen:
                seen.add(b)
                todo.append(b)
    return seen


def move_allowed(frm: str | None, to: str, item_type: str, *, merging: bool) -> bool:
    """One commit makes one move; a merge or squash may carry a chain of them (each was gated on its own branch)."""
    if frm is None:
        return merging or to == LIFECYCLE["initial"]
    if merging:
        return to in reachable(frm, item_type)
    edges = LIFECYCLE["edges"] + LIFECYCLE["typeEdges"].get(item_type, [])
    return frm == to or [frm, to] in edges


def staged_changes() -> list[tuple[str, str, str]]:
    """(kind, old path, new path) per staged change: A, C, M, R, T (type change) or D; for the others old == new."""
    out = git("diff", "--cached", "--name-status", "-M", "-z", "--diff-filter=ACMRTD").split("\0")
    changes, i = [], 0
    while i < len(out) - 1:
        kind = out[i][0]
        if kind in "RC":
            old, new, i = out[i + 1], out[i + 2], i + 3
        else:
            old = new = out[i + 1]
            i += 2
        changes.append((kind, old, new))
    return changes


def staged_readmes(changes: list[tuple[str, str, str]]) -> list[tuple[str, str]]:
    """(staged path, HEAD path) per added, changed or renamed work-item README; a rename is a move, never a creation."""
    return [(new, old if kind == "R" else new) for kind, old, new in changes if kind in "ACMR" and WORK_ITEM.match(new)]


def later_status(path: str) -> str | None:
    """The later of the HEAD and MERGE_HEAD statuses of a README (lifecycle order). A README with no frontmatter block
    is a legacy file, not a v2 work item, and counts as a draft; `(unreadable)` when a frontmatter block holds no
    lifecycle status, so a damaged item is never treated as a draft; None when neither side holds the file."""
    found = [t for t in (head_text(path), ref_text("MERGE_HEAD", path)) if t is not None]
    blocks = [t for t in found if FRONTMATTER_BLOCK.match(t)]
    if found and not blocks:
        return LIFECYCLE["initial"]
    statuses = [status_of(t) for t in blocks]
    if any(s not in LIFECYCLE["states"] for s in statuses):
        return "(unreadable)"
    return max(statuses, key=LIFECYCLE["states"].index) if statuses else None


def removal_problem(changes: list[tuple[str, str, str]]) -> str | None:
    """FR-12: no README of an item past draft is deleted, moved out of `docs/work/<id>/README.md` or retyped, and no
    committed review record is deleted, unless the whole item is a draft going away."""
    gone: set[str] = set()   # item folders whose README is deleted or moved out in this commit
    added = [new for kind, _, new in changes if kind in "ACR" and WORK_ITEM.match(new)]
    for kind, old, new in changes:
        if not WORK_ITEM.match(old) or kind not in "DRT" or (kind == "R" and WORK_ITEM.match(new)):
            continue
        status = later_status(old)
        if status != LIFECYCLE["initial"]:
            hint = "; to rename the folder, rename in its own commit with the README unchanged" if kind == "D" and added else ""
            return (f"{old}: deleting or moving a {status} work item: set status: killed instead "
                    f"(it stays as history){hint}")
        if kind != "T":
            gone.add(old.rsplit("/", 1)[0])
    for kind, old, new in changes:
        if kind in "DR" and REVIEW_RECORD.match(old) and not (kind == "R" and REVIEW_RECORD.match(new)) \
                and old.rsplit("/", 2)[0] not in gone:
            return f"review records cannot be deleted: {old}"
    return None


def chain(frm: str, to: str, item_type: str) -> list[list[str]]:
    """The shortest run of lifecycle edges from `frm` to `to` ([] when equal or unreachable)."""
    edges = LIFECYCLE["edges"] + LIFECYCLE["typeEdges"].get(item_type, [])
    paths: dict[str, list[list[str]]] = {frm: []}
    todo = [frm]
    while todo:
        here = todo.pop(0)
        for a, b in edges:
            if a == here and b not in paths:
                paths[b] = [*paths[here], [a, b]]
                todo.append(b)
    return paths.get(to, [])


def merge_base_text(path: str) -> str | None:
    """The README as the merge base of HEAD and MERGE_HEAD holds it; None when there is no such base or file."""
    base = git("merge-base", "HEAD", "MERGE_HEAD", ok_codes=(0, 1)).split()
    return ref_text(base[0], path) if base else None


def edges_of_move(head_path: str, head: str | None, before: str | None, status: str, item_type: str,
                  *, merging: bool) -> list[list[str]]:
    """FR-10: the lifecycle edges this commit's move traverses. A plain commit makes its single edge; a merge, squash,
    import (no HEAD version) or repair (unreadable HEAD status) is the shortest chain from the HEAD status (draft when
    absent or unreadable). A merge in which BOTH sides moved the status away from the merge base is the chain from
    that base: neither side's record judged the merged content."""
    start = before if head is not None and before in LIFECYCLE["states"] else LIFECYCLE["initial"]
    if merging or head is None or start != before:
        edges = chain(start, status, item_type)
    else:
        edges = [[before, status]] if before != status else []
    other = ref_text("MERGE_HEAD", head_path)
    if other is not None:
        base = status_of(merge_base_text(head_path))
        base = base if base in LIFECYCLE["states"] else LIFECYCLE["initial"]
        if before != base and status_of(other) != base:
            edges += [e for e in chain(base, status, item_type) if e not in edges]
    return edges


def lifecycle_problem(tree: spec_check.Tree, readmes: list[tuple[str, str]], merging: bool) -> str | None:
    """Every staged work-item README makes an allowed move, passes its tier and, on a lock or ship move, carries a
    fresh passing review record (contracts/work-item.lifecycle.v1.json, work item review-records)."""
    for path, head_path in readmes:
        status = status_of(tree.read(path))
        head = head_text(head_path)
        head_fm = frontmatter_of(head)
        before = status_of(head)
        moved = head is None or before != status
        if status not in LIFECYCLE["states"]:
            if moved:
                return f"{path}: status `{status}` is not a lifecycle state ({', '.join(LIFECYCLE['states'])})"
            WARNINGS.append(f"warn: {path}: status `{status}` is not a lifecycle state; fix it when the item next moves")
            continue
        repair = head is not None and before not in LIFECYCLE["states"]  # an unreadable HEAD status may be repaired
        # The committed type decides the type edges, so retyping cannot unlock a move in the same commit.
        item_type = str((head_fm or spec_check.Item(tree, path).fm or {}).get("type"))
        if not repair and not move_allowed(before if head is not None else None, status, item_type, merging=merging):
            hint = "; a new item starts at draft (a folder rename is detected as a move)" if head is None else ""
            return f"{path}: move not allowed: {before or '(new)'} -> {status}{hint}"
        staged_text = tree.read(path)
        v3_item = spec_v3.involves_v3(head, staged_text)
        if v3_item and head is not None and (frozen := spec_v3.frozen_set_problem(head, staged_text)):
            import review_record  # lazy (FR-11)
            if not (merging and merged_item_equals_a_side(tree, path, head_path, status, review_record)):
                return f"{path}: {frozen}"  # a README equal to a merge side's was gated on that side's branch
        errors, warnings = spec_check.check_work_item(tree, path, require_sections=True, **live_kwargs(v3_item))
        # A v3 item has no References section: the pardon for an old README without one never applies to it.
        historical = not moved and head is not None and not LEADING.search(head) and not v3_item
        if errors and not historical:
            return f"{path} is not committable: {'; '.join(errors[:4])}"
        WARNINGS.extend(f"warn: {e}" for e in errors)
        if why := record_problem(tree, path, head_path, head, before, status, item_type, merging=merging):
            return why
    return None


def record_problem(tree: spec_check.Tree, path: str, head_path: str, head: str | None, before: str | None, status: str,
                   item_type: str, *, merging: bool) -> str | None:
    """FR-8, FR-10: on an edge into spec-locked or shipped the item needs a fresh passing record."""
    edges = edges_of_move(head_path, head, before, status, item_type, merging=merging)
    staged_text = tree.read(path)
    if spec_v3.raises_scrutiny(head, staged_text):  # spec-standard-v3 FR-11: a raise is judged like a lock
        edges = [*edges, [before, "spec-locked"]]
    if not any(to in RECORDED_STATES for _, to in edges):
        return None
    import review_record  # lazy (FR-11): a broken record or contract blocks only the moves that need it
    if merged_item_equals_a_side(tree, path, head_path, status, review_record):
        return None  # that side's history already passed the gate for exactly this content
    why = review_record.required_records(tree, path.rsplit("/", 1)[0], edges, item_type=item_type,
                                         **live_kwargs(spec_v3.involves_v3(head, staged_text)))
    return f"{path}: {why}" if why else None


def merged_item_equals_a_side(tree: spec_check.Tree, path: str, head_path: str, status: str, review_record) -> bool:
    """FR-10: in a merge (MERGE_HEAD exists), an item whose hashed files equal HEAD's or MERGE_HEAD's version, at the same
    status, derives no edges: that side's commits were gated one by one. A conflict resolved to new content, or a
    squash (no MERGE_HEAD), is not exempt."""
    if ref_text("MERGE_HEAD", head_path) is None and head_text(head_path) is None:
        return False
    if not Path(git("rev-parse", "--git-path", "MERGE_HEAD").strip()).exists():
        return False
    merged = review_record.content_hash(tree, path.rsplit("/", 1)[0])
    for rev in ("MERGE_HEAD", "HEAD"):
        text = ref_text(rev, head_path)
        if text is not None and status_of(text) == status:
            side = spec_check.HeadTree(tree.root, rev)
            try:
                if review_record.content_hash(side, head_path.rsplit("/", 1)[0]) == merged:
                    return True
            except review_record.HashError:
                continue
    return False


def merged_items_problem(tree: spec_check.Tree, changes: list[tuple[str, str, str]],
                         readmes: list[tuple[str, str]]) -> str | None:
    """A merge can move an item without touching its README (both sides locked it, the files were merged by hand):
    every item with a staged change whose README is not staged is judged by its edges alone."""
    if not Path(git("rev-parse", "--git-path", "MERGE_HEAD").strip()).exists():
        return None
    seen = {path for path, _ in readmes}
    items = sorted({f"docs/work/{m.group(1)}/README.md" for _, _, new in changes if (m := ITEM_FILE.match(new))} - seen)
    for path in items:
        status = status_of(tree.read(path)) if tree.is_file(path) else None
        head = head_text(path)
        if status in LIFECYCLE["states"] and head is not None:
            item_type = str((frontmatter_of(head) or {}).get("type"))
            if why := record_problem(tree, path, path, head, status_of(head), status, item_type, merging=True):
                return why
    return None


def reason_to_reject(message: str, message_file: Path) -> str | None:
    root = Path(git("rev-parse", "--show-toplevel").strip())
    merging = any(Path(git("rev-parse", "--git-path", name).strip()).exists() for name in MERGING)
    changes = staged_changes()
    removal = removal_problem(changes)  # first, on every branch
    if removal:
        return removal
    tree, readmes = spec_check.IndexTree(root), staged_readmes(changes)
    lifecycle = lifecycle_problem(tree, readmes, merging) or merged_items_problem(tree, changes, readmes)  # every branch
    if lifecycle:
        return lifecycle
    if any(Path(git("rev-parse", "--git-path", name).strip()).exists() for name in IN_PROGRESS):
        return None  # concluding a merge/rebase/cherry-pick/revert: the replayed commits carry their own specs
    branch = git("symbolic-ref", "-q", "--short", "HEAD", ok_codes=(0, 1)).strip()
    default = default_branch()
    if branch and default is not None and branch != default:
        return None  # agent branches and worktrees carry work in progress; the default branch is the gate
    # A detached HEAD (empty branch) or an unresolvable default branch is gated (fail closed), never waved through.
    body = message_body(message)
    trailers = re.findall(r"^Spec:\s*(\S+)\s*$", git_trailers(message_file), re.M)
    if len(trailers) > 1:
        return f"found {len(trailers)} Spec trailers; a commit cites exactly one work item"
    cited = trailers[0] if trailers else None
    root = Path(git("rev-parse", "--show-toplevel").strip())
    tree = spec_check.IndexTree(root)  # judge what will be committed, never the working tree
    staged = [f for f in git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR").split("\0") if f]
    source = [f for f in staged if SOURCE.search(f) and not NOT_SOURCE.search(f)]
    if not source or is_real_revert(body):
        # Gate-exempt commit: a trailer is optional, but a work-item trailer that is present must pass the static tier.
        return item_problem(cited, tree, for_source_commit=False) if cited and WORK_ITEM.match(cited) else None
    if cited is None:
        return (f"this commit stages source ({', '.join(source[:3])}) but has no `Spec: docs/work/<id>/README.md` "
                "trailer. Write the work item first (AC table with pass/fail conditions and tests), set its status to "
                f"`building`, cite it. Format: {STANDARD} (legacy `docs/specs/<slug>.md` is accepted until migration ends)"
                + trailer_hint(body))
    if WORK_ITEM.match(cited):
        return item_problem(cited, tree, for_source_commit=True)
    if not cited.startswith("docs/specs/") or ".." in cited or not cited.endswith(".md"):
        return f"the Spec trailer must name docs/work/<id>/README.md inside this repo, got `{cited}`"
    found = spec_check.legacy_problems(cited, tree)
    status = None if found else (spec_check.legacy_frontmatter(tree.read(cited) or "") or {}).get("status")
    if found or status not in spec_check.TRACED_STATUSES:
        return f"{cited} is not committable: {'; '.join(found[:4]) or f'status is `{status}`, must be locked or done'}"
    return None


def is_real_revert(body: str) -> bool:
    """A subject is a claim, not evidence: a revert is exempt only when its body names a commit that exists."""
    m = REVERTS.search(body)
    if not m or not body.startswith("Revert "):
        return False
    try:
        r = subprocess.run(["git", "cat-file", "-e", f"{m.group(1)}^{{commit}}"], capture_output=True, timeout=GIT_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GateError(f"git cat-file failed: {e}") from e
    return r.returncode == 0


def item_problem(cited: str, tree: spec_check.Tree, *, for_source_commit: bool) -> str | None:
    """Run the Work-Item Standard checker on the README the trailer names, as staged; CK-26 binds source commits."""
    if not tree.is_file(cited):
        return f"{cited} is not committable: the work item does not exist in this commit"
    errors, _ = spec_check.check_work_item(tree, cited, for_source_commit,
                                           **live_kwargs(spec_v3.involves_v3(tree.read(cited))))
    return f"{cited} is not committable: {'; '.join(errors[:4])}" if errors else None


def comment_char(message: str) -> str:
    """The comment character git used for THIS message file, read from git's own template lines (with
    core.commentChar=auto git picks a character per message, which a separate git process cannot know)."""
    for line in message.splitlines():
        if m := re.match(r"^(\S) -+ >8 -+$", line) or re.match(r"^(\S) Please enter the commit message", line):
            return m.group(1)
    configured = git("config", "core.commentChar", ok_codes=(0, 1)).strip()
    return configured if configured and configured != "auto" else "#"


def git_trailers(message_file: Path) -> str:
    """The trailers exactly as git reads them: the raw message file, its own comment character, the scissors handled
    by git, no `---` divider. The parse runs outside the repo with no global or system config and only pinned
    settings, so repo or user `trailer.*` config cannot change what counts as the Spec trailer."""
    message_file = Path(message_file).resolve()
    char = comment_char(message_file.read_text(encoding="utf-8", errors="replace")) if message_file.is_file() else "#"
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_CONFIG")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    try:
        r = subprocess.run(["git", "-c", "trailer.separators=:", "-c", f"core.commentChar={char}", "interpret-trailers",
                            "--parse", "--no-divider", str(message_file)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT_S, env=env,
                           cwd=tempfile.gettempdir())
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GateError(f"git interpret-trailers failed: {e}") from e
    if r.returncode != 0:
        raise GateError(f"git interpret-trailers exited {r.returncode}: {r.stderr.strip()[:200]}")
    return r.stdout


# --- Why a Spec line was not read (docs/work/fix-gate-trailer-hint) ------------------------------------------------
SPEC_SHAPED = re.compile(r"^\s*specs?\s*:\s*docs/(work|specs)/", re.I)
TRAILER_LINE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*\s*:")
HINT = "not read as a trailer"


def message_body(message: str) -> str:
    """The message as a reader sees it: the text above the `commit -v` scissors, comment lines removed."""
    char = comment_char(message)
    lines: list[str] = []
    for line in message.splitlines():
        if line.startswith(char) and re.match(rf"^{re.escape(char)} -+ >8 -+$", line):
            break
        if not line.startswith(char):
            lines.append(line)
    return "\n".join(lines).strip()


def trailer_hint(body: str) -> str:
    """Every reason git did not read a path-shaped Spec line as the `Spec` trailer (empty when there is none)."""
    paragraphs = [p.split("\n") for p in re.split(r"\n\s*\n", body.strip()) if p.strip()]
    if not paragraphs:
        return ""
    final = paragraphs[-1]
    for line in (l for p in paragraphs for l in p if SPEC_SHAPED.match(l)):
        causes: list[str] = []
        others = [l for i, l in enumerate(final) if l != line and not TRAILER_LINE.match(l)
                  and not (l[:1].isspace() and i > 0 and TRAILER_LINE.match(final[i - 1].lstrip()))]  # continuation
        if line in final and others:
            causes.append(f"the final paragraph has a non-trailer line (`{others[0].strip()}`); it may hold only trailers")
        key, _, value = line.strip().partition(":")
        if key.strip() != "Spec":
            causes.append(f"the key must be exactly `Spec` (found `{key.strip()}`)")
        if len(value.split()) > 1:
            causes.append("text follows the path; the value must be the path alone")
        if line[:1].isspace():
            causes.append("the line is indented; a trailer starts at column 0")
        if line not in final or len(paragraphs) == 1:
            causes.append("it is outside the final trailer block (git reads trailers only from the last paragraph, "
                          "after a blank line)")
        if not causes:   # D34 fallback: show what git read instead of an empty cause list
            causes.append("git read no `Spec` trailer from the final paragraph; check it holds only `Key: value` lines")
        return f" A `Spec:` line was found but {HINT}: " + "; ".join(causes) + "."
    return ""


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("spec-gate: expected the commit message file path", file=sys.stderr)
        return 1
    try:
        why = reason_to_reject(Path(argv[0]).read_text(encoding="utf-8", errors="replace"), Path(argv[0]))
    except (GateError, OSError, spec_check.ToolError, subprocess.TimeoutExpired) as e:
        why = f"gate error, so the commit is rejected (fails closed): {e}"
    for line in WARNINGS:
        print(f"spec-gate: {line}", file=sys.stderr)
    if why:
        print(f"spec-gate: {why}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
