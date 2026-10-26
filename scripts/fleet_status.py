"""Fleet progress checker: one snapshot of every project under D:/repo.

    python ~/.claude/scripts/fleet_status.py [--root D:/repo] [--out ~/.claude/docs/fleet]

Writes fleet_status.json (machine-readable) and SNAPSHOT_<date>.md (one row per project), and prints
a one-line-per-project summary. Read-only: it runs `git` queries and lists scheduled tasks, nothing
else. Activity classes: active (commit in the last 14 days), warm (90), cold (365), stale (older),
no-git (a folder with no repository).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

GIT_TIMEOUT_S = 20
TASK_TIMEOUT_S = 60
SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "__pycache__", ".next", "dist", "build", "worktrees"}
STATE_DOCS = ("docs/STATE.md", "STATE.md", "workflow_state.md", "todo.md", "docs/ROADMAP.md", "ROADMAP.md",
              "docs/KNOWLEDGE.md", "README.md")
CLASSES = ((14, "active"), (90, "warm"), (365, "cold"))
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def git(repo: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=GIT_TIMEOUT_S,
                           encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def find_repos(root: Path, depth: int = 3) -> list[Path]:
    """Directories whose `.git` is a directory (real repos, not worktrees), up to `depth` below root."""
    out, frontier = [], [root]
    for _ in range(depth):
        nxt = []
        for d in frontier:
            for c in sorted(p for p in d.iterdir() if p.is_dir() and p.name not in SKIP_DIRS and not p.name.startswith(".")):
                if (c / ".git").is_dir():
                    out.append(c)
                nxt.append(c)                     # keep going: repos nest (Stock/ holds Research 2026/)
        frontier = nxt
    return out


def classify(days: int | None) -> str:
    if days is None:
        return "empty"
    return next((name for limit, name in CLASSES if days <= limit), "stale")


def state_doc(repo: Path) -> dict | None:
    for rel in STATE_DOCS:
        p = repo / rel
        if p.is_file():
            lines = [l.strip("#*> -").strip() for l in p.read_text(encoding="utf-8", errors="replace").splitlines()]
            first = next((l for l in lines if l and not l.startswith(("```", "|", "<", "!["))), "")
            return {"path": rel, "modified": datetime.fromtimestamp(p.stat().st_mtime).date().isoformat(), "first_line": first[:160]}
    return None


def tier(repo: Path) -> str | None:
    p = repo / "CLAUDE.md"
    m = re.search(r"deploymentTier:?\**\s*`?([a-z-]+)", p.read_text(encoding="utf-8", errors="replace")) if p.is_file() else None
    return m.group(1) if m else None


def scheduled_tasks() -> list[dict]:
    """Every enabled Windows scheduled task whose action points into D:\\repo."""
    ps = ("Get-ScheduledTask | Where-Object { $_.State -ne 'Disabled' } | ForEach-Object { $i = $_ | Get-ScheduledTaskInfo; "
          "[pscustomobject]@{name=$_.TaskName; args=(($_.Actions | ForEach-Object { \"$($_.Execute) $($_.Arguments) $($_.WorkingDirectory)\" }) -join ' '); "
          "result=$i.LastTaskResult; last=$i.LastRunTime.ToString('yyyy-MM-dd HH:mm')} } | ConvertTo-Json -Compress")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                           timeout=TASK_TIMEOUT_S, creationflags=NO_WINDOW)
        rows = json.loads(r.stdout or "[]")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return []
    rows = rows if isinstance(rows, list) else [rows]
    return [t for t in rows if "repo" in (t.get("args") or "").lower()]


def snapshot(root: Path) -> dict:
    today = date.today()
    tasks = scheduled_tasks()
    projects = []
    for repo in find_repos(root):
        last = git(repo, "log", "-1", "--format=%cs|%s")
        last_date, _, subject = last.partition("|")
        days = (today - date.fromisoformat(last_date)).days if last_date else None
        counts = {f"commits_{n}d": int(git(repo, "rev-list", "--count", f"--since={n}.days", "HEAD") or 0) for n in (30, 90, 365)}
        rel = repo.relative_to(root).as_posix()
        projects.append({
            "project": rel, "category": rel.split("/")[0], "last_commit": last_date or None, "last_subject": subject[:100],
            "days_since": days, "activity": classify(days), **counts,
            "branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
            "dirty_files": len([l for l in git(repo, "status", "--porcelain").splitlines() if l.strip()]),
            "remote": git(repo, "remote", "get-url", "origin") or None,
            "tier": tier(repo), "state_doc": state_doc(repo),
            "tasks": [t["name"] for t in tasks if str(repo).lower().replace("/", "\\") in (t.get("args") or "").lower().replace("/", "\\")],
        })
    git_roots = {p["project"] for p in projects}
    loose = [d.relative_to(root).as_posix() for d in sorted(root.iterdir()) if d.is_dir() and not d.name.startswith(".")
             and not any(g == d.name or g.startswith(d.name + "/") for g in git_roots)]
    return {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "root": str(root),
            "projects": projects, "no_git": loose, "tasks": tasks}


def to_markdown(snap: dict) -> str:
    rows = ["| project | activity | last commit | 30d / 90d / 365d | dirty | tier | tasks | state doc |",
            "|---|---|---|---|---|---|---|---|"]
    order = {"active": 0, "warm": 1, "cold": 2, "stale": 3, "empty": 4}
    for p in sorted(snap["projects"], key=lambda p: (order[p["activity"]], p["days_since"] or 99999)):
        sd = p["state_doc"]
        rows.append(f"| {p['project']} | {p['activity']} | {p['last_commit'] or '-'} ({p['days_since'] if p['days_since'] is not None else '-'}d) | "
                    f"{p['commits_30d']} / {p['commits_90d']} / {p['commits_365d']} | {p['dirty_files']} | {p['tier'] or '-'} | "
                    f"{', '.join(p['tasks']) or '-'} | {(sd['path'] + ' ' + sd['modified']) if sd else 'none'} |")
    return (f"# Fleet snapshot {snap['generated'][:10]}\n\nGenerated by `~/.claude/scripts/fleet_status.py` "
            f"(read-only). Folders without git: {', '.join(snap['no_git']) or 'none'}.\n\n" + "\n".join(rows) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="D:/repo")
    ap.add_argument("--out", default=str(Path.home() / ".claude" / "docs" / "fleet"))
    a = ap.parse_args()
    snap = snapshot(Path(a.root))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "fleet_status.json").write_text(json.dumps(snap, indent=2), encoding="utf-8")
    (out / f"SNAPSHOT_{snap['generated'][:10]}.md").write_text(to_markdown(snap), encoding="utf-8", newline="\n")
    for p in snap["projects"]:
        print(f"{p['activity']:6} {p['project']:40} last {p['last_commit']} ({p['days_since']}d) 90d:{p['commits_90d']} dirty:{p['dirty_files']}")
    print(f"no git: {snap['no_git']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
