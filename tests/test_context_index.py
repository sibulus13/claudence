"""Tests for the context index: lookup across nested area files, its lint check, and the researcher wiring.

    python -m pytest ~/.claude/tests/test_context_index.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME / "scripts"))
import context_index as ci  # noqa: E402
import harness_lint as hl  # noqa: E402

HEADER = "| Topic | Where | Kind | Summary | Verified |\n|---|---|---|---|---|\n"


def fleet(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    (docs / "context").mkdir(parents=True)
    real = docs / "spec.md"
    real.write_text("# spec\n", encoding="utf-8")
    (docs / "CONTEXT_INDEX.md").write_text(
        "# Context index\n\n| Area | File | Covers |\n|---|---|---|\n"
        "| Orchestration | [context/orchestration.md](context/orchestration.md) | agents, loops |\n", encoding="utf-8")
    (docs / "context" / "orchestration.md").write_text(
        "# Orchestration\n\n" + HEADER
        + f"| Shared runner Weaver | `{real.as_posix()}:1` | spec | the runner for Foreman and Cortex | 2026-11-07 |\n"
        + "| Runner detail | [runner.md](runner.md) | index | Weaver stages | 2026-11-07 |\n"
        + f"| Notifications | `{real.as_posix()}:1` | spec | TeleFi | 2026-11-07 |\n", encoding="utf-8")
    (docs / "context" / "runner.md").write_text(
        "# Runner\n\n" + HEADER + f"| Weaver heartbeat | `{real.as_posix()}:56` | spec | runner hang check | 2026-11-07 |\n",
        encoding="utf-8")
    return docs


def test_context_index_AC_1_lookup_finds_entries_across_nested_area_files(tmp_path: Path):
    """context-index/AC-1"""
    hits = ci.lookup(fleet(tmp_path), ["weaver", "runner"])
    assert sorted(h["topic"] for h in hits) == ["Runner detail", "Shared runner Weaver", "Weaver heartbeat"]
    assert {h["area"] for h in hits} == {"orchestration.md", "runner.md"}


def test_context_index_AC_2_broken_paths_orphan_areas_and_undated_entries_are_named(tmp_path: Path):
    """context-index/AC-2"""
    docs = fleet(tmp_path)
    (docs / "context" / "orphan.md").write_text("# Orphan\n\n" + HEADER, encoding="utf-8")
    with (docs / "context" / "runner.md").open("a", encoding="utf-8") as fh:
        fh.write(f"| Gone | `{(tmp_path / 'nope.md').as_posix()}:3` | code | moved | 2026-11-07 |\n")
        fh.write(f"| Undated | `{(docs / 'spec.md').as_posix()}` | code | x |  |\n")
    details = " ".join(f["detail"] + " " + f["path"] for f in ci.check(docs))
    assert "nope.md" in details and "orphan.md" in details and "Undated" in details
    assert len(ci.check(fleet(tmp_path / "clean"))) == 0


def test_context_index_AC_3_the_harness_lint_reports_context_index_findings(tmp_path: Path):
    """context-index/AC-3"""
    docs = fleet(tmp_path)
    (docs / "context" / "orphan.md").write_text("# Orphan\n\n" + HEADER, encoding="utf-8")
    assert any(f["check"] == "context-index" for f in hl.check_context_index(docs))


def test_context_index_AC_4_the_researcher_can_write_and_is_told_lookup_first_update_last():
    """context-index/AC-4"""
    card = (HOME / "agents" / "researcher.md").read_text(encoding="utf-8")
    tools = next(line for line in card.splitlines() if line.startswith("tools:"))
    assert "Edit" in tools and "Write" in tools
    skill = (HOME / "skills" / "research-page" / "SKILL.md").read_text(encoding="utf-8")
    assert "context_index.py lookup" in skill and "CONTEXT_INDEX.md" in skill
    assert skill.index("context_index.py lookup") < skill.index("**Have.**")
