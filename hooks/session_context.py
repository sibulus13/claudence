"""SessionStart context: inject facts instead of instructing Claude to go find them.

- the repo's state doc (first match) and whether it is older than the last commit;
- the repo's deploymentTier (from its CLAUDE.md), or a warning that it is undeclared;
- ledger drafts the nightly job wrote that /ledger has not confirmed yet;
- after a compaction: the standing ask to summarize in-progress work, open states and the next step.
Prints additionalContext JSON; prints nothing when there is nothing to say.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ledger_draft import ledger_has_day  # noqa: E402  (one definition of "the ledger has this day")

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


FLEET_DIR = Path.home() / ".claude" / "docs" / "fleet"
DRAFTS_DIR = FLEET_DIR / "drafts"
LEDGER_FILE = FLEET_DIR / "LEDGER.md"


def pending_drafts(drafts_dir: Path = DRAFTS_DIR, ledger_file: Path = LEDGER_FILE) -> list[str]:
    """Draft days the ledger does not have a row for yet (a draft whose day is already curated is stale)."""
    if not drafts_dir.is_dir():
        return []
    ledger = ledger_file.read_text(encoding="utf-8", errors="replace") if ledger_file.exists() else ""
    # Only <YYYY-MM-DD>.md is a draft; a stray note or an edited copy must never break session start.
    days = (p.stem for p in drafts_dir.glob("*.md") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.stem))
    return sorted(d for d in days if not ledger_has_day(ledger, date.fromisoformat(d)))


def lines_for(cwd: str, source: str, drafts_dir: Path = DRAFTS_DIR, ledger_file: Path = LEDGER_FILE) -> list[str]:
    out = []
    pending = pending_drafts(drafts_dir, ledger_file)
    if pending:
        out.append(f"ledger draft for {', '.join(pending)} pending: run /ledger to curate it into LEDGER.md.")
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
