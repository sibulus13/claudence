"""Tests for scripts/projects_sweep.py: dry-run candidates only, and the dirs that must never be candidates.

    python -m pytest ~/.claude/tests/test_projects_sweep.py -q
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import projects_sweep as ps  # noqa: E402
from upkeep_config import DEFAULTS  # noqa: E402

OLD = time.time() - 30 * 86400


def mk(projects: Path, name: str, files: dict[str, str] | None = None, age: float = OLD) -> Path:
    d = projects / name
    d.mkdir(parents=True)
    for rel, text in (files or {}).items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(text, encoding="utf-8")
    os.utime(d, (age, age))
    return d


@pytest.fixture
def world(tmp_path: Path):
    root = tmp_path / "claude"
    projects = root / "projects"
    projects.mkdir(parents=True)
    return root, projects, {**DEFAULTS, "repoRoot": None}


def reasons(report: dict) -> dict[str, str]:
    return {Path(c["path"]).name: c["reason"] for c in report["candidates"]}


def test_old_empty_dir_is_a_candidate_but_a_fresh_empty_dir_and_a_dir_with_files_are_not(world):
    root, projects, cfg = world
    mk(projects, "C--empty-old")
    mk(projects, "C--empty-new", age=time.time())
    mk(projects, "C--has-session", {"abc.jsonl": "{}"})
    assert reasons(ps.sweep(root, cfg)) == {"C--empty-old": "empty"}


def test_temp_clutter_dirs_are_candidates_only_when_old(world):
    root, projects, cfg = world
    mk(projects, "C--Users-Michael-AppData-Local-Temp-remember-summarizer-cwd-1", {"s.jsonl": "{}"})
    mk(projects, "C--Users-Michael-AppData-Local-Temp-remember-summarizer-cwd-2", {"s.jsonl": "{}"}, age=time.time())
    assert reasons(ps.sweep(root, cfg)) == {"C--Users-Michael-AppData-Local-Temp-remember-summarizer-cwd-1": "temp"}


def test_a_dir_holding_memory_notes_is_never_a_candidate(world):
    root, projects, cfg = world
    mk(projects, "C--Users-Michael-AppData-Local-Temp-remember-summarizer-cwd-9", {"memory/MEMORY.md": "- n"})
    mk(projects, "D--repo-App--git-foreman-worktrees-x1", {"memory/note.md": "n"})
    assert ps.sweep(root, cfg)["candidates"] == []


def test_worktree_dir_is_orphaned_only_when_its_worktree_is_gone(world, tmp_path: Path):
    root, projects, cfg = world
    tree = tmp_path / "repos"
    live = tree / "Theme" / "app" / ".git" / "foreman-worktrees" / "wt1"
    live.mkdir(parents=True)
    cfg = {**cfg, "repoRoot": str(tree)}
    enc = ps.encode_cwd
    mk(projects, enc(live), {"s.jsonl": "{}"})
    gone = tree / "Theme" / "app" / ".git" / "foreman-worktrees" / "wt2"
    mk(projects, enc(gone), {"s.jsonl": "{}"})
    assert reasons(ps.sweep(root, cfg)) == {enc(gone): "orphaned-worktree"}


def test_encode_cwd_matches_claude_code_project_dir_naming():
    assert ps.encode_cwd(Path("D:/repo/Assistant/cortex/.git/foreman-worktrees/x")) == \
        "D--repo-Assistant-cortex--git-foreman-worktrees-x"


def test_report_lists_categories_and_new_findings_only_when_a_category_first_appears(world):
    root, projects, cfg = world
    mk(projects, "C--empty-old")
    first = ps.sweep(root, cfg)
    assert [f["id"] for f in first["newFindings"]] == ["projects-sweep:empty"]
    again = ps.sweep(root, cfg, previous_categories={"empty"})
    assert again["newFindings"] == []


def test_cli_is_dry_run_it_deletes_nothing_and_writes_the_report(world):
    root, projects, cfg = world
    d = mk(projects, "C--empty-old")
    out = subprocess.run([sys.executable, str(Path(ps.__file__)), "--root", str(root), "--json"],
                         capture_output=True, text=True, check=True).stdout
    report = json.loads(out)
    assert report["dryRun"] is True and len(report["candidates"]) == 1
    assert d.exists()
    assert (root / "state" / "projects-sweep.json").exists()
