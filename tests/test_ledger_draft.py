"""Tests for scripts/ledger_draft.py: drafting, ledger-row detection, flagging, and the never-writes-the-ledger rule.

    python -m pytest ~/.claude/tests/test_ledger_draft.py -q
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ledger_draft as ld  # noqa: E402
from upkeep_config import DEFAULTS  # noqa: E402

DAY = date(2026, 10, 28)
STAMP = "2026-10-28T12:00:00"


def commit(repo: Path, msg: str, when: str = STAMP) -> None:
    env = {"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "PATH": __import__("os").environ["PATH"]}
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "--allow-empty", "-m", msg], check=True, env=env,
                   capture_output=True)


@pytest.fixture
def world(tmp_path: Path):
    root = tmp_path / "claude"
    (root / "docs" / "fleet").mkdir(parents=True)
    tree = tmp_path / "repos"
    app = tree / "Theme" / "app"
    app.mkdir(parents=True)
    for r in (root, app):
        subprocess.run(["git", "init", "-q", str(r)], check=True)
    cfg = {**DEFAULTS, "repoRoot": str(tree), "ledgerDraftMinCommits": 2}
    return root, app, cfg


def test_render_groups_commits_by_repo_oldest_first(world):
    root, app, cfg = world
    commit(app, "feat: one", "2026-10-28T09:00:00")
    commit(app, "fix: two", "2026-10-28T10:00:00")
    commit(root, "docs: three")
    text = ld.render(DAY, ld.day_commits(root, cfg, DAY))
    assert text.startswith("### 2026-10-28 (Wed)")
    assert "| Theme/app | feat: one |" in text and text.index("feat: one") < text.index("fix: two")
    assert "| claudence | docs: three |" in text and "<!-- 3 commits" in text


def test_ledger_has_day_matches_only_that_days_heading():
    assert ld.ledger_has_day("### 2026-10-28 (Wed)\nrows", DAY)
    assert not ld.ledger_has_day("### 2026-10-29 (Thu)\n", DAY)
    assert not ld.ledger_has_day("mentions 2026-10-28 in prose", DAY)


def test_plan_drafts_an_unledgered_day_flags_it_and_is_new_once(world):
    root, app, cfg = world
    for i in range(3):
        commit(app, f"feat: {i}")
    out = root / "docs" / "fleet" / "drafts"
    first = ld.plan(root, cfg, DAY, 1, out)[0]
    assert first["commits"] == 3 and first["flagged"] and first["new"]
    assert (out / "2026-10-28.md").read_text(encoding="utf-8").count("| Theme/app |") == 3
    second = ld.plan(root, cfg, DAY, 1, out)[0]
    assert second["flagged"] and not second["new"]


def test_plan_does_not_flag_a_quiet_day_and_skips_a_ledgered_day(world):
    root, app, cfg = world
    commit(app, "feat: only one")
    out = root / "drafts"
    quiet = ld.plan(root, cfg, DAY, 1, out)[0]
    assert quiet["commits"] == 1 and not quiet["flagged"]
    (root / "docs" / "fleet" / "LEDGER.md").write_text("### 2026-10-28 (Wed)\n", encoding="utf-8")
    (out / "2026-10-28.md").unlink()
    done = ld.plan(root, cfg, DAY, 1, out)[0]
    assert done["ledgered"] and done["draft"] is None and not (out / "2026-10-28.md").exists()


def test_plan_covers_the_lookback_window(world):
    root, app, cfg = world
    commit(app, "feat: yesterday", "2026-10-27T12:00:00")
    report = ld.plan(root, cfg, DAY, 3, root / "drafts")
    assert [e["date"] for e in report] == ["2026-10-28", "2026-10-27", "2026-10-26"]
    assert [e["commits"] for e in report] == [0, 1, 0]


def test_cli_json_never_touches_the_ledger_and_reports_new_findings(world, tmp_path: Path):
    root, app, cfg = world
    ledger = root / "docs" / "fleet" / "LEDGER.md"
    ledger.write_text("### 2026-10-29 (Thu)\nrow\n", encoding="utf-8")
    before = ledger.read_bytes()
    for i in range(3):
        commit(app, f"feat: {i}")
    (root / "docs" / "fleet" / "upkeep.config.json").write_text(
        json.dumps({"repoRoot": cfg["repoRoot"], "ledgerDraftMinCommits": 2}), encoding="utf-8")
    cmd = [sys.executable, str(Path(ld.__file__)), "2026-10-28", "--root", str(root), "--days", "1",
           "--out", str(root / "docs" / "fleet" / "drafts"), "--json"]
    out = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
    assert [f["id"] for f in out["newFindings"]] == ["ledger-draft:2026-10-28"]
    assert ledger.read_bytes() == before
    again = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
    assert again["newFindings"] == []
