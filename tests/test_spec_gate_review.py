"""Regression tests for the code-review findings on the commit-msg gate (spec: docs/work/spec-gate, AC-5..AC-7).

    python -m pytest ~/.claude/tests/test_spec_gate_review.py -q
"""
from __future__ import annotations

import itertools
import subprocess
import sys
from pathlib import Path

import pytest

from test_spec_gate import ENV, GATE, README_REL, TRAILER, commit, git, repo2, set_status, write  # noqa: F401


COUNTER = itertools.count(2)


def staged_only_src_commit(repo: Path, message: str | None = None) -> subprocess.CompletedProcess:
    write(repo, "src/app.py", f"x = {next(COUNTER)}\n")  # a new change each call, so there is always something staged
    git(repo, "add", "src/app.py")
    return commit(repo, "-m", message or f"feat: x\n\n{TRAILER}")


# ---- finding 1: the gate reads the commit (the index), never the working tree ----

def test_readme_is_read_from_the_index_not_the_working_tree(repo2: Path) -> None:
    # spec-gate/AC-6
    set_status(repo2, "draft")
    git(repo2, "add", "-A")
    git(repo2, "commit", "-qm", "docs: draft", "--no-verify")
    set_status(repo2, "building")  # on disk and unstaged only
    r = staged_only_src_commit(repo2)
    assert r.returncode != 0 and "CK-26" in r.stderr


def test_a_test_file_that_exists_only_on_disk_does_not_satisfy_ck20(repo2: Path) -> None:
    # spec-gate/AC-6
    git(repo2, "rm", "-q", "--cached", "tests/demo_cases.txt")
    git(repo2, "commit", "-qm", "chore: untrack", "--no-verify")
    assert (repo2 / "tests" / "demo_cases.txt").is_file()
    r = staged_only_src_commit(repo2)
    assert r.returncode != 0 and "CK-20" in r.stderr


def test_a_work_item_that_exists_only_on_disk_does_not_exist_for_the_gate(repo2: Path) -> None:
    # spec-gate/AC-6
    write(repo2, "docs/work/fresh/README.md", (repo2 / README_REL).read_text(encoding="utf-8").replace("id: demo", "id: fresh"))
    r = staged_only_src_commit(repo2, "feat: x\n\nSpec: docs/work/fresh/README.md")
    assert r.returncode != 0 and "does not exist" in r.stderr


def test_a_config_file_that_exists_only_on_disk_does_not_satisfy_ck24(repo2: Path) -> None:
    # spec-gate/AC-6
    git(repo2, "rm", "-q", "--cached", "rules/rules.cfg")
    git(repo2, "commit", "-qm", "chore: untrack", "--no-verify")
    r = staged_only_src_commit(repo2)
    assert r.returncode != 0 and "CK-24" in r.stderr


def test_the_staged_version_of_the_readme_is_what_counts(repo2: Path) -> None:
    # spec-gate/AC-7
    set_status(repo2, "draft")  # staged draft, so rejected even though HEAD says building
    git(repo2, "add", README_REL)
    r = staged_only_src_commit(repo2)
    # the staged status is what is judged: the lifecycle gate rejects the staged move building -> draft first
    assert r.returncode != 0 and ("CK-26" in r.stderr or "move not allowed: building -> draft" in r.stderr), r.stderr


# ---- finding 2: detached HEAD fails closed ----

def test_detached_head_is_gated(repo2: Path) -> None:
    # spec-gate/AC-5
    git(repo2, "checkout", "-q", "--detach")
    r = staged_only_src_commit(repo2, "feat: x")
    assert r.returncode != 0 and "no `Spec: docs/work/<id>/README.md` trailer" in r.stderr


def test_unresolvable_default_branch_is_gated_not_guessed(repo2: Path) -> None:
    # spec-gate/AC-5 (final review R-1: `trunk` with no origin/HEAD was treated as an agent branch and waved through)
    git(repo2, "branch", "-q", "-m", "trunk")
    r = staged_only_src_commit(repo2, "feat: x")
    assert r.returncode != 0 and "no `Spec: docs/work/<id>/README.md` trailer" in r.stderr


def test_detached_head_during_a_rebase_is_not_gated(repo2: Path) -> None:
    # spec-gate/AC-7
    git(repo2, "checkout", "-q", "--detach")
    git_dir = Path(git(repo2, "rev-parse", "--git-dir").stdout.strip())
    (repo2 / git_dir / "REBASE_HEAD").write_text(git(repo2, "rev-parse", "HEAD").stdout, encoding="utf-8")
    assert staged_only_src_commit(repo2, "feat: replayed").returncode == 0


# ---- finding 3: the source filter and the exemptions ----

@pytest.mark.parametrize("path", ["src/dist/x.js", "pkg/build/y.py", "lib/out/z.go", "a.c", "b.cpp", "c.h", "d.kt", "e.swift",
                                  "f.scala", "g.ex", "h.ipynb", "i.r", "j.tf", "k.m", "l.pl", "m.hpp", "n.cc", "o.kts", "p.exs"])
def test_nested_dist_dirs_and_more_languages_count_as_source(repo2: Path, path: str) -> None:
    # spec-gate/AC-5
    write(repo2, path, "x\n")
    git(repo2, "add", path)
    r = commit(repo2, "-m", "feat: x")
    assert r.returncode != 0 and "no `Spec:" in r.stderr


@pytest.mark.parametrize("path", ["dist/x.js", "build/y.py", "out/z.go", "coverage/c.js", "tests/helper.py", "README.md"])
def test_root_build_output_tests_and_docs_are_not_source(repo2: Path, path: str) -> None:
    # spec-gate/AC-7
    write(repo2, path, "x\n")
    git(repo2, "add", path)
    assert commit(repo2, "-m", "chore: x").returncode == 0


@pytest.mark.parametrize("kind", ["refactor", "style", "test"])
def test_a_subject_type_is_a_claim_not_an_exemption(repo2: Path, kind: str) -> None:
    # spec-gate/AC-5
    r = staged_only_src_commit(repo2, f"{kind}: tidy")
    assert r.returncode != 0 and "no `Spec:" in r.stderr


def test_a_refactor_with_a_building_work_item_lands(repo2: Path) -> None:
    # spec-gate/AC-7
    assert staged_only_src_commit(repo2, f"refactor: tidy\n\n{TRAILER}").returncode == 0


def test_revert_is_exempt_only_with_a_real_reverted_sha(repo2: Path) -> None:
    # spec-gate/AC-7
    sha = git(repo2, "rev-parse", "HEAD").stdout.strip()
    ok = staged_only_src_commit(repo2, f'Revert "chore: init"\n\nThis reverts commit {sha}.')
    assert ok.returncode == 0, ok.stderr
    bare = staged_only_src_commit(repo2, 'Revert "chore: init"')
    assert bare.returncode != 0 and "no `Spec:" in bare.stderr
    bogus = staged_only_src_commit(repo2, 'Revert "x"\n\nThis reverts commit ' + "0" * 40 + ".")
    assert bogus.returncode != 0 and "no `Spec:" in bogus.stderr


# ---- finding 7: specific reasons, fail closed, ambiguity ----

def test_a_git_failure_rejects_and_says_it_failed_closed(tmp_path: Path) -> None:
    # spec-gate/AC-5
    msg = tmp_path / "msg.txt"
    msg.write_text("feat: x\n", encoding="utf-8")
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    r = subprocess.run([sys.executable, str(GATE), str(msg)], cwd=not_a_repo, capture_output=True, text=True, env=ENV, timeout=60)
    assert r.returncode == 1 and "fails closed" in r.stderr


def test_two_spec_trailers_are_ambiguous_and_rejected(repo2: Path) -> None:
    # spec-gate/AC-6
    r = staged_only_src_commit(repo2, f"feat: x\n\nSpec: docs/work/nope/README.md\nSpec: docs/work/demo/README.md")
    assert r.returncode != 0 and "exactly one" in r.stderr


def test_a_symlink_or_outside_path_cannot_stand_in_for_the_work_item(repo2: Path) -> None:
    # spec-gate/AC-6
    r = staged_only_src_commit(repo2, "feat: x\n\nSpec: docs/work/demo/../../../outside/README.md")
    assert r.returncode != 0 and "must name docs/work" in r.stderr
