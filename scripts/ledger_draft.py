"""Draft fleet-ledger days: every commit made that day, grouped by repo, as rows to curate into LEDGER.md.

    python ~/.claude/scripts/ledger_draft.py [YYYY-MM-DD]                      print one day (default: today)
    python ~/.claude/scripts/ledger_draft.py [DATE] --days 7 --out DIR --json  nightly job: draft each unledgered day

Never writes the ledger. With --out it writes `<DIR>/<date>.md` for each of the last --days days (ending at DATE)
that has commits and no `### <date>` heading in the ledger file; the curator (/ledger) merges the draft into the
ledger and deletes the draft file. A day above `ledgerDraftMinCommits` commits with no ledger row is flagged, and
is a new finding until a `--commit` records its id in `<root>/state/ledger-draft.json` (pending report first). Repo tree and thresholds come from upkeep.config.json.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import date, timedelta
from pathlib import Path

from upkeep_config import HIDDEN, commit_pending, config_path, load_config, previous_ids, store_pending, write_atomic

MAX_DEPTH = 4


def repos(root: Path, cfg: dict) -> list[Path]:
    found = [root]
    tree = Path(cfg["repoRoot"]) if cfg["repoRoot"] else None
    if tree is None or not tree.is_dir():
        return found
    skip = set(cfg["repoSkip"])
    for dp, dns, _ in os.walk(tree):
        depth = len(Path(dp).relative_to(tree).parts)
        if ".git" in dns:
            found.append(Path(dp))
        dns[:] = [d for d in dns if d not in skip and not d.startswith(".") and depth < MAX_DEPTH]
    return found


def commits(repo: Path, day: date) -> list[str]:
    nxt = day + timedelta(days=1)
    r = subprocess.run(["git", "-C", str(repo), "log", "--all", f"--since={day} 00:00", f"--until={nxt} 00:00",
                        "--format=%h %ad %s", "--date=format:%H:%M"], capture_output=True, text=True, timeout=30, **HIDDEN)
    return [line for line in r.stdout.splitlines() if line.strip()]


def repo_name(root: Path, cfg: dict, repo: Path) -> str:
    if repo == root:
        return "claudence"
    return repo.relative_to(Path(cfg["repoRoot"])).as_posix()


def render(day: date, by_repo: dict[str, list[str]]) -> str:
    total = sum(len(rows) for rows in by_repo.values())
    out = [f"### {day} ({day.strftime('%a')})", "Headline: <one line>", "",
           "| project | change | why | ref | kind |", "|---|---|---|---|---|"]
    for name, rows in by_repo.items():
        for row in reversed(rows):
            sha, hhmm, subject = row.split(" ", 2)
            out.append(f"| {name} | {subject} | <why> | {sha} ({hhmm}) | <kind> |")
    out += ["", f"<!-- {total} commits; merge related rows, add Incidents and Watch -->"]
    return "\n".join(out) + "\n"


def ledger_has_day(ledger_text: str, day: date) -> bool:
    """A `### <date>` heading at line start, followed by anything but another digit (also at end of file)."""
    return re.search(rf"^### {day}(?!\d)", ledger_text, re.M) is not None


def finding_id(day: date) -> str:
    return f"ledger-draft:{day}"


def day_commits(root: Path, cfg: dict, day: date) -> dict[str, list[str]]:
    by_repo = {}
    for repo in repos(root, cfg):
        rows = commits(repo, day)
        if rows:
            by_repo[repo_name(root, cfg, repo)] = rows
    return by_repo


def plan(root: Path, cfg: dict, end: date, days: int, out_dir: Path, previous: set[str] | None = None) -> list[dict]:
    """Draft every unledgered day in the window (never overwriting a draft the curator may be editing).

    A flagged day is new when its finding id is not in `previous`, the committed (delivered) ids; None = all new."""
    ledger = root / cfg["ledgerFile"]
    ledger_text = ledger.read_text(encoding="utf-8") if ledger.exists() else ""
    report = []
    for back in range(days):
        day = end - timedelta(days=back)
        ledgered = ledger_has_day(ledger_text, day)
        entry = {"date": str(day), "ledgered": ledgered, "commits": 0, "draft": None, "flagged": False, "new": False}
        if not ledgered:
            by_repo = day_commits(root, cfg, day)
            entry["commits"] = sum(len(r) for r in by_repo.values())
            if entry["commits"]:
                draft = out_dir / f"{day}.md"
                if not draft.exists():
                    write_atomic(draft, render(day, by_repo))
                entry["draft"] = draft.as_posix()
                entry["flagged"] = entry["commits"] > cfg["ledgerDraftMinCommits"]
                entry["new"] = entry["flagged"] and (previous is None or finding_id(day) not in previous)
        report.append(entry)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("date", nargs="?", type=date.fromisoformat, default=date.today())
    ap.add_argument("--root", type=Path, default=Path.home() / ".claude")
    ap.add_argument("--config", type=Path)
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--out", type=Path, help="drafts directory (default: print the one day)")
    ap.add_argument("--state", type=Path, help="committed report (default: <root>/state/ledger-draft.json)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--commit", action="store_true", help="promote the pending report to the baseline (after delivery)")
    args = ap.parse_args(argv)
    cfg = load_config(args.config or config_path(args.root))
    state = args.state or args.root / "state" / "ledger-draft.json"
    if args.commit:
        commit_pending(state)
        return 0
    if args.out is None:
        print(render(args.date, day_commits(args.root, cfg, args.date)), end="")
        return 0
    report = plan(args.root, cfg, args.date, args.days, args.out, previous_ids(state))

    def summary(e: dict) -> dict:
        return {"id": finding_id(date.fromisoformat(e["date"])), "summary": f"{e['date']}: {e['commits']} commits, no ledger row"}

    out = {"days": report, "findings": [summary(e) for e in report if e["flagged"]],
           "newFindings": [summary(e) for e in report if e["new"]]}
    store_pending(state, out)
    if args.json:
        print(json.dumps(out))
    else:
        for e in report:
            if e["draft"]:
                print(f"{e['date']}: {e['commits']} commits drafted to {e['draft']}{' FLAGGED' if e['flagged'] else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
