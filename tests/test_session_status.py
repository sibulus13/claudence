"""Tests for the computed status at session start (hooks/session_context.py).

    python -m pytest ~/.claude/tests/test_session_status.py -q
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
import session_context as sc  # noqa: E402

GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}


def git(repo: Path, *args: str, when: str | None = None) -> None:
    env = {**GIT_ENV, **({"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when} if when else {})}
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


def repo_with_doc(tmp_path: Path, frontmatter: str) -> Path:
    repo = tmp_path / "r"
    (repo / "docs").mkdir(parents=True)
    git(repo, "init", "-q")
    (repo / "docs" / "STATE.md").write_text(frontmatter + "# State\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "docs: state", when="2026-09-26T10:00:00Z")
    for i in range(3):
        (repo / f"f{i}.txt").write_text(str(i), encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", f"feat: change {i}", when=f"2026-10-0{i + 1}T10:00:00Z")
    return repo


def joined(repo: Path) -> str:
    return "\n".join(sc.lines_for(str(repo), "startup", drafts_dir=repo / "none", ledger_file=repo / "none"))


def test_session_status_AC_1_a_doc_edited_today_still_shows_its_lag(tmp_path: Path):
    """session-status/AC-1"""
    repo = repo_with_doc(tmp_path, '---\nupdatedAt: "2026-09-26T12:00:00Z"\n---\n')
    with (repo / "docs" / "STATE.md").open("a", encoding="utf-8") as fh:
        fh.write("- one appended backlog line\n")
    assert "3 commits since" in joined(repo)


def test_session_status_AC_2_status_names_last_commit_items_in_progress_and_uncommitted(tmp_path: Path):
    """session-status/AC-2"""
    repo = repo_with_doc(tmp_path, "")
    item = repo / "docs" / "work" / "fast-merge" / "README.md"
    item.parent.mkdir(parents=True)
    item.write_text("---\nid: fast-merge\nstatus: building\n---\n# x\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "test: fast-merge tests; item building")
    (repo / "loose.txt").write_text("x", encoding="utf-8")
    text = joined(repo)
    assert "test: fast-merge tests; item building" in text
    assert "fast-merge" in text.split("In progress")[-1]
    assert "1 uncommitted" in text


def test_session_status_AC_3_a_doc_without_a_date_counts_from_its_last_commit(tmp_path: Path):
    """session-status/AC-3"""
    repo = repo_with_doc(tmp_path, "")
    assert "3 commits since" in joined(repo)
