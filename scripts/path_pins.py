"""Path-pin inventory: everything that would break if a repo under D:/repo moved.

    python ~/.claude/scripts/path_pins.py [--root D:/repo] [--out ~/.claude/docs/fleet]

Read-only. For every repo it finds who references that repo by absolute path:
  - code/config files in any repo (the move breaks them),
  - docs (links go stale, nothing crashes),
  - machine config outside the repos: scheduled tasks, ~/.foreman/repos.json, ~/.claude config,
    memory and scripts,
  - Claude Code session history, which is keyed by the folder path (~/.claude/projects/D--repo-...).
It also records each repo's GitHub remote and Vercel link, which a local move does not change.
Writes path_pins.json and PATH_PINS_<date>.md next to the fleet snapshot.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

from fleet_status import SKIP_DIRS, find_repos, git, scheduled_tasks

PIN = re.compile(r"[dD]:(?:\\\\|\\|/)repo(?:\\\\|\\|/)([^\"'`\s<>|*?\])(,;]+(?: [0-9][^\"'`\s<>|*?\])(,;]*)?)")
CODE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".json", ".ps1", ".psm1", ".bat", ".cmd", ".vbs", ".lua",
            ".toml", ".yaml", ".yml", ".ini", ".cfg", ".env", ".sh", ".xml"}
DOC_EXT = {".md", ".txt", ".html"}
MAX_BYTES = 1_000_000
EXTRA_SKIP = SKIP_DIRS | {"data", "logs", "out", "output", "coverage", ".pytest_cache", ".turbo", "target"}
HOME = Path.home()
MACHINE_CONFIG = [HOME / ".foreman" / "repos.json", HOME / ".foreman" / "config.json", HOME / ".claude" / "settings.json",
                  HOME / ".claude" / "CLAUDE.md", HOME / ".claude" / "terminal.lua", HOME / ".wezterm.lua"]
MACHINE_DIRS = [HOME / ".claude" / "scripts", HOME / ".claude" / "workspaces", HOME / ".claude" / "hooks",
                HOME / ".claude" / "skills", HOME / ".claude" / "workflows", HOME / ".claude" / "agents",
                HOME / ".claude" / "projects" / "D--repo" / "memory", HOME / ".telefi"]


def text_files(base: Path, stop_at: frozenset[Path] = frozenset()):
    """Text files under base, pruning build/vendor dirs and nested repos (scanned on their own turn)."""
    for dirpath, dirnames, filenames in os.walk(base):
        here = Path(dirpath)
        dirnames[:] = [d for d in dirnames if d not in EXTRA_SKIP and not d.startswith(".git") and here / d not in stop_at]
        for name in filenames:
            f = here / name
            if (f.suffix.lower() in CODE_EXT | DOC_EXT or name == "CLAUDE.md") and f.stat().st_size <= MAX_BYTES:
                yield f


def refs_in(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [m.group(1).replace("\\\\", "/").replace("\\", "/").rstrip("/.") for m in PIN.finditer(text)]


def owner(ref: str, roots: list[str]) -> str | None:
    """The repo a referenced path points into (longest matching root)."""
    low = ref.lower()
    hits = [r for r in roots if low == r.lower() or low.startswith(r.lower() + "/")]
    return max(hits, key=len) if hits else None


def history_dir_name(rel: str) -> str:
    return "D--repo-" + re.sub(r"[^A-Za-z0-9]", "-", rel)


def inventory(root: Path) -> dict:
    repos = find_repos(root)
    roots = [r.relative_to(root).as_posix() for r in repos]
    pins: dict[str, dict] = {r: {"self_code": set(), "other_code": set(), "docs": set(), "machine": set(), "tasks": set()} for r in roots}

    def record(src_label: str, src_repo: str | None, refs: list[str], is_doc: bool) -> None:
        for ref in refs:
            target = owner(ref, roots)
            if not target:
                continue
            kind = "docs" if is_doc else ("self_code" if src_repo == target else "other_code")
            if src_repo is None:
                kind = "machine"
            pins[target][kind].add(src_label)

    for i, repo in enumerate(repos, 1):
        rel = roots[i - 1]
        print(f"[{i}/{len(repos)}] {rel}", flush=True)
        nested = frozenset(r for r in repos if r != repo and repo in r.parents)
        for f in text_files(repo, nested):
            is_doc = f.suffix.lower() in DOC_EXT or f.name == "CLAUDE.md"
            record(f"{rel}/{f.relative_to(repo).as_posix()}", rel, refs_in(f), is_doc)

    machine_files = [p for p in MACHINE_CONFIG if p.is_file()]
    for d in MACHINE_DIRS:
        if d.is_dir():
            machine_files += list(text_files(d))
    for f in machine_files:
        record(str(f).replace("\\", "/").replace(str(HOME).replace("\\", "/"), "~"), None, refs_in(f), False)
    for t in scheduled_tasks():
        for ref in [m.group(1).replace("\\", "/") for m in PIN.finditer(t.get("args") or "")]:
            target = owner(ref, roots)
            if target:
                pins[target]["tasks"].add(t["name"])

    history = {p.name for p in (HOME / ".claude" / "projects").iterdir() if p.is_dir()}
    out = []
    for rel in roots:
        repo = root / rel
        hist = history_dir_name(rel)
        vercel = repo / ".vercel" / "project.json"
        p = pins[rel]
        out.append({"project": rel, "remote": git(repo, "remote", "get-url", "origin") or None,
                    "vercel_linked": vercel.is_file(), "claude_history": hist in history,
                    "breaks_on_move": len(p["other_code"]) + len(p["machine"]) + len(p["tasks"]),
                    **{k: sorted(v) for k, v in p.items()}})
    return {"generated": date.today().isoformat(), "root": str(root), "projects": out}


def to_markdown(inv: dict) -> str:
    rows = ["| project | breaks on move | own code hardcodes itself | other repos' code | machine config | tasks | docs | history | remote |",
            "|---|---|---|---|---|---|---|---|---|"]
    for p in sorted(inv["projects"], key=lambda p: (-p["breaks_on_move"], -len(p["self_code"]), p["project"])):
        rows.append(f"| {p['project']} | {p['breaks_on_move']} | {len(p['self_code'])} | {len(p['other_code'])} | "
                    f"{len(p['machine'])} | {', '.join(p['tasks']) or '-'} | {len(p['docs'])} | "
                    f"{'yes' if p['claude_history'] else '-'} | {(p['remote'] or '-').replace('https://github.com/', '')} |")
    return (f"# Path pins {inv['generated']}\n\nGenerated by `~/.claude/scripts/path_pins.py` (read-only). "
            "Detail per file: `path_pins.json`.\n\n" + "\n".join(rows) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="D:/repo")
    ap.add_argument("--out", default=str(HOME / ".claude" / "docs" / "fleet"))
    a = ap.parse_args()
    inv = inventory(Path(a.root))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "path_pins.json").write_text(json.dumps(inv, indent=2), encoding="utf-8")
    (out / f"PATH_PINS_{inv['generated']}.md").write_text(to_markdown(inv), encoding="utf-8", newline="\n")
    print(f"wrote {out / 'path_pins.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
