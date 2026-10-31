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

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spec_check  # noqa: E402

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


def reason_to_reject(message: str) -> str | None:
    if any(Path(git("rev-parse", "--git-path", name).strip()).exists() for name in IN_PROGRESS):
        return None  # concluding a merge/rebase/cherry-pick/revert: the replayed commits carry their own specs
    branch = git("symbolic-ref", "-q", "--short", "HEAD", ok_codes=(0, 1)).strip()
    default = default_branch()
    if branch and default is not None and branch != default:
        return None  # agent branches and worktrees carry work in progress; the default branch is the gate
    # A detached HEAD (empty branch) or an unresolvable default branch is gated (fail closed), never waved through.
    body = "\n".join(line for line in message.splitlines() if not line.startswith("#")).strip()
    trailers = re.findall(r"^Spec:\s*(\S+)\s*$", git_trailers(body), re.M)
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
                f"`building`, cite it. Format: {STANDARD} (legacy `docs/specs/<slug>.md` is accepted until migration ends)")
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


def git_trailers(body: str) -> str:
    try:
        r = subprocess.run(["git", "interpret-trailers", "--parse"], input=body, capture_output=True, text=True,
                           encoding="utf-8", timeout=GIT_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GateError(f"git interpret-trailers failed: {e}") from e
    return r.stdout


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("spec-gate: expected the commit message file path", file=sys.stderr)
        return 1
    try:
        why = reason_to_reject(Path(argv[0]).read_text(encoding="utf-8", errors="replace"))
    except (GateError, OSError, spec_check.ToolError, subprocess.TimeoutExpired) as e:
        why = f"gate error, so the commit is rejected (fails closed): {e}"
    if why:
        print(f"spec-gate: {why}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
