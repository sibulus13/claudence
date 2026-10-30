"""SessionStart context: the pending-ledger-draft line.

    python -m pytest ~/.claude/tests/test_session_context.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
import session_context as sc  # noqa: E402


def test_pending_drafts_are_named_by_date(tmp_path: Path):
    (tmp_path / "2026-10-28.md").write_text("x", encoding="utf-8")
    (tmp_path / "2026-10-27.md").write_text("x", encoding="utf-8")
    (tmp_path / "note.txt").write_text("x", encoding="utf-8")
    lines = sc.lines_for(str(tmp_path), "startup", drafts_dir=tmp_path, ledger_file=tmp_path / "none.md")
    assert lines[0] == "ledger draft for 2026-10-27, 2026-10-28 pending: run /ledger to curate it into LEDGER.md."


def test_a_draft_whose_day_is_already_in_the_ledger_is_not_pending(tmp_path: Path):
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    (drafts / "2026-10-28.md").write_text("x", encoding="utf-8")
    (drafts / "2026-10-27.md").write_text("x", encoding="utf-8")
    ledger = tmp_path / "LEDGER.md"
    ledger.write_text("### 2026-10-28 (Wed)", encoding="utf-8")  # heading at EOF, no newline
    assert sc.pending_drafts(drafts, ledger) == ["2026-10-27"]


def test_no_drafts_dir_or_empty_dir_says_nothing_about_the_ledger(tmp_path: Path):
    assert not any("ledger draft" in line for line in sc.lines_for(str(tmp_path), "startup", drafts_dir=tmp_path))
    assert not any("ledger draft" in line for line in sc.lines_for(str(tmp_path), "startup", drafts_dir=tmp_path / "x"))
