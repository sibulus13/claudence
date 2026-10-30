"""Tests for scripts/harness_lint.py: one case per check (a)-(f), plus the new-finding contract.

    python -m pytest ~/.claude/tests/test_harness_lint.py -q
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import harness_lint as hl  # noqa: E402


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *args], check=True,
                   capture_output=True)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    r = tmp_path / "claude"
    (r / "projects" / "proj" / "memory").mkdir(parents=True)
    (r / "CLAUDE.md").write_text("# global\nsee [rules](rules/a.md)\n", encoding="utf-8")
    (r / "rules").mkdir()
    (r / "rules" / "a.md").write_text("rule\n", encoding="utf-8")
    mem = r / "projects" / "proj" / "memory"
    (mem / "MEMORY.md").write_text("- [note](note_one.md): hook\n", encoding="utf-8")
    (mem / "note_one.md").write_text("---\nname: note-one\n---\nbody\n", encoding="utf-8")
    (r / ".gitignore").write_text("state/\n", encoding="utf-8")
    git(r, "init", "-q")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "init")
    return r


def lint(root: Path, cfg: dict | None = None, previous: set[str] | None = None) -> dict:
    return hl.run(root, {**json.loads(json.dumps(hl.DEFAULTS)), **(cfg or {})}, previous)


def of(report: dict, check: str) -> list[dict]:
    return [f for f in report["findings"] if f["check"] == check]


def test_clean_tree_has_no_findings(root: Path):
    assert lint(root)["total"] == 0


def test_a_dangling_markdown_link_and_backtick_path_are_found_but_fenced_and_placeholder_paths_are_not(root: Path):
    (root / "CLAUDE.md").write_text(
        "[gone](rules/missing.md) and `~/definitely-not-here-xyz/file.md` and `~/<placeholder>/x`\n"
        "```\n`~/in-a-fence-xyz/f.md`\n```\n[web](https://example.com/x)\n", encoding="utf-8")
    found = of(lint(root), "paths")
    details = " ".join(f["detail"] for f in found)
    assert "rules/missing.md" in details and "definitely-not-here-xyz" in details
    assert "placeholder" not in details and "in-a-fence" not in details and "example.com" not in details
    assert len(found) == 2


def test_a_path_check_skip_exempts_historical_files(root: Path):
    (root / "rules" / "a.md").write_text("`~/gone-xyz/f.md`\n", encoding="utf-8")
    assert of(lint(root), "paths")
    assert not of(lint(root, {"pathCheckSkip": ["rules/a.md"]}), "paths")


def test_b_deny_list_hits_outside_fleet_docs_only_and_ignore_line_exempts_history(root: Path):
    (root / "rules" / "a.md").write_text("uses CronCreate here\nCronCreate was retired\n", encoding="utf-8")
    (root / "docs" / "fleet").mkdir(parents=True)
    (root / "docs" / "fleet" / "L.md").write_text("CronCreate\n", encoding="utf-8")
    cfg = {"denyList": [{"pattern": "CronCreate", "label": "cron"}], "denyIgnoreLine": "retired"}
    found = of(lint(root, cfg), "deny")
    assert [f["path"] for f in found] == ["rules/a.md"]
    assert "line 1" in found[0]["detail"]


def test_c_parity_flags_unindexed_note_and_dangling_index_link(root: Path):
    mem = root / "projects" / "proj" / "memory"
    (mem / "orphan.md").write_text("x\n", encoding="utf-8")
    (mem / "MEMORY.md").write_text("- [note](note_one.md): h\n- [ghost](ghost.md): h\n", encoding="utf-8")
    details = [f["detail"] for f in of(lint(root), "parity")]
    assert any("orphan.md is not in MEMORY.md" in d for d in details)
    assert any("ghost.md" in d and "does not exist" in d for d in details)


def test_d_budgets_for_global_claude_md_fleet_index_and_project_index(root: Path):
    (root / "CLAUDE.md").write_text("x\n" * 5, encoding="utf-8")
    fleet = root / "projects" / "fleet" / "memory"
    fleet.mkdir(parents=True)
    (fleet / "MEMORY.md").write_text("".join(f"- [n{i}](n{i}.md): h\n" for i in range(4)), encoding="utf-8")
    for i in range(4):
        (fleet / f"n{i}.md").write_text("x\n", encoding="utf-8")
    mem = root / "projects" / "proj" / "memory"
    (mem / "MEMORY.md").write_text("- [note](note_one.md): h\n" * 4, encoding="utf-8")
    cfg = {"fleetMemoryDir": "fleet", "budgets": {**hl.DEFAULTS["budgets"], "globalClaudeMdLines": 3,
                                                  "fleetIndexLines": 3, "projectIndexLines": 3}}
    paths = sorted(f["path"] for f in of(lint(root, cfg), "budget"))
    assert paths == ["CLAUDE.md", "projects/fleet/memory/MEMORY.md", "projects/proj/memory/MEMORY.md"]


def test_d_repo_claude_md_budget_walks_the_configured_tree_and_skips_archive(root: Path, tmp_path: Path):
    tree = tmp_path / "repos"
    (tree / "Theme" / "app").mkdir(parents=True)
    (tree / "_Archive" / "old").mkdir(parents=True)
    (tree / "Theme" / "app" / "CLAUDE.md").write_text("x\n" * 10, encoding="utf-8")
    (tree / "_Archive" / "old" / "CLAUDE.md").write_text("x\n" * 10, encoding="utf-8")
    cfg = {"repoRoot": str(tree), "budgets": {**hl.DEFAULTS["budgets"], "repoClaudeMdLines": 5}}
    found = of(lint(root, cfg), "budget")
    assert len(found) == 1 and found[0]["path"].endswith("Theme/app/CLAUDE.md")


def test_e_wikilink_resolves_by_stem_or_frontmatter_name_and_flags_dangling(root: Path):
    mem = root / "projects" / "proj" / "memory"
    (mem / "note_one.md").write_text("---\nname: note-one\n---\n[[note-one]] [[note_one]] [[missing-note]]\n",
                                     encoding="utf-8")
    found = of(lint(root), "wikilink")
    assert len(found) == 1 and "missing-note" in found[0]["detail"]


def test_f_git_drift_reports_modified_and_untracked(root: Path):
    (root / "rules" / "a.md").write_text("changed\n", encoding="utf-8")
    (root / "new.txt").write_text("n\n", encoding="utf-8")
    details = sorted(f["detail"] for f in of(lint(root), "drift"))
    assert details == ["modified: rules/a.md", "untracked: new.txt"]


def test_new_findings_are_only_ids_absent_from_the_previous_report(root: Path):
    (root / "new.txt").write_text("n\n", encoding="utf-8")
    first = lint(root)
    assert len(first["newFindings"]) == 1
    again = lint(root, previous={f["id"] for f in first["findings"]})
    assert again["newFindings"] == [] and again["resolved"] == 0
    (root / "other.txt").write_text("o\n", encoding="utf-8")
    (root / "new.txt").unlink()
    third = lint(root, previous={f["id"] for f in first["findings"]})
    assert [f["path"] for f in third["newFindings"]] == ["other.txt"] and third["resolved"] == 1


def test_cli_writes_report_and_second_run_has_no_new_findings(root: Path, tmp_path: Path):
    (root / "new.txt").write_text("n\n", encoding="utf-8")
    script = Path(hl.__file__)
    cmd = [sys.executable, str(script), "--root", str(root), "--json"]
    one = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
    two = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
    assert len(one["newFindings"]) == 1 and two["newFindings"] == [] and two["total"] == 1
    assert (root / "state" / "harness-lint.json").exists()
