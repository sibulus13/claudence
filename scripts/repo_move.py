"""Move folders inside D:/repo, keeping Claude Code history attached, with an undo log.

    python ~/.claude/scripts/repo_move.py --plan moves.json [--dry-run]
    python ~/.claude/scripts/repo_move.py --undo            # reverses the last batch

moves.json: [{"from": "AI/bifrost", "to": "_Archive/AI/bifrost", "why": "superseded by Foreman"}, ...]
Per move: rename the folder (same volume, so instant and history-preserving), rename the Claude Code
history folders keyed by the old path (~/.claude/projects/D--repo-<slug>...), then list the pins that
still name the old path (from path_pins.json; rerun path_pins.py first). It never edits a pin itself:
scheduled tasks and registries are rewritten by the caller in the same step. Log: MOVES.jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("D:/repo")
HISTORY = Path.home() / ".claude" / "projects"
FLEET = Path.home() / ".claude" / "docs" / "fleet"
LOG = FLEET / "MOVES.jsonl"


def slug(rel: str) -> str:
    """Claude Code's history-folder name for D:/repo/<rel>: every non-alphanumeric becomes '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(ROOT / rel))


def history_dirs(rel: str) -> list[Path]:
    s = slug(rel)
    return [p for p in HISTORY.iterdir() if p.is_dir() and (p.name == s or p.name.startswith(s + "-"))]


def pins_for(rel: str) -> list[str]:
    inv = FLEET / "path_pins.json"
    if not inv.is_file():
        return ["path_pins.json missing: run path_pins.py"]
    out = []
    for p in json.loads(inv.read_text(encoding="utf-8"))["projects"]:
        if p["project"] == rel or p["project"].startswith(rel + "/"):
            out += [f"{k}: {v}" for k in ("other_code", "machine", "tasks") for v in p[k]]
    return out


def move(src: str, dst: str, dry: bool) -> dict:
    a, b = ROOT / src, ROOT / dst
    if not a.exists():
        return {"from": src, "to": dst, "status": "missing"}
    if b.exists():
        return {"from": src, "to": dst, "status": "target exists"}
    hist = [(h, HISTORY / (slug(dst) + h.name[len(slug(src)):])) for h in history_dirs(src)]
    rec = {"from": src, "to": dst, "history": [[h.name, n.name] for h, n in hist], "open_pins": pins_for(src)}
    if dry:
        return rec | {"status": "dry-run"}
    b.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(a, b)
    except OSError as e:                       # a file held open (dev server, editor) blocks the rename
        return rec | {"status": f"failed: {e}"}
    for h, n in hist:
        os.rename(h, n)
    return rec | {"status": "moved"}


def undo() -> int:
    batches = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    last = batches[-1]
    for m in reversed([m for m in last["moves"] if m["status"] == "moved"]):
        r = move(m["to"], m["from"], dry=False)
        print(r["status"], m["to"], "->", m["from"])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--undo", action="store_true")
    a = ap.parse_args()
    if a.undo:
        return undo()
    if not a.plan:
        sys.exit("--plan or --undo is required")
    plan = json.loads(a.plan.read_text(encoding="utf-8"))
    results = []
    for i, m in enumerate(plan, 1):
        r = move(m["from"], m["to"], a.dry_run) | {"why": m.get("why", "")}
        results.append(r)
        print(f"[{i}/{len(plan)}] {r['status']:9} {m['from']} -> {m['to']}  history:{len(r.get('history', []))}  open pins:{len(r.get('open_pins', []))}", flush=True)
        for pin in r.get("open_pins", []):
            print("      pin", pin)
    if not a.dry_run:
        with LOG.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "moves": results}) + "\n")
    return 0 if all(r["status"] in ("moved", "dry-run") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
