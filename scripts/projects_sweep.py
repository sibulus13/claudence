"""Dry-run sweep of <root>/projects: reports Claude Code project dirs that are clutter. Deletes nothing.

    python ~/.claude/scripts/projects_sweep.py [--json] [--root DIR] [--config FILE] [--out FILE]

A direct child of projects/ is a candidate when its newest file is older than `sweepMinAgeDays` and
  empty               holds no files at all,
  temp                its name matches a `sweepTempPatterns` regex (summarizer, probe and e2e working dirs), or
  orphaned-worktree   its name matches `sweepWorktreePatterns` and no live git worktree maps to that name.
A dir holding memory notes is never a candidate. There is no --apply: deleting is a separate, owner-approved step.
Age is the newest file inside the dir. Report: <root>/state/projects-sweep.pending.json, promoted to projects-sweep.json
by --commit (the baseline). One finding per dir; it is new when its dir is not in the baseline.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from ledger_draft import repos
from upkeep_config import HIDDEN, commit_pending, config_path, load_config, previous_ids, store_pending

DAY_S = 86400
WORKTREE_PARENTS = (".git/foreman-worktrees", ".claude/worktrees")


def encode_cwd(path: Path | str) -> str:
    """Claude Code names a project dir after its cwd: every non-alphanumeric character becomes '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", Path(path).as_posix() if isinstance(path, Path) else path)


def live_worktree_names(root: Path, cfg: dict) -> set[str]:
    paths: set[str] = set()
    for repo in repos(root, cfg):
        for parent in WORKTREE_PARENTS:
            base = repo / parent
            if base.is_dir():
                paths.update(p.as_posix() for p in base.iterdir() if p.is_dir())
        r = subprocess.run(["git", "-C", str(repo), "worktree", "list", "--porcelain"], capture_output=True,
                           text=True, timeout=30, **HIDDEN)
        paths.update(line[len("worktree "):] for line in r.stdout.splitlines() if line.startswith("worktree "))
    return {encode_cwd(p) for p in paths}


def files_in(d: Path) -> list[Path]:
    return [p for p in d.rglob("*") if p.is_file()]


def has_memory(files: list[Path], d: Path) -> bool:
    return any(p.relative_to(d).parts[0] == "memory" for p in files)


def last_activity(d: Path, files: list[Path]) -> float:
    """A dir's age is its newest file: the dir's own mtime does not change when a session appends to a file."""
    return max((p.stat().st_mtime for p in files), default=d.stat().st_mtime)


def sweep(root: Path, cfg: dict, previous: set[str] | None = None, now: float | None = None) -> dict:
    now = now if now is not None else time.time()
    min_age = cfg["sweepMinAgeDays"] * DAY_S
    temp = [re.compile(p) for p in cfg["sweepTempPatterns"]]
    worktree = [re.compile(p) for p in cfg["sweepWorktreePatterns"]]
    projects = root / "projects"
    live = live_worktree_names(root, cfg) if any(worktree) else set()
    candidates = []
    for d in sorted(p for p in projects.iterdir() if p.is_dir()) if projects.is_dir() else []:
        files = files_in(d)
        age = now - last_activity(d, files)
        if age < min_age or has_memory(files, d):
            continue
        if not files:
            reason = "empty"
        elif any(rx.search(d.name) for rx in temp):
            reason = "temp"
        elif any(rx.search(d.name) for rx in worktree) and d.name not in live:
            reason = "orphaned-worktree"
        else:
            continue
        candidates.append({"id": f"projects-sweep:{d.name}", "path": d.as_posix(), "reason": reason,
                           "ageDays": int(age // DAY_S), "bytes": sum(p.stat().st_size for p in files)})
    counts = {c: sum(1 for x in candidates if x["reason"] == c) for c in sorted({x["reason"] for x in candidates})}
    fresh = [c for c in candidates if previous is None or c["id"] not in previous]
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dryRun": True,
        "counts": counts,
        "totalBytes": sum(c["bytes"] for c in candidates),
        "findings": candidates,
        "newFindings": [{"id": c["id"], "summary": f"would delete {c['reason']} dir {Path(c['path']).name} ({c['ageDays']} d)"}
                        for c in fresh],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", type=Path, default=Path.home() / ".claude")
    ap.add_argument("--config", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--commit", action="store_true", help="promote the pending report to the baseline (after delivery)")
    args = ap.parse_args(argv)
    cfg = load_config(args.config or config_path(args.root))
    out = args.out or args.root / "state" / "projects-sweep.json"
    if args.commit:
        commit_pending(out)
        return 0
    report = sweep(args.root, cfg, previous_ids(out))
    store_pending(out, report)
    if args.json:
        sys.stdout.write(json.dumps(report) + "\n")
    else:
        print(f"projects-sweep (dry-run): {report['counts']} {report['totalBytes']} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
