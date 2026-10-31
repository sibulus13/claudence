"""Install the fleet git hooks (spec gate + portable file names) into every repo under a root.

    python install_fleet_hooks.py [D:/repo] [--no-push] [--dry-run]

Per repo: copy git-hooks/fleet-pre-commit-config.yaml to .pre-commit-config.yaml (if absent), commit only that file,
run `pre-commit install`, push unless --no-push. Repos with their own core.hooksPath are skipped and reported: the
pre-commit framework refuses to install there, and those repos need the gate added to their own hooks.
Idempotent: a configured repo is only re-installed (no new commit). Spec: ~/.claude/docs/work/spec-gate/ AC-10.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "git-hooks" / "fleet-pre-commit-config.yaml"
TARGET = ".pre-commit-config.yaml"
SKIP_DIRS = {"_Archive", "node_modules"}
REPO_DEPTH = 3  # D:/repo/<Theme>/<project> and D:/repo/<Theme>/<group>/<project>
TIMEOUT_S = 120


def run(*cmd: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT_S)


def repos(root: Path) -> list[Path]:
    found, frontier = [], [(root, 0)]
    while frontier:
        d, depth = frontier.pop()
        if (d / ".git").is_dir():
            found.append(d)
            continue
        if depth < REPO_DEPTH:
            frontier += [(c, depth + 1) for c in d.iterdir() if c.is_dir() and c.name not in SKIP_DIRS
                         and not c.name.startswith(".")]
    return sorted(found)


def install(repo: Path, push: bool, dry: bool) -> str:
    if run("git", "config", "--local", "core.hooksPath", cwd=repo).stdout.strip():
        return "SKIP has its own core.hooksPath: add the spec gate to its hooks by hand"
    cfg = repo / TARGET
    committed = False
    if not cfg.exists():
        if dry:
            return "would add config, commit and install"
        cfg.write_text(CONFIG.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        run("git", "add", "--", TARGET, cwd=repo)
        c = run("git", "commit", "-q", "--no-verify", "-m", "chore: add fleet git hooks (spec gate, portable names)",
                "--", TARGET, cwd=repo)
        if c.returncode != 0:
            return f"FAIL commit: {c.stderr.strip()[:160]}"
        committed = True
    if dry:
        return "would re-install hooks"
    i = run(sys.executable, "-m", "pre_commit", "install", cwd=repo)
    if i.returncode != 0:
        return f"FAIL install: {(i.stderr or i.stdout).strip()[:160]}"
    if committed and push and run("git", "remote", cwd=repo).stdout.strip():
        p = run("git", "push", "-q", cwd=repo)
        if p.returncode != 0:
            return f"committed, PUSH FAILED: {p.stderr.strip()[:120]}"
    return "added and installed" if committed else "already configured, hooks installed"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", nargs="?", type=Path, default=Path("D:/repo"))
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    failed = 0
    for repo in repos(a.root):
        status = install(repo, push=not a.no_push, dry=a.dry_run)
        failed += status.startswith("FAIL")
        print(f"{repo.relative_to(a.root).as_posix()}: {status}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
