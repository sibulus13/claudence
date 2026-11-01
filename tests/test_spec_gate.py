"""Acceptance tests for the git-layer spec gate (spec: docs/specs/spec-gate.md, AC-5..AC-9).

Every test makes a real commit in a temp repo, so the hook sees exactly what git sees.

    python -m pytest ~/.claude/tests/test_spec_gate.py -q
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

CLAUDE = Path(__file__).resolve().parents[1]
GATE = CLAUDE / "scripts" / "spec_gate.py"
FLEET_CONFIG = CLAUDE / "git-hooks" / "fleet-pre-commit-config.yaml"
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t"}
SPEC = ("---\nid: demo\nkind: feature\nstatus: {status}\ncreated: 2026-10-31\n---\n# Demo\n\n"
        "## Acceptance criteria\n| AC | Given / when | Pass when | Fail when | Test |\n|---|---|---|---|---|\n"
        "| AC-1 | x | y | z | tests/test_demo.py |\n")


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=ENV, check=check,
                          timeout=60)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo on `main` with the commit-msg gate installed directly, plus a locked demo spec and its test."""
    r = tmp_path / "repo"
    git(tmp_path, "init", "-q", "-b", "main", str(r))
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "commit-msg").write_text(f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "{GATE.as_posix()}" "$1"\n',
                                      encoding="utf-8", newline="\n")
    git(r, "config", "core.hooksPath", hooks.as_posix())
    write(r, "docs/specs/demo.md", SPEC.format(status="locked"))
    write(r, "tests/test_demo.py", "# demo/AC-1\n")
    write(r, "src/app.py", "x = 1\n")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "chore: init", "--no-verify")
    return r


def write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def commit(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return git(repo, "commit", "-q", *args, check=False)


@pytest.mark.parametrize("form", [["-am", "feat: x"], ["-m", "feat: x", "-a"], ["-m", "wip", "-m", "refactor: later", "-a"],
                                  ["-am", "Add widget, see test: ok"]])
def test_ac5_source_commit_on_default_branch_without_trailer_is_rejected(repo: Path, form: list[str]) -> None:
    # spec-gate/AC-5
    write(repo, "src/app.py", "x = 2\n")
    r = commit(repo, *form)
    assert r.returncode != 0 and "Spec" in r.stderr


def test_ac5_new_untracked_source_staged_by_add_is_rejected(repo: Path) -> None:
    # spec-gate/AC-5
    write(repo, "src/more.py", "y = 1\n")
    git(repo, "add", "src/more.py")
    assert commit(repo, "-m", "feat: more").returncode != 0


@pytest.mark.parametrize("trailer,status,reason", [("docs/specs/nope.md", "locked", "spec not found"),
                                                   ("docs/specs/demo.md", "draft", "must be locked or done"),
                                                   ("../elsewhere/docs/specs/demo.md", "locked", "must name")])
def test_ac6_trailer_naming_missing_draft_or_outside_spec_is_rejected(repo: Path, trailer: str, status: str,
                                                                      reason: str) -> None:
    # spec-gate/AC-6
    write(repo, "docs/specs/demo.md", SPEC.format(status=status))
    write(repo, "src/app.py", "x = 2\n")
    r = commit(repo, "-am", f"feat: x\n\nSpec: {trailer}")
    assert r.returncode != 0 and reason in r.stderr


def test_ac7_valid_trailer_message_file_and_exempt_forms_land(repo: Path, tmp_path: Path) -> None:
    # spec-gate/AC-7
    write(repo, "src/app.py", "x = 2\n")
    assert commit(repo, "-am", "feat: x\n\nSpec: docs/specs/demo.md").returncode == 0
    msg = tmp_path / "msg.txt"
    msg.write_text("fix: y\n\nSpec: docs/specs/demo.md\n", encoding="utf-8")
    write(repo, "src/app.py", "x = 3\n")
    assert commit(repo, "-a", "-F", str(msg)).returncode == 0
    write(repo, "README.md", "docs only\n")
    git(repo, "add", "README.md")
    assert commit(repo, "-m", "docs: readme").returncode == 0


def test_ac7_non_default_branch_and_merge_commits_land(repo: Path) -> None:
    # spec-gate/AC-7
    git(repo, "checkout", "-q", "-b", "agent/wip")
    write(repo, "src/app.py", "x = 9\n")
    assert commit(repo, "-am", "chore: checkpoint").returncode == 0
    git(repo, "checkout", "-q", "main")
    r = git(repo, "merge", "--no-ff", "-q", "-m", "Merge branch 'agent/wip'", "agent/wip", check=False)
    assert r.returncode == 0, r.stderr


def fleet_repo(tmp_path: Path) -> Path:
    r = tmp_path / "fleet"
    git(tmp_path, "init", "-q", "-b", "main", str(r))
    (r / ".pre-commit-config.yaml").write_text(FLEET_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
    git(r, "add", ".pre-commit-config.yaml")
    git(r, "commit", "-qm", "chore: hooks", "--no-verify")
    inst = subprocess.run([sys.executable, "-m", "pre_commit", "install", "-t", "pre-commit", "-t", "commit-msg"],
                          cwd=r, capture_output=True, text=True, env=ENV, timeout=120)
    assert inst.returncode == 0, inst.stderr + inst.stdout
    return r


def test_ac8_file_name_with_space_or_non_ascii_is_rejected(tmp_path: Path) -> None:
    # spec-gate/AC-8
    r = fleet_repo(tmp_path)
    write(r, "notes/my notes.md", "x\n")
    git(r, "add", "-A")
    bad = commit(r, "-m", "docs: notes")
    assert bad.returncode != 0 and "my notes.md" in (bad.stdout + bad.stderr)
    git(r, "rm", "-q", "--cached", "notes/my notes.md")
    write(r, "notes/café.md", "x\n")
    git(r, "add", "-A")
    assert commit(r, "-m", "docs: notes").returncode != 0


def test_ac9_pre_commit_install_wires_both_hooks_into_real_commits(tmp_path: Path) -> None:
    # spec-gate/AC-9
    r = fleet_repo(tmp_path)
    write(r, "src/app.py", "x = 1\n")
    git(r, "add", "-A")
    unspecified = commit(r, "-m", "feat: x")
    assert unspecified.returncode != 0 and "Spec" in (unspecified.stdout + unspecified.stderr)
    write(r, "README.md", "ok\n")
    git(r, "reset", "-q")
    git(r, "add", "README.md")
    assert commit(r, "-m", "docs: readme").returncode == 0


INSTALLER = CLAUDE / "scripts" / "install_fleet_hooks.py"


def plain_repo(path: Path) -> Path:
    git(path.parent, "init", "-q", "-b", "main", str(path))
    write(path, "README.md", "x\n")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "chore: init", "--no-verify")
    return path


def test_ac10_installer_is_idempotent_commits_only_config_and_reports_skips(tmp_path: Path) -> None:
    # spec-gate/AC-10
    root = tmp_path / "fleet"
    root.mkdir()
    fresh, dirty, custom = plain_repo(root / "fresh"), plain_repo(root / "dirty"), plain_repo(root / "custom")
    write(dirty, "src/wip.py", "unrelated = 1\n")
    git(custom, "config", "core.hooksPath", "githooks")
    run = lambda: subprocess.run([sys.executable, str(INSTALLER), str(root), "--no-push"], capture_output=True,
                                 text=True, env=ENV, timeout=300)
    first = run()
    assert first.returncode == 0, first.stderr + first.stdout
    for r in (fresh, dirty):
        assert (r / ".pre-commit-config.yaml").is_file()
        assert (r / ".git" / "hooks" / "commit-msg").is_file()
        assert git(r, "show", "--name-only", "--format=", "HEAD").stdout.split() == [".pre-commit-config.yaml"]
    assert "src/wip.py" in git(dirty, "status", "--porcelain", "-uall").stdout
    assert "custom" in first.stdout and "hooksPath" in first.stdout
    heads = {r: git(r, "rev-parse", "HEAD").stdout for r in (fresh, dirty)}
    second = run()
    assert second.returncode == 0 and all(git(r, "rev-parse", "HEAD").stdout == h for r, h in heads.items())


# ---- Work-Item Standard v2: Spec: docs/work/<id>/README.md (spec-gate/AC-5..AC-7, CK-26) ----

FIXTURE_ITEM = Path(__file__).resolve().parent / "fixtures" / "work-items" / "base"
TRAILER = "Spec: docs/work/demo/README.md"
README_REL = "docs/work/demo/README.md"


@pytest.fixture
def repo2(tmp_path: Path) -> Path:
    """A repo on `main` with the commit-msg gate and the valid building demo work item."""
    import shutil

    r = tmp_path / "repo2"
    git(tmp_path, "init", "-q", "-b", "main", str(r))
    hooks = tmp_path / "hooks2"
    hooks.mkdir()
    (hooks / "commit-msg").write_text(f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "{GATE.as_posix()}" "$1"\n',
                                      encoding="utf-8", newline="\n")
    git(r, "config", "core.hooksPath", hooks.as_posix())
    shutil.copytree(FIXTURE_ITEM, r, dirs_exist_ok=True)
    write(r, "src/app.py", "x = 1\n")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "chore: init", "--no-verify")
    return r


def set_status(repo: Path, status: str) -> None:
    p = repo / README_REL
    text = re.sub(r"^status: .*$", f"status: {status}", p.read_text(encoding="utf-8"), flags=re.M)
    p.write_text(text, encoding="utf-8", newline="\n")


def test_ac5_v2_source_commit_without_trailer_is_rejected_and_names_the_work_item_path(repo2: Path) -> None:
    # spec-gate/AC-5
    write(repo2, "src/app.py", "x = 2\n")
    r = commit(repo2, "-am", "feat: x")
    assert r.returncode != 0 and "docs/work/" in r.stderr and "WORK-ITEM-STANDARD" in r.stderr


@pytest.mark.parametrize("trailer,reason", [("Spec: docs/work/nope/README.md", "does not exist"),
                                            ("Spec: docs/work/demo/functional.md", "must name docs/work"),
                                            ("Spec: ../elsewhere/docs/work/demo/README.md", "must name docs/work"),
                                            ("Spec: docs/work/../../x/README.md", "must name docs/work"),
                                            ("Spec: docs/work/demo/sub/README.md", "must name docs/work")])
def test_ac6_v2_trailer_naming_missing_or_misshapen_path_is_rejected(repo2: Path, trailer: str, reason: str) -> None:
    # spec-gate/AC-6
    write(repo2, "src/app.py", "x = 2\n")
    r = commit(repo2, "-am", f"feat: x\n\n{trailer}")
    assert r.returncode != 0 and reason in r.stderr


def seed_status(repo: Path, status: str) -> None:
    """Make `status` the HEAD state without the hook (the lifecycle forbids reaching some of them from building)."""
    set_status(repo, status)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", f"chore: seed {status}", "--no-verify", "--allow-empty")


@pytest.mark.parametrize("status", ["draft", "spec-locked", "killed", "promoted"])
def test_ac6_v2_source_commit_needs_a_building_or_shipped_item(repo2: Path, status: str) -> None:
    # spec-gate/AC-6
    seed_status(repo2, status)
    write(repo2, "src/app.py", "x = 2\n")
    r = commit(repo2, "-am", f"feat: x\n\n{TRAILER}")
    # promoted on a feature is also invalid frontmatter (CK-1), which the lifecycle gate may report first
    assert r.returncode != 0 and ("CK-26" in r.stderr or (status == "promoted" and "CK-1" in r.stderr)), r.stderr


def test_ac6_v2_an_invalid_building_item_is_rejected_with_the_checkers_problems(repo2: Path) -> None:
    # spec-gate/AC-6
    p = repo2 / README_REL
    p.write_text(p.read_text(encoding="utf-8").replace("owner: harness\n", ""), encoding="utf-8", newline="\n")
    write(repo2, "src/app.py", "x = 2\n")
    r = commit(repo2, "-am", f"feat: x\n\n{TRAILER}")
    assert r.returncode != 0 and "CK-1" in r.stderr


def test_ac7_v2_building_and_shipped_items_let_a_source_commit_land(repo2: Path) -> None:
    # spec-gate/AC-7
    write(repo2, "src/app.py", "x = 2\n")
    assert commit(repo2, "-am", f"feat: x\n\n{TRAILER}").returncode == 0
    set_status(repo2, "shipped")
    write(repo2, "docs/work/demo/evidence/demo.webm", "x")
    git(repo2, "add", "-A")
    write(repo2, "src/app.py", "x = 3\n")
    assert commit(repo2, "-am", f"feat: y\n\n{TRAILER}").returncode == 0


def test_ac7_v2_spec_locked_item_is_fine_on_an_exempt_commit_but_a_broken_one_is_not(repo2: Path) -> None:
    # spec-gate/AC-7
    seed_status(repo2, "spec-locked")
    write(repo2, "tests/red_test.txt", "demo/AC-1\n")
    git(repo2, "add", "-A")
    assert commit(repo2, "-m", f"test: red tests\n\n{TRAILER}").returncode == 0
    p = repo2 / README_REL
    p.write_text(p.read_text(encoding="utf-8").replace("owner: harness\n", ""), encoding="utf-8", newline="\n")
    git(repo2, "add", "-A")
    broken = commit(repo2, "-m", f"docs: tweak\n\n{TRAILER}")
    assert broken.returncode != 0 and "CK-1" in broken.stderr


def test_ac7_v2_untrailered_docs_only_commit_lands(repo2: Path) -> None:
    # spec-gate/AC-7
    write(repo2, "NOTES.md", "x\n")
    git(repo2, "add", "NOTES.md")
    assert commit(repo2, "-m", "docs: notes").returncode == 0
