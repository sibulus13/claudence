"""The lifecycle gate: every staged work-item README makes an allowed status move and passes its tier.

Work item: docs/work/spec-references-envelope (AC-8, fixtures T1 to T9). Real commits in a temp repo; HEAD states are
seeded with --no-verify, then the commit under test runs the real commit-msg hook.

    python -m pytest ~/.claude/tests/test_spec_gate_lifecycle.py -q
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from review_helpers import stage_record
from test_spec_gate import CLAUDE, README_REL, commit, git, repo2, write  # noqa: F401

LIFECYCLE = json.loads((CLAUDE / "contracts" / "work-item.lifecycle.v1.json").read_text(encoding="utf-8"))
ITEM_DIR = "docs/work/demo"
RECORDED = {"spec-locked": "design", "shipped": "code"}  # moves that need a fresh passing record (review-records)


def set_field(repo: Path, key: str, value: str, rel: str = README_REL) -> None:
    p = repo / rel
    text = re.sub(rf"^{key}: .*$", f"{key}: {value}", p.read_text(encoding="utf-8"), count=1, flags=re.M)
    p.write_text(text, encoding="utf-8", newline="\n")


def seed(repo: Path, status: str, **fields: str) -> None:
    """Commit the README at `status` without the hook, so it becomes the HEAD state."""
    set_field(repo, "status", status)
    for k, v in fields.items():
        set_field(repo, k, v)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", f"chore: seed {status}", "--no-verify", "--allow-empty")


def move(repo: Path, status: str) -> subprocess.CompletedProcess:
    set_field(repo, "status", status)
    git(repo, "add", README_REL)
    if status in RECORDED:
        stage_record(repo, RECORDED[status])
    return commit(repo, "-m", f"docs: move to {status}")


def ready_for(repo: Path, status: str) -> None:
    """Make the demo item pass the tier of `status` (shipped needs its evidence file)."""
    if status == "shipped":
        write(repo, f"{ITEM_DIR}/evidence/demo.webm", "x")
    if status == "killed":
        set_field(repo, "status", "killed")


ALLOWED = [(f, t) for f, t in LIFECYCLE["edges"]]


@pytest.mark.parametrize("frm,to", ALLOWED, ids=[f"{f}->{t}" for f, t in ALLOWED])
def test_t1_every_allowed_move_lands(repo2: Path, frm: str, to: str) -> None:
    # spec-references-envelope/AC-8 (T1)
    ready_for(repo2, to)
    seed(repo2, frm)
    r = move(repo2, to)
    assert r.returncode == 0, r.stderr


def test_t1_create_as_draft_and_promote_an_experiment_land(repo2: Path) -> None:
    # spec-references-envelope/AC-8 (T1)
    shutil.copytree(repo2 / ITEM_DIR, repo2 / "docs/work/demo2")
    set_field(repo2, "id", "demo2", "docs/work/demo2/README.md")
    set_field(repo2, "status", "draft", "docs/work/demo2/README.md")
    git(repo2, "add", "-A")
    assert commit(repo2, "-m", "docs: new item").returncode == 0
    p = repo2 / README_REL
    p.write_text(p.read_text(encoding="utf-8").replace("  architecture: added", "  architecture: none"), encoding="utf-8")
    (repo2 / ITEM_DIR / "architecture.md").unlink()
    seed(repo2, "building", type="experiment")
    r = move(repo2, "promoted")
    assert r.returncode == 0, r.stderr


DISALLOWED_NEW = ["spec-locked", "building", "shipped"]


@pytest.mark.parametrize("status", DISALLOWED_NEW)
def test_t2_creating_an_item_past_draft_is_rejected(repo2: Path, status: str) -> None:
    # spec-references-envelope/AC-8 (T2)
    shutil.copytree(repo2 / ITEM_DIR, repo2 / "docs/work/demo2")
    set_field(repo2, "id", "demo2", "docs/work/demo2/README.md")
    set_field(repo2, "status", status, "docs/work/demo2/README.md")
    git(repo2, "add", "-A")
    r = commit(repo2, "-m", "docs: new item")
    assert r.returncode != 0 and "move not allowed" in r.stderr


@pytest.mark.parametrize("frm,to", [("draft", "building"), ("draft", "shipped"), ("spec-locked", "shipped"),
                                    ("building", "promoted")])
def test_t2_skipping_a_stage_or_promoting_a_feature_is_rejected(repo2: Path, frm: str, to: str) -> None:
    # spec-references-envelope/AC-8 (T2)
    ready_for(repo2, to)
    seed(repo2, frm)
    r = move(repo2, to)
    assert r.returncode != 0 and "move not allowed" in r.stderr


def cut(repo: Path, title: str) -> None:
    p = repo / README_REL
    text = p.read_text(encoding="utf-8")
    start = text.index(f"## {title}\n")
    end = text.find("\n## ", start + 1)
    p.write_text(text[:start] + (text[end + 1:] if end != -1 else ""), encoding="utf-8", newline="\n")


def test_t3_locking_without_references_is_rejected(repo2: Path) -> None:
    # spec-references-envelope/AC-8 (T3)
    seed(repo2, "draft")
    cut(repo2, "References")
    r = move(repo2, "spec-locked")
    assert r.returncode != 0 and "missing section `## References`" in r.stderr


def test_t4_building_with_an_uncited_ac_is_rejected(repo2: Path) -> None:
    # spec-references-envelope/AC-8 (T4)
    seed(repo2, "spec-locked")
    (repo2 / "tests/demo_cases.txt").write_text("nothing cited\n", encoding="utf-8")
    git(repo2, "add", "-A")
    r = move(repo2, "building")
    assert r.returncode != 0 and "CK-20" in r.stderr


def test_t5_shipping_without_evidence_is_rejected(repo2: Path) -> None:
    # spec-references-envelope/AC-8 (T5)
    seed(repo2, "building")
    r = move(repo2, "shipped")
    assert r.returncode != 0 and "CK-25" in r.stderr


@pytest.mark.parametrize("amend", [False, True])
def test_t6_breaking_a_locked_spec_is_rejected_also_by_amend(repo2: Path, amend: bool) -> None:
    # spec-references-envelope/AC-8 (T6)
    seed(repo2, "spec-locked")
    cut(repo2, "Operating envelope")
    git(repo2, "add", README_REL)
    r = commit(repo2, *(["--amend", "-m", "docs: amend"] if amend else ["-m", "docs: edit"]))
    assert r.returncode != 0 and "missing section `## Operating envelope`" in r.stderr


def test_t7_preexisting_item_without_sections_only_warns(repo2: Path) -> None:
    # spec-references-envelope/AC-8 (T7)
    cut(repo2, "References")
    cut(repo2, "Operating envelope")
    seed(repo2, "building")
    p = repo2 / README_REL
    p.write_text(p.read_text(encoding="utf-8").replace("# Demo feature", "# Demo feature, edited"), encoding="utf-8")
    git(repo2, "add", README_REL)
    r = commit(repo2, "-m", "docs: typo")
    assert r.returncode == 0 and "warn: CK-47" in r.stderr, r.stderr


def test_t8_the_rules_run_on_a_feature_branch(repo2: Path) -> None:
    # spec-references-envelope/AC-8 (T8)
    git(repo2, "checkout", "-q", "-b", "feat/x")
    test_t2_creating_an_item_past_draft_is_rejected(repo2, "shipped")


@pytest.mark.parametrize("value", ["Spec-Locked", "[oops"])
def test_t9_unreadable_or_unknown_status_is_rejected(repo2: Path, value: str) -> None:
    # spec-references-envelope/AC-8 (T9)
    seed(repo2, "draft")
    r = move(repo2, value)
    assert r.returncode != 0 and "status" in r.stderr


# ---------------------------------------------------------------- review round 1 regressions (2026-10-31)

def branch_with_moves(repo: Path, *moves: str) -> None:
    git(repo, "checkout", "-q", "-b", "feat")
    for status in moves:
        ready_for(repo, status)
        git(repo, "add", "-A")
        r = move(repo, status)
        assert r.returncode == 0, r.stderr
    git(repo, "checkout", "-q", "main")


@pytest.mark.parametrize("squash", [False, True])
def test_review_merging_several_lawful_moves_lands(repo2: Path, squash: bool) -> None:
    # spec-references-envelope/AC-8 (review finding 1)
    seed(repo2, "spec-locked")
    branch_with_moves(repo2, "building", "shipped")
    if squash:
        git(repo2, "merge", "--squash", "-q", "feat")
        r = commit(repo2, "-m", "docs: squash feat")
    else:
        r = subprocess.run(["git", "-C", str(repo2), "merge", "--no-ff", "-q", "-m", "Merge feat", "feat"],
                           capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr


def test_review_merging_a_backward_move_is_still_rejected(repo2: Path) -> None:
    # spec-references-envelope/AC-8 (review finding 1: the merge rule widens to reachability, not to anything)
    seed(repo2, "building")
    git(repo2, "checkout", "-q", "-b", "feat")
    seed(repo2, "draft")  # bypassed on the branch with --no-verify
    git(repo2, "checkout", "-q", "main")
    git(repo2, "merge", "--squash", "-q", "feat")
    r = commit(repo2, "-m", "docs: squash feat")
    assert r.returncode != 0 and "move not allowed" in r.stderr


def test_review_renaming_an_item_folder_is_not_a_creation(repo2: Path) -> None:
    # spec-references-envelope/AC-8 (review finding 3)
    git(repo2, "mv", ITEM_DIR, "docs/work/demo-renamed")
    set_field(repo2, "id", "demo-renamed", "docs/work/demo-renamed/README.md")
    git(repo2, "add", "-A")
    r = commit(repo2, "-m", "docs: rename the item")
    # judged as a move (building -> building), never "(new)"; the tier still applies, so stale AC citations are named
    assert "move not allowed" not in r.stderr and "(new)" not in r.stderr, r.stderr


def test_review_repairing_an_unreadable_head_frontmatter_lands(repo2: Path) -> None:
    # spec-references-envelope/AC-8 (review finding 3)
    p = repo2 / README_REL
    good = p.read_text(encoding="utf-8")
    p.write_text(good.replace("status: building", "status: [building"), encoding="utf-8", newline="\n")
    git(repo2, "add", "-A")
    git(repo2, "commit", "-qm", "chore: break", "--no-verify")
    p.write_text(good, encoding="utf-8", newline="\n")
    git(repo2, "add", README_REL)
    stage_record(repo2, "design")  # a repair is judged as the chain draft -> building (review-records FR-10)
    r = commit(repo2, "-m", "docs: repair the frontmatter")
    assert r.returncode == 0, r.stderr


def test_review_the_committed_type_decides_the_type_edges(repo2: Path) -> None:
    # spec-references-envelope/AC-8 (review finding 8): retyping to experiment does not unlock promoted in one commit
    p = repo2 / README_REL
    p.write_text(p.read_text(encoding="utf-8").replace("  architecture: added", "  architecture: none"), encoding="utf-8")
    (repo2 / ITEM_DIR / "architecture.md").unlink()
    seed(repo2, "building")
    set_field(repo2, "type", "experiment")
    r = move(repo2, "promoted")
    assert r.returncode != 0 and "move not allowed" in r.stderr, r.stderr


def test_review_merging_an_item_created_and_built_on_a_branch_lands(repo2: Path) -> None:
    # spec-references-envelope/AC-8 (review finding 1: "(new) -> building" through a squash)
    git(repo2, "rm", "-rq", ITEM_DIR)
    git(repo2, "commit", "-qm", "chore: no item yet", "--no-verify")
    git(repo2, "checkout", "-q", "-b", "feat")
    git(repo2, "checkout", "-q", "HEAD~1", "--", ITEM_DIR)
    set_field(repo2, "status", "draft")
    git(repo2, "add", "-A")
    assert commit(repo2, "-m", "docs: new item").returncode == 0
    for status in ("spec-locked", "building"):
        r = move(repo2, status)
        assert r.returncode == 0, r.stderr
    git(repo2, "checkout", "-q", "main")
    git(repo2, "merge", "--squash", "-q", "feat")
    r = commit(repo2, "-m", "docs: squash feat")
    assert r.returncode == 0, r.stderr
