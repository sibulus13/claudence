"""Read-only audit of the user's Windows scheduled tasks: failing results and dead triggers.

    python ~/.claude/scripts/tasks_audit.py [--json] [--root DIR] [--config FILE] [--out FILE] [--tasks-file FILE]

Tasks matching `tasksIgnoreRegex` (vendor updaters) are skipped. Rows come from tasks_inventory.ps1 (read-only Get-ScheduledTask), or --tasks-file for tests. Finding kinds:
  failing         LastTaskResult is not one of `tasksFailingResultsAllowed` (0 ok, running, not yet run)
  disabled-long   disabled and last run more than `tasksDeadDays` ago
  never-run       enabled but has never run
  next-run-far    next run more than `tasksNextRunFarDays` away (a 2099 placeholder trigger)
Report: <root>/state/tasks-audit.json; a new finding is an id absent from the previous report. Changes nothing.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from upkeep_config import config_path, load_config

INVENTORY = Path(__file__).with_name("tasks_inventory.ps1")
NEVER_RUN_BEFORE_YEAR = 2000  # Windows reports a never-run task as 1999-11-30


def parse(ts: str | None) -> datetime | None:
    return datetime.fromisoformat(ts) if ts else None


def audit(tasks: list[dict], cfg: dict, now: datetime) -> list[dict]:
    out = []

    def add(kind: str, t: dict, detail: str) -> None:
        out.append({"id": f"tasks-audit:{kind}:{t['name']}", "kind": kind, "task": t["name"], "detail": detail})

    ignore = [re.compile(p) for p in cfg["tasksIgnoreRegex"]]
    for t in tasks:
        if any(rx.search(t["name"]) for rx in ignore):
            continue
        last, nxt = parse(t["lastRun"]), parse(t["nextRun"])
        disabled = t["state"] == "Disabled"
        never = last is None or last.year < NEVER_RUN_BEFORE_YEAR
        if t["lastResult"] not in cfg["tasksFailingResultsAllowed"]:
            add("failing", t, f"LastTaskResult 0x{t['lastResult'] & 0xFFFFFFFF:X} ({t['lastResult']})")
        if disabled and not never and (now - last).days > cfg["tasksDeadDays"]:
            add("disabled-long", t, f"disabled, last ran {(now - last).days} days ago")
        if not disabled and never:
            add("never-run", t, "enabled but has never run")
        if nxt and (nxt - now).days > cfg["tasksNextRunFarDays"]:
            add("next-run-far", t, f"next run {nxt.date()}")
    return out


def report(tasks: list[dict], cfg: dict, now: datetime, previous_ids: set[str] | None) -> dict:
    findings = audit(tasks, cfg, now)
    new = [f for f in findings if previous_ids is None or f["id"] not in previous_ids]
    return {"generatedAt": now.isoformat(timespec="seconds"), "taskCount": len(tasks), "total": len(findings),
            "newFindings": [{"id": f["id"], "summary": f"{f['task']}: {f['detail']}"} for f in new],
            "findings": findings}


def collect() -> list[dict]:
    r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(INVENTORY)],
                       capture_output=True, check=True, timeout=120)
    return json.loads(r.stdout.decode("utf-8-sig"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", type=Path, default=Path.home() / ".claude")
    ap.add_argument("--config", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--tasks-file", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    cfg = load_config(args.config or config_path(args.root))
    out = args.out or args.root / "state" / "tasks-audit.json"
    tasks = json.loads(args.tasks_file.read_text(encoding="utf-8")) if args.tasks_file else collect()
    previous = {f["id"] for f in json.loads(out.read_text(encoding="utf-8"))["findings"]} if out.exists() else None
    rep = report(tasks, cfg, datetime.now(timezone.utc).astimezone(), previous)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    if args.json:
        sys.stdout.write(json.dumps(rep) + "\n")
    else:
        print(f"tasks-audit: {rep['taskCount']} tasks, {rep['total']} findings ({len(rep['newFindings'])} new)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
