"""Tests for the context lifecycle: catalogue lint, read tracking, and the archive-then-delete sweep.

    python -m pytest ~/.claude/tests/test_context_lifecycle.py -q
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import context_reads as cr  # noqa: E402
import harness_lint as hl  # noqa: E402
import projects_sweep as ps  # noqa: E402
from upkeep_config import DEFAULTS  # noqa: E402

DAY = 86400
NOW = time.time()


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")


def transcript(root: Path, calls: list[tuple[float, dict]], name: str = "s.jsonl") -> None:
    d = root / "projects" / "D--repo"
    d.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"type": "assistant", "timestamp": iso(t),
                         "message": {"content": [{"type": "tool_use", "name": "Read", "input": inp}]}})
             for t, inp in calls]
    (d / name).write_text("\n".join(lines) + "\nnot json\n", encoding="utf-8")


def aged(p: Path, days: float, text: str = "x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    os.utime(p, (NOW - days * DAY, NOW - days * DAY))
    return p


def setup_memory(root: Path) -> tuple[Path, Path, Path]:
    mem = root / "projects" / "D--repo" / "memory"
    stale = aged(mem / "stale_note.md", 100)
    fresh = aged(mem / "fresh_note.md", 100)
    (mem / "MEMORY.md").write_text("# Index\n- [Stale](stale_note.md) - old\n- [Fresh](fresh_note.md) - read\n",
                                   encoding="utf-8")
    return mem, stale, fresh


def cfg() -> dict:
    return json.loads(json.dumps(DEFAULTS))


def test_context_lifecycle_AC_1_unclassified_and_unowned_docs_are_named(tmp_path):
    """context-lifecycle/AC-1"""
    fleet = tmp_path / "docs"
    aged(fleet / "reports" / "2026-09-01-old.md", 1)
    aged(fleet / "LEDGER.md", 1)
    aged(fleet / "NEXT_SESSION.md", 1)
    aged(fleet / "loose.md", 1)
    aged(fleet / "TASTE.md", 1, "---\nlifecycle: live\n---\n# Taste\n")
    (fleet / "lifecycle.json").write_text(json.dumps({"rules": [
        {"glob": "reports/*.md", "lifecycle": "snapshot"},
        {"glob": "LEDGER.md", "lifecycle": "live", "updatedBy": "/ledger at session end"},
        {"glob": "NEXT_SESSION.md", "lifecycle": "live"},
    ]}), encoding="utf-8")
    named = {Path(f["path"]).name for f in hl.check_lifecycle(fleet)}
    assert named == {"loose.md", "NEXT_SESSION.md", "TASTE.md"}


def test_context_lifecycle_AC_2_a_path_in_any_tool_call_is_a_read(tmp_path):
    """context-lifecycle/AC-2"""
    note = tmp_path / "notes" / "a.md"
    other = tmp_path / "notes" / "b.md"
    seen = NOW - 3 * DAY
    windows = str(note).replace("/", "\\")
    transcript(tmp_path, [(NOW - 40 * DAY, {"command": "echo start"}),
                          (seen, {"command": f"grep -n x {windows}"})])
    reads, coverage = cr.last_reads(tmp_path / "projects", [note, other])
    assert abs(reads[cr.key(note)] - seen) < 1
    assert cr.key(other) not in reads
    assert abs(coverage - (NOW - 40 * DAY)) < 1


def test_context_lifecycle_AC_3_unread_memory_is_archived_then_deleted(tmp_path):
    """context-lifecycle/AC-3"""
    mem, stale, fresh = setup_memory(tmp_path)
    transcript(tmp_path, [(NOW - 120 * DAY, {"command": "echo start"}), (NOW - 5 * DAY, {"file_path": str(fresh)})])
    ps.apply(ps.plan(tmp_path, tmp_path / "docs", cfg(), now=NOW), now=NOW)
    assert (mem / "archive" / "stale_note.md").exists() and fresh.exists()
    assert "stale_note.md" not in (mem / "MEMORY.md").read_text(encoding="utf-8")
    later = NOW + 91 * DAY
    ps.apply(ps.plan(tmp_path, tmp_path / "docs", cfg(), now=later), now=later)
    assert not (mem / "archive" / "stale_note.md").exists()


def test_context_lifecycle_AC_4_reports_are_archived_never_deleted_and_scratch_cycles(tmp_path):
    """context-lifecycle/AC-4"""
    fleet = tmp_path / "docs"
    old = aged(fleet / "reports" / "2026-08-03-old.md", 100)
    read_scratch = aged(fleet / "scratch" / "kept.md", 100)
    unread_scratch = aged(fleet / "scratch" / "gone.md", 100)
    (fleet / "lifecycle.json").write_text(json.dumps({"rules": [
        {"glob": "reports/*.md", "lifecycle": "snapshot"}, {"glob": "scratch/*.md", "lifecycle": "scratch"}]}),
        encoding="utf-8")
    transcript(tmp_path, [(NOW - 120 * DAY, {"command": "echo start"}),
                          (NOW - 7 * DAY, {"file_path": str(read_scratch)})])
    ps.apply(ps.plan(tmp_path, fleet, cfg(), now=NOW), now=NOW)
    archived_report = fleet / "reports" / "archive" / "2026-08" / old.name
    assert archived_report.exists() and read_scratch.exists() and not unread_scratch.exists()
    later = NOW + 400 * DAY
    ps.apply(ps.plan(tmp_path, fleet, cfg(), now=later), now=later)
    assert archived_report.exists()
    assert not any((fleet / "archive").rglob("gone.md"))


def test_context_lifecycle_AC_5_a_dry_run_lists_moves_and_changes_nothing(tmp_path):
    """context-lifecycle/AC-5"""
    mem, stale, _ = setup_memory(tmp_path)
    transcript(tmp_path, [(NOW - 120 * DAY, {"command": "echo start"})])
    before = sorted(p.as_posix() for p in tmp_path.rglob("*"))
    actions = ps.plan(tmp_path, tmp_path / "docs", cfg(), now=NOW)
    assert any(a["path"] == stale.as_posix() and a["action"] == "archive" for a in actions)
    assert sorted(p.as_posix() for p in tmp_path.rglob("*")) == before


def test_context_lifecycle_AC_4_a_dated_doc_at_the_fleet_root_is_never_deleted(tmp_path):
    """context-lifecycle/AC-4 (review finding 1: root snapshots shared the scratch archive and were deleted)"""
    fleet = tmp_path / "docs"
    plan_doc = aged(fleet / "PLAN_2026-08-03.md", 100)
    aged(fleet / "scratch" / "gone.md", 100)
    (fleet / "lifecycle.json").write_text(json.dumps({"rules": [
        {"glob": "*_20??-??-??.md", "lifecycle": "snapshot"}, {"glob": "scratch/*.md", "lifecycle": "scratch"}]}),
        encoding="utf-8")
    transcript(tmp_path, [(NOW - 120 * DAY, {"command": "echo start"})])
    ps.apply(ps.plan(tmp_path, fleet, cfg(), now=NOW), now=NOW)
    later = NOW + 400 * DAY
    ps.apply(ps.plan(tmp_path, fleet, cfg(), now=later), now=later)
    assert [q.name for q in fleet.rglob(plan_doc.name)] == [plan_doc.name]
    assert not any(fleet.rglob("gone.md"))


def test_context_lifecycle_AC_2_relative_bash_and_escaped_spellings_count_as_reads(tmp_path):
    """context-lifecycle/AC-2 (review finding 3: only the full absolute spelling counted)"""
    fleet = tmp_path / "docs"
    rel, bash, escaped, tilde = (fleet / "reports" / f"{n}.md" for n in ("rel", "bash", "esc", "tilde"))
    win = str(escaped).replace("/", "\\")
    drive, rest = str(bash).replace("\\", "/").split(":", 1)
    seen = NOW - 2 * DAY
    transcript(tmp_path, [(NOW - 120 * DAY, {"command": "echo start"}),
                          (seen, {"command": "cat reports/rel.md"}),
                          (seen, {"command": f"head /{drive.lower()}{rest}"}),
                          (seen, {"command": win.replace("\\", "\\\\")}),
                          (seen, {"file_path": "~/docs/reports/tilde.md"})])
    reads, _ = cr.last_reads(tmp_path / "projects", [rel, bash, escaped, tilde])
    assert {k.rsplit("/", 1)[-1] for k in reads} == {"rel.md", "bash.md", "esc.md", "tilde.md"}


def git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env).stdout


def test_context_lifecycle_AC_4_moves_are_committed_except_ignored_and_others_work_is_left(tmp_path):
    """context-lifecycle/AC-4 (review finding 2: an ignored path made the commit fail silently)"""
    fleet = tmp_path / "docs"
    fleet.mkdir()
    git(fleet, "init", "-q")
    (fleet / ".gitignore").write_text("backup_*/\n", encoding="utf-8")
    tracked = aged(fleet / "research_notes" / "n.md", 100)
    aged(fleet / "backup_2026-10-25" / "b.md", 100)
    other = aged(fleet / "LEDGER.md", 1)
    (fleet / "lifecycle.json").write_text(json.dumps({"rules": [
        {"glob": "research_notes/*.md", "lifecycle": "scratch"}, {"glob": "backup_2026-10-25/*", "lifecycle": "scratch"},
        {"glob": "LEDGER.md", "lifecycle": "live", "updatedBy": "x"}]}), encoding="utf-8")
    git(fleet, "add", "-A")
    git(fleet, "commit", "-q", "-m", "init")
    other.write_text("another session's edit", encoding="utf-8")
    transcript(tmp_path, [(NOW - 120 * DAY, {"command": "echo start"})])
    actions = ps.apply(ps.plan(tmp_path, fleet, cfg(), now=NOW), now=NOW)
    assert ps.commit_moves(fleet, actions) == []
    assert git(fleet, "status", "--porcelain").split() == ["M", "LEDGER.md"]
    assert not tracked.exists()

