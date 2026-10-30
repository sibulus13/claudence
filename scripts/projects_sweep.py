"""Dry-run sweep of <root>/projects: reports Claude Code project dirs that are clutter. Deletes nothing.

    python ~/.claude/scripts/projects_sweep.py [--json] [--root DIR] [--config FILE] [--out FILE]

A direct child of projects/ is a candidate when it is older than `sweepMinAgeDays` and
  empty               holds no files at all,
  temp                its name matches a `sweepTempPatterns` regex (summarizer, probe and e2e working dirs), or
  orphaned-worktree   its name matches `sweepWorktreePatterns` and no live git worktree maps to that name.
A dir holding memory notes is never a candidate. There is no --apply: deleting is a separate, owner-approved step.
Report: <root>/state/projects-sweep.json. A new finding is a candidate category seen for the first time.
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
from upkeep_config import config_path, load_config

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
                           text=True, timeout=30)
        paths.update(line[len("worktree "):] for line in r.stdout.splitlines() if line.startswith("worktree "))
    return {encode_cwd(p) for p in paths}


def files_in(d: Path) -> list[Path]:
    return [p for p in d.rglob("*") if p.is_file()]


def has_memory(files: list[Path], d: Path) -> bool:
    return any(p.relative_to(d).parts[0] == "memory" for p in files)


def sweep(root: Path, cfg: dict, previous_categories: set[str] | None = None, now: float | None = None) -> dict:
    now = now if now is not None else time.time()
    min_age = cfg["sweepMinAgeDays"] * DAY_S
    temp = [re.compile(p) for p in cfg["sweepTempPatterns"]]
    worktree = [re.compile(p) for p in cfg["sweepWorktreePatterns"]]
    projects = root / "projects"
    live = live_worktree_names(root, cfg) if any(worktree) else set()
    candidates = []
    for d in sorted(p for p in projects.iterdir() if p.is_dir()) if projects.is_dir() else []:
        age = now - d.stat().st_mtime
        if age < min_age:
            continue
        files = files_in(d)
        if has_memory(files, d):
            continue
        if not files:
            reason = "empty"
        elif any(rx.search(d.name) for rx in temp):
            reason = "temp"
        elif any(rx.search(d.name) for rx in worktree) and d.name not in live:
            reason = "orphaned-worktree"
        else:
            continue
        candidates.append({"path": d.as_posix(), "reason": reason, "ageDays": int(age // DAY_S),
                           "bytes": sum(p.stat().st_size for p in files)})
    categories = sorted({c["reason"] for c in candidates})
    fresh = categories if previous_categories is None else [c for c in categories if c not in previous_categories]
    counts = {c: sum(1 for x in candidates if x["reason"] == c) for c in categories}
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dryRun": True,
        "counts": counts,
        "totalBytes": sum(c["bytes"] for c in candidates),
        "candidates": candidates,
        "newFindings": [{"id": f"projects-sweep:{c}", "summary": f"would delete {counts[c]} {c} project dir(s)"}
                        for c in fresh],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", type=Path, default=Path.home() / ".claude")
    ap.add_argument("--config", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    cfg = load_config(args.config or config_path(args.root))
    out = args.out or args.root / "state" / "projects-sweep.json"
    previous = set(json.loads(out.read_text(encoding="utf-8"))["counts"]) if out.exists() else None
    report = sweep(args.root, cfg, previous)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    if args.json:
        sys.stdout.write(json.dumps(report) + "\n")
    else:
        print(f"projects-sweep (dry-run): {report['counts']} {report['totalBytes']} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
