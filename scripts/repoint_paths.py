"""Rewrite absolute D:/repo paths after a move batch, in every slash style, and report per git repo.

    python ~/.claude/scripts/repoint_paths.py --map moves.json [--dry-run]

moves.json is the same file repo_move.py takes ([{"from": ..., "to": ...}]). Matches D:/repo/<from>,
D:\\repo\\<from> and the JSON-escaped D:\\\\repo\\\\<from> (any drive-letter case), only at a path
boundary. Scans D:/repo (skipping _Archive, node_modules, .git, build output, worktrees, logs) and
~/.claude, ~/.foreman, ~/.telefi, ~/.cortex config. Prints changed files grouped by git repo and
whether each was clean before, so the caller commits only files it alone touched.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path("D:/repo")
HOME = Path.home()
SKIP_DIRS = {"node_modules", ".git", ".next", ".next-gate", ".venv", "venv", "__pycache__", "_Archive",
             "worktrees", ".evidence-41", "dist", "build", ".turbo", "projects", "tool-results",
             "file-history", "shell-snapshots", "todos", "cache", "plugins", "logs", "tmp", "outbox"}
TEXT_EXT = {".md", ".json", ".yaml", ".yml", ".toml", ".py", ".ps1", ".psm1", ".cmd", ".bat", ".vbs",
            ".js", ".mjs", ".cjs", ".ts", ".tsx", ".lua", ".txt", ".cfg", ".ini", ".sh", ".env.example"}
MAX_BYTES = 2_000_000


def pattern(rel: str) -> re.Pattern:
    parts = rel.split("/")
    sep = r"(?:/|\\\\|\\)"
    body = sep.join(re.escape(p) for p in ["repo", *parts])
    return re.compile(r"([dD]:)(" + sep + r")" + body + r"(?![A-Za-z0-9_\-])")


def substitute(text: str, moves: list[dict]) -> str:
    for m in sorted(moves, key=lambda m: -len(m["from"])):   # longest first: Stock/Research 2026 before Stock
        rx = pattern(m["from"])

        def repl(mt: re.Match, to=m["to"]) -> str:
            s = mt.group(2)
            return mt.group(1) + s + s.join(["repo", *to.split("/")])
        text = rx.sub(repl, text)
    return text


def files(base: Path):
    for dp, dns, fns in os.walk(base):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            p = Path(dp) / fn
            if p.suffix.lower() in TEXT_EXT and not fn.endswith(".jsonl"):
                yield p


def roots() -> list[Path]:
    out = [ROOT, HOME / ".claude", HOME / ".foreman", HOME / ".telefi", HOME / ".cortex" / "config"]
    out += [d / "memory" for d in (HOME / ".claude" / "projects").glob("D--repo*") if (d / "memory").is_dir()]
    return [p for p in out if p.exists()]


def git_top(p: Path) -> str:
    r = subprocess.run(["git", "-C", str(p.parent), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else "(no git)"


def was_clean(top: str, p: Path) -> bool:
    if top == "(no git)":
        return True
    r = subprocess.run(["git", "-C", top, "status", "--porcelain", "--", str(p)], capture_output=True, text=True)
    return r.stdout.strip() == ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--exclude", action="append", default=[], help="skip paths containing this (forward slashes)")
    a = ap.parse_args()
    moves = json.loads(a.map.read_text(encoding="utf-8"))
    probe = re.compile(r"[dD]:(?:/|\\\\|\\)repo")
    seen: set[Path] = set()
    report: dict[str, list[str]] = {}
    for base in roots():
        for p in files(base):
            if p in seen or p.stat().st_size > MAX_BYTES or any(x in p.as_posix() for x in a.exclude):
                continue
            seen.add(p)
            try:
                raw = p.read_bytes()
                text = raw.decode("utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if not probe.search(text):
                continue
            new = substitute(text, moves)
            if new == text:
                continue
            top = git_top(p)
            clean = was_clean(top, p)
            if not a.dry_run:
                p.write_bytes(new.encode("utf-8"))
            report.setdefault(top, []).append(("" if clean else "DIRTY-BEFORE ") + str(p))
    for top, fs in sorted(report.items()):
        print(f"== {top} ({len(fs)})")
        for f in fs:
            print("  ", f)
    print(f"files changed: {sum(len(v) for v in report.values())}{' (dry run)' if a.dry_run else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
