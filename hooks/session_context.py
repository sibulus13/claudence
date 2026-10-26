"""SessionStart context: inject facts instead of instructing Claude to go find them.

- the repo's state doc (first match) and whether it is older than the last commit;
- the repo's deploymentTier (from its CLAUDE.md), or a warning that it is undeclared;
- after a compaction: the standing ask to summarize in-progress work, open states and the next step.
Prints additionalContext JSON; prints nothing when there is nothing to say.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

STATE_DOCS = ("docs/STATE.md", "STATE.md", "workflow_state.md", "todo.md", "context.md", "docs/KNOWLEDGE.md",
              "ROADMAP.md", "docs/ROADMAP.md")
TIER = re.compile(r"deploymentTier:\s*`?([a-z-]+)", re.I)


def repo_root(cwd: str) -> Path | None:
    r = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10)
    return Path(r.stdout.strip()) if r.returncode == 0 else None


def last_commit_epoch(root: Path) -> int:
    r = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%ct"], capture_output=True, text=True,
                       timeout=10)
    return int(r.stdout.strip() or 0)


def lines_for(cwd: str, source: str) -> list[str]:
    out = []
    root = repo_root(cwd)
    if root is None:
        out.append("Fleet session (not inside a repo): project hooks and memory arrive via the D:/repo router "
                   "on first touch of a project.")
    else:
        doc = next((root / d for d in STATE_DOCS if (root / d).exists()), None)
        if doc:
            stale = doc.stat().st_mtime < last_commit_epoch(root) - 86400
            out.append(f"State doc: {doc.as_posix()}{' (older than the last commit by >1 day: spot-check it)' if stale else ''}. "
                       "Read it before changing code.")
        else:
            out.append(f"No state doc in {root.as_posix()}: that is itself a finding.")
        claude_md = root / "CLAUDE.md"
        m = TIER.search(claude_md.read_text(encoding="utf-8", errors="replace")) if claude_md.exists() else None
        out.append(f"deploymentTier: {m.group(1)}" if m else "deploymentTier: undeclared (treat as pre-traffic; declare it).")
    if source == "compact":
        out.append("After compaction: first summarize what was in progress, any temporary states left in place, "
                   "and the next concrete step.")
    return out


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    lines = lines_for(event.get("cwd") or ".", event.get("source") or "startup")
    if lines:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": "\n".join(lines)}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
