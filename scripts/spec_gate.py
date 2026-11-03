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
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spec_check  # noqa: E402
import yaml  # noqa: E402

SOURCE = re.compile(r"(\.(py|[cm]?[jt]sx?|ps1|psm1|lua|go|rs|sh|bat|cmd|rb|java|cs|php|sql|vbs|vue|svelte|html|css|"
                    r"c|cc|cpp|h|hpp|kt|kts|swift|scala|ex|exs|ipynb|m|r|pl|tf)|(^|/)Dockerfile)$", re.I)
# Tests (one definition, shared with the checker's CK-20), build output at the repo root only, vendored and generated files.
NOT_SOURCE = re.compile(spec_check.TEST_PATH.pattern + r"|^(dist|build|out|coverage)/|(^|/)node_modules/|\.d\.ts$|"
                        r"\.min\.(js|css)$", re.I)
WORK_ITEM = re.compile(r"^docs/work/(?!\.\.?/)[\w.-]+/README\.md$")
REVERTS = re.compile(r"^This reverts commit ([0-9a-f]{7,40})\b", re.M)
IN_PROGRESS = ("MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD")
GIT_TIMEOUT_S = 10
STANDARD = "~/.claude/skills/dark-factory/WORK-ITEM-STANDARD.md"


class GateError(Exception):
    pass


def git(*args: str, ok_codes: tuple[int, ...] = (0,)) -> str:
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


def head_text(path: str) -> str | None:
    """The HEAD version of a file; None when it is absent, HEAD is unborn, or the object cannot be read."""
    if subprocess.run(["git", "cat-file", "-e", f"HEAD:{path}"], capture_output=True, timeout=GIT_TIMEOUT_S).returncode:
        return None
    try:
        return git("show", f"HEAD:{path}")
    except GateError:
        return None  # an unreadable HEAD version counts as absent, so a commit that repairs it is not blocked


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


def staged_readmes() -> list[tuple[str, str]]:
    """(staged path, HEAD path) per added, changed or renamed work-item README; a rename is a move, never a creation."""
    out = git("diff", "--cached", "--name-status", "-M", "-z", "--diff-filter=ACMR").split("\0")
    pairs, i = [], 0
    while i < len(out) - 1:
        kind = out[i]
        if kind.startswith(("R", "C")):
            old, new, i = out[i + 1], out[i + 2], i + 3
        else:
            old = new = out[i + 1]
            i += 2
        if WORK_ITEM.match(new):
            pairs.append((new, old if kind.startswith("R") else new))
    return pairs


def lifecycle_problem(tree: spec_check.Tree, readmes: list[tuple[str, str]], merging: bool) -> str | None:
    """Every staged work-item README makes an allowed move and passes its tier (contracts/work-item.lifecycle.v1.json)."""
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
        errors, warnings = spec_check.check_work_item(tree, path, require_sections=True)
        historical = not moved and head is not None and not LEADING.search(head)
        if errors and not historical:
            return f"{path} is not committable: {'; '.join(errors[:4])}"
        WARNINGS.extend(f"warn: {e}" for e in errors)
    return None


def reason_to_reject(message: str, message_file: Path) -> str | None:
    root = Path(git("rev-parse", "--show-toplevel").strip())
    merging = any(Path(git("rev-parse", "--git-path", name).strip()).exists() for name in MERGING)
    lifecycle = lifecycle_problem(spec_check.IndexTree(root), staged_readmes(), merging)  # first, on every branch
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
    errors, _ = spec_check.check_work_item(tree, cited, for_source_commit)
    return f"{cited} is not committable: {'; '.join(errors[:4])}" if errors else None


def git_trailers(message_file: Path) -> str:
    """The trailers exactly as git reads them: the raw message file (git handles comments, core.commentChar and the
    `commit -v` scissors itself), no `---` divider, separators pinned so repo config cannot change the reading."""
    try:
        r = subprocess.run(["git", "-c", "trailer.separators=:", "interpret-trailers", "--parse", "--no-divider",
                            str(message_file)], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=GIT_TIMEOUT_S)
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
    char = git("config", "core.commentChar", ok_codes=(0, 1)).strip() or "#"
    char = "#" if char == "auto" else char
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
        others = [l for l in final if l != line and not TRAILER_LINE.match(l)]
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
