"""Draft a fleet-ledger day: every commit made that day, grouped by repo, as rows to curate into LEDGER.md.

    python ~/.claude/scripts/ledger_draft.py [YYYY-MM-DD]     (default: today)

Read-only. Scans the git repos under D:/repo (skipping _Archive, node_modules and worktrees) plus ~/.claude.
Prints a markdown table; the curator merges related commits into one row and adds the why.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path("D:/repo")
SKIP = {"node_modules", "_Archive", ".venv", "worktrees", "foreman-worktrees", ".next"}
MAX_DEPTH = 4


def repos() -> list[Path]:
    found = [Path.home() / ".claude"]
    for dp, dns, _ in os.walk(ROOT):
        depth = len(Path(dp).relative_to(ROOT).parts)
        if ".git" in dns:
            found.append(Path(dp))
        dns[:] = [d for d in dns if d not in SKIP and not d.startswith(".") and depth < MAX_DEPTH]
    return found


def commits(repo: Path, day: date) -> list[str]:
    nxt = day + timedelta(days=1)
    r = subprocess.run(["git", "-C", str(repo), "log", "--all", f"--since={day} 00:00", f"--until={nxt} 00:00",
                        "--format=%h %ad %s", "--date=format:%H:%M"], capture_output=True, text=True, timeout=30)
    return [l for l in r.stdout.splitlines() if l.strip()]


def main() -> int:
    day = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    print(f"### {day} ({day.strftime('%a')})\nHeadline: <one line>\n")
    print("| project | change | why | ref | kind |\n|---|---|---|---|---|")
    total = 0
    for repo in repos():
        rows = commits(repo, day)
        total += len(rows)
        name = "claudence" if repo.name == ".claude" else repo.relative_to(ROOT).as_posix()
        for row in reversed(rows):
            sha, hhmm, subject = row.split(" ", 2)
            print(f"| {name} | {subject} | <why> | {sha} ({hhmm}) | <kind> |")
    print(f"\n<!-- {total} commits; merge related rows, add Incidents and Watch -->")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
