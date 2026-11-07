"""pre-commit hook: refuse a staged DECISIONS.md that adds a duplicate decision id.

    python decision_ids.py <path>...      (pre-commit passes the matching staged files)

Compares the staged file with HEAD, so a duplicate that already exists never blocks unrelated work.
Work item: docs/work/decision-ids/.
"""
from __future__ import annotations

import collections
import re
import subprocess
import sys

ROW_ID = re.compile(r"^\|\s*([A-Z]+-?[A-Z]*-?\d+)\s*\|", re.M)
GIT_TIMEOUT_S = 30


def duplicates(text: str) -> set[str]:
    return {k for k, n in collections.Counter(ROW_ID.findall(text)).items() if n > 1}


def new_duplicates(head: str, staged: str) -> list[str]:
    return sorted(duplicates(staged) - duplicates(head))


def git_show(ref: str) -> str:
    run = subprocess.run(["git", "show", ref], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT_S)
    return run.stdout if run.returncode == 0 else ""


def main(paths: list[str]) -> int:
    failed = 0
    for path in paths:
        clashes = new_duplicates(git_show(f"HEAD:{path}"), git_show(f":{path}"))
        if clashes:
            print(f"decision-ids: {path} adds duplicate ids {', '.join(clashes)}; take the next free id", file=sys.stderr)
            failed = 1
    return failed


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
