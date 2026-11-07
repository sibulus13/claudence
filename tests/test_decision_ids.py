"""decision-ids/AC-1, decision-ids/AC-2, decision-ids/AC-3, decision-ids/MNC-1: a commit may not add a duplicate decision id."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import decision_ids  # noqa: E402

ROW = "| {} | 2026-11-06 | text | confirmed | why | when |\n"


def test_a_new_duplicate_is_reported():
    assert decision_ids.new_duplicates(ROW.format("C1"), ROW.format("C1") * 2) == ["C1"]


def test_an_old_duplicate_does_not_block_unrelated_work():
    old = ROW.format("D-5") * 2
    assert decision_ids.new_duplicates(old, old + ROW.format("D-6")) == []


def test_a_real_commit_with_a_clash_is_refused(tmp_path):
    def git(*a):
        return subprocess.run(["git", *a], cwd=tmp_path, capture_output=True, text=True, timeout=30)

    git("init", "-q")
    git("config", "user.email", "t@example.test")
    git("config", "user.name", "t")
    docs = tmp_path / "docs"
    docs.mkdir()
    f = docs / "DECISIONS.md"
    f.write_text(ROW.format("C1"), encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "base")
    f.write_text(ROW.format("C1") * 2, encoding="utf-8")
    git("add", ".")
    run = subprocess.run([sys.executable, decision_ids.__file__, "docs/DECISIONS.md"], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert run.returncode == 1
    assert "C1" in run.stderr
