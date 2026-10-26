"""Post-move repair for every folder in a repo_move.py plan: git worktree links and pnpm junctions.

    python ~/.claude/scripts/repair_worktrees.py --map moves.json

Both break on a move because they store ABSOLUTE paths: a linked worktree's gitdir pointer, and pnpm's
node_modules junctions on Windows. Run it right after repo_move.py, together with repoint_paths.py
and repoint_tasks.ps1 (incident 2026-10-25: Crucible's dashboard tsc gate failed after the move
because the hand-written finishing script skipped the pnpm relink).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

PNPM_SEARCH_DEPTH = 3
SKIP = {"node_modules", ".git", ".claude", ".venv", "_Archive"}


def repair_worktrees(root: str, old: str) -> str:
    out = subprocess.run(["git", "-C", root, "worktree", "list", "--porcelain"],
                         capture_output=True, text=True, timeout=60).stdout
    paths = [l[9:] for l in out.splitlines() if l.startswith("worktree ")]
    fixed = [root + p[len(old):] for p in paths if p.startswith(old + "/") and Path(root + p[len(old):]).exists()]
    if fixed:
        subprocess.run(["git", "-C", root, "worktree", "repair", *fixed], capture_output=True, text=True, timeout=120)
    left = subprocess.run(["git", "-C", root, "worktree", "list"], capture_output=True, text=True,
                          timeout=60).stdout.count("prunable")
    return f"worktrees repaired {len(fixed)}, still prunable {left}"


def pnpm_dirs(root: Path) -> list[Path]:
    found = []
    for dp, dns, fns in os.walk(root):
        depth = len(Path(dp).relative_to(root).parts)
        dns[:] = [d for d in dns if d not in SKIP and depth < PNPM_SEARCH_DEPTH]
        if "pnpm-lock.yaml" in fns and (Path(dp) / "node_modules").is_dir():
            found.append(Path(dp))
    return found


def relink(d: Path) -> str:
    r = subprocess.run("pnpm install --offline --frozen-lockfile --force", cwd=d, shell=True,
                       capture_output=True, text=True, timeout=1800)
    return f"pnpm relink {d.name}: {'ok' if r.returncode == 0 else 'FAILED ' + r.stderr.strip()[-200:]}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", type=Path, required=True)
    moves = json.loads(ap.parse_args().map.read_text(encoding="utf-8"))
    for m in moves:
        root = Path("D:/repo") / m["to"]
        if not root.is_dir():
            continue
        notes = []
        if (root / ".git").exists():
            notes.append(repair_worktrees(root.as_posix(), f"D:/repo/{m['from']}"))
        notes += [relink(d) for d in pnpm_dirs(root)]
        print(f"{m['to']}: " + ("; ".join(notes) or "nothing to repair"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
