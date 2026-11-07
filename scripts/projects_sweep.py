"""Dry-run sweep of <root>/projects: reports Claude Code project dirs that are clutter. Deletes nothing.

    python ~/.claude/scripts/projects_sweep.py [--json] [--root DIR] [--config FILE] [--out FILE]

A direct child of projects/ is a candidate when its newest file is older than `sweepMinAgeDays` and
  empty               holds no files at all,
  temp                its name matches a `sweepTempPatterns` regex (summarizer, probe and e2e working dirs), or
  orphaned-worktree   its name matches `sweepWorktreePatterns` and no live git worktree maps to that name.
A dir holding memory notes is never a candidate.

Lifecycle cycle (owner, 2026-11-07; docs/work/context-lifecycle): `plan` lists, and `--apply` carries out,
  memory notes   unread and unedited `memoryArchiveDays` -> <memory>/archive/, out of MEMORY.md; deleted `memoryDeleteDays` later
  snapshots      fleet docs classed snapshot, unread `reportArchiveDays` -> <dir>/archive/YYYY-MM/; never deleted
  scratch        fleet docs classed scratch, and the clutter dirs above, unread `scratchArchiveDays` -> archive;
                 deleted `scratchDeleteDays` later
Unread time counts from the oldest transcript (context_reads.py), so nothing moves before the record is long enough.
Age is the newest file inside the dir. Report: <root>/state/projects-sweep.pending.json, promoted to projects-sweep.json
by --commit (the baseline). One finding per dir; it is new when its dir is not in the baseline.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from context_catalog import classify, docs, rules
from context_reads import key, last_reads
from fleet_paths import fleet_docs_dir
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


GIT_TIMEOUT_S = 30
SCRATCH_ARCHIVE = Path("archive") / "scratch"  # the only fleet folder files are deleted from; snapshots never land here
MONTH = re.compile(r"(\d{4})-(\d{2})-\d{2}")


def month_of(p: Path) -> str:
    m = MONTH.search(p.name)
    return f"{m.group(1)}-{m.group(2)}" if m else datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m")


def plan(root: Path, fleet: Path, cfg: dict, now: float | None = None) -> list[dict]:
    """Every move and deletion the lifecycle cycle calls for now. Pure: reads files, changes nothing."""
    now = now if now is not None else time.time()
    catalogue = rules(fleet) if fleet.is_dir() else []
    classed = [(p, classify(fleet, p, catalogue)) for p in (docs(fleet) if fleet.is_dir() else [])]
    notes = [p for d in (root / "projects").glob("*/memory") for p in d.glob("*.md") if p.name != "MEMORY.md"]
    swept = [(p, c["lifecycle"]) for p, c in classed if c and c["lifecycle"] in ("snapshot", "scratch")]
    reads, oldest = last_reads(root / "projects", notes + [p for p, _ in swept])

    def unread_days(p: Path) -> float:
        return (now - max(p.stat().st_mtime, reads.get(key(p), 0.0), oldest or now)) / DAY_S

    def aged(p: Path) -> float:
        return (now - p.stat().st_mtime) / DAY_S

    actions = []
    for p in notes:
        if unread_days(p) > cfg["memoryArchiveDays"]:
            actions.append({"action": "archive", "kind": "memory", "path": p.as_posix(),
                            "dest": (p.parent / "archive" / p.name).as_posix(), "index": (p.parent / "MEMORY.md").as_posix()})
    for p in (q for d in (root / "projects").glob("*/memory/archive") for q in d.glob("*.md")):
        if aged(p) > cfg["memoryDeleteDays"]:
            actions.append({"action": "delete", "kind": "memory", "path": p.as_posix()})
    for p, cls in swept:
        if cls == "snapshot" and unread_days(p) > cfg["reportArchiveDays"]:
            dest = p.parent / "archive" / month_of(p) / p.name
            actions.append({"action": "archive", "kind": "snapshot", "path": p.as_posix(), "dest": dest.as_posix()})
        elif cls == "scratch" and unread_days(p) > cfg["scratchArchiveDays"]:
            dest = fleet / SCRATCH_ARCHIVE / p.relative_to(fleet)
            actions.append({"action": "archive", "kind": "scratch", "path": p.as_posix(), "dest": dest.as_posix()})
    scratch_archive = fleet / SCRATCH_ARCHIVE
    for p in (q for q in scratch_archive.rglob("*") if q.is_file()) if scratch_archive.is_dir() else []:
        if aged(p) > cfg["scratchDeleteDays"]:
            actions.append({"action": "delete", "kind": "scratch", "path": p.as_posix()})
    if (root / "projects").is_dir():
        for c in sweep(root, {**cfg, "sweepMinAgeDays": cfg["scratchArchiveDays"]}, now=now)["findings"]:
            dest = root / "archive" / "projects" / Path(c["path"]).name
            actions.append({"action": "archive", "kind": "scratch", "path": c["path"], "dest": dest.as_posix()})
    archived = root / "archive" / "projects"
    for d in (q for q in archived.iterdir() if q.is_dir()) if archived.is_dir() else []:
        if aged(d) > cfg["scratchDeleteDays"]:
            actions.append({"action": "delete", "kind": "scratch", "path": d.as_posix()})
    return actions


def drop_index_line(index: Path, name: str) -> None:
    if index.exists():
        lines = index.read_text(encoding="utf-8").splitlines(keepends=True)
        index.write_text("".join(line for line in lines if f"]({name})" not in line), encoding="utf-8")


def apply_one(a: dict, now: float) -> None:
    src = Path(a["path"])
    if a["action"] == "delete":
        shutil.rmtree(src) if src.is_dir() else src.unlink(missing_ok=True)
        return
    dest = Path(a["dest"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    os.utime(dest, (now, now))
    if a.get("index"):
        drop_index_line(Path(a["index"]), src.name)


def apply(actions: list[dict], now: float | None = None) -> list[dict]:
    """Carry out `plan`'s actions one file at a time; an archived file's age restarts at the move. An error stops the run
    (exit 1, traceback in the task log); the moves already made are marked done."""
    now = now if now is not None else time.time()
    for a in actions:
        apply_one(a, now)
        a["outcome"] = "done"
    return actions


def git_run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=GIT_TIMEOUT_S)


def commit_moves(fleet: Path, actions: list[dict]) -> list[str]:
    """Commit only the fleet docs paths the sweep changed: tracked sources, and destinations git does not ignore.
    Other sessions' work in progress is never staged. Returns named failures; an empty list means committed or nothing to do."""
    root = fleet.resolve()
    touched = sorted({Path(p).resolve().relative_to(root).as_posix() for a in actions if a.get("outcome") == "done"
                      for p in (a["path"], a.get("dest")) if p and Path(p).resolve().is_relative_to(root)})
    if not touched:
        return []
    tracked = set(git_run(fleet, "ls-files", "--", *touched).stdout.split("\n"))
    ignored = set(git_run(fleet, "check-ignore", "--", *touched).stdout.split("\n"))
    paths = sorted(p for p in touched if p in tracked or (p not in ignored and (root / p).exists()))
    if not paths:
        return []
    failures = []
    for step in (["add", "-A", "--", *paths],
                 ["commit", "-q", "-m", f"chore: weekly context sweep moved {len(paths)} fleet doc paths", "--", *paths]):
        r = git_run(fleet, *step)
        if r.returncode != 0:
            return [f"git-{step[0]}-failed: {(r.stderr or r.stdout).strip()[:300]}"]
    if git_run(fleet, "rev-parse", "--abbrev-ref", "@{u}").returncode == 0:
        r = git_run(fleet, "push", "-q")
        if r.returncode != 0:
            failures.append(f"git-push-failed: {r.stderr.strip()[:300]}")
    return failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", type=Path, default=Path.home() / ".claude")
    ap.add_argument("--config", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--commit", action="store_true", help="promote the pending report to the baseline (after delivery)")
    ap.add_argument("--plan", action="store_true", help="print the lifecycle cycle's moves and deletions; change nothing")
    ap.add_argument("--apply", action="store_true", help="carry out the lifecycle cycle's moves and deletions")
    args = ap.parse_args(argv)
    cfg = load_config(args.config or config_path())
    out = args.out or args.root / "state" / "projects-sweep.json"
    if args.commit:
        commit_pending(out)
        return 0
    if args.plan or args.apply:
        actions = plan(args.root, fleet_docs_dir(), cfg)
        failures = []
        if args.apply:
            failures = commit_moves(fleet_docs_dir(), apply(actions))
        sys.stdout.write(json.dumps({"applied": args.apply, "failures": failures, "actions": actions}, indent=1) + "\n")
        return 1 if failures else 0
    report = sweep(args.root, cfg, previous_ids(out))
    store_pending(out, report)
    if args.json:
        sys.stdout.write(json.dumps(report) + "\n")
    else:
        print(f"projects-sweep (dry-run): {report['counts']} {report['totalBytes']} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
