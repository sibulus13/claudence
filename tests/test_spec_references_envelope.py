"""Acceptance tests for References and Operating envelope (work item: docs/work/spec-references-envelope).

One parametrized case per row of the AC fixtures tables in functional.md. Each case asserts only on CK-47/48/49
lines, so a fixture that is otherwise incomplete for its type cannot make the case pass or fail.

    python -m pytest ~/.claude/tests/test_spec_references_envelope.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from test_spec_check import README, build, edit

CLAUDE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLAUDE / "scripts"))
import gen_heading_config  # noqa: E402
import spec_check  # noqa: E402
import work_item_md  # noqa: E402

RULES = ("CK-47", "CK-48", "CK-49")
LOCAL_HEADER = "| Source (file:line) | Status (working / partial / broken) | What it shows | Decision (extract / wrap / replace / ignore) + reason |"
WEB_HEADER = "| Source (URL) | Date checked | What it shows | Decision |"
ENV_HEADER = "| Assumption | How it is observed (not hoped) | If violated |"
LOCAL_ROW = "| docs/work/demo/README.md:1 | working | the parent item | extract: reuse it |"  # always present
WEB_ROW = "| https://example.org/demo | 2026-10-31 | a convention | ignore: not relevant |"
ENV_ROW = "| one user at a time | AC-1 | refuse: exit 1 with a named reason |"
REFS = "## References\n"
ENVELOPE = "## Operating envelope\n"
LOCKED = edit(README, "status: building", "status: spec-locked")


def section(title: str) -> tuple:
    """Delete one H2 section (heading to the next H2) from the README."""
    return ("cut", title)


def check(tmp_path: Path, ops: list, *, require: bool = True, item: str = "demo") -> list[str]:
    root = build(tmp_path, [op for op in ops if op[0] != "cut"])
    readme = root / "docs" / "work" / item / "README.md"
    text = readme.read_text(encoding="utf-8")
    for op in ops:
        if op[0] == "cut":
            start = text.rindex(f"## {op[1]}\n")  # the last one: a test may insert a second copy first
            end = text.find("\n## ", start + 1)
            text = text[:start] + (text[end + 1:] if end != -1 else "")
    readme.write_text(text, encoding="utf-8", newline="\n")
    errors, warnings = spec_check.check_item(readme, root, require_sections=require)
    return [line for line in errors + warnings if any(f"{r}: " in line for r in RULES)]


def assert_case(lines: list[str], expected: str | None) -> None:
    if expected is None:
        assert lines == [], lines
    else:
        assert any(expected in line for line in lines), lines


def ins(before: str, text: str) -> tuple:
    return edit(README, before, text + before)


# ---------------------------------------------------------------- AC-1: generated heading config

def test_ac1_heading_config_counts_order_leading_and_optional() -> None:
    # spec-references-envelope/AC-1 (fixtures 1.1 to 1.5)
    cfg = gen_heading_config.generate()
    full = ["References", "Operating envelope", "Purpose", "Non-goals", "Capabilities", "Non-functional requirements",
            "Trade-offs", "Patterns applied", "Components chosen", "Gate plan"]
    lite = ["References", "Operating envelope", "Purpose", "Non-goals", "Capabilities", "Non-functional requirements",
            "Gate plan"]
    assert cfg["l0"]["full"] == full and cfg["l0"]["lite"] == lite and cfg["nestedBase"] == lite
    assert cfg["leading"] == ["References", "Operating envelope"]
    counts = {t: len(e["headings"]) for t, e in cfg["readme"].items()}
    assert counts == {"feature": 10, "integration": 11, "data-collection": 9, "experiment": 10, "research": 5,
                      "bugfix": 5, "refactor": 6}
    assert cfg["readme"]["experiment"]["headings"][0] == "References"
    assert cfg["readme"]["refactor"]["headings"][:2] == ["References", "Operating envelope"]
    for t in ("bugfix", "research", "experiment"):
        assert cfg["readme"][t]["optional"] == ["Operating envelope"]
    for t in ("feature", "integration", "data-collection", "refactor"):
        assert "optional" not in cfg["readme"][t]


@pytest.mark.parametrize("fault", ["1.6", "1.7"])
def test_ac1_stale_config_is_detected(tmp_path: Path, fault: str) -> None:
    # spec-references-envelope/AC-1
    std = tmp_path / "STANDARD.md"
    out = tmp_path / "headings.json"
    text = gen_heading_config.STANDARD.read_text(encoding="utf-8")
    out.write_text(json.dumps(gen_heading_config.generate(), indent=2) + "\n", encoding="utf-8")
    if fault == "1.6":
        std.write_text(text.replace('"L0 full" headings: `References`, ', '"L0 full" headings: ', 1), encoding="utf-8")
    else:
        std.write_text(text, encoding="utf-8")
        cfg = json.loads(out.read_text(encoding="utf-8"))
        del cfg["leading"]
        out.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    assert gen_heading_config.stale(out, std) == "stale"


# ---------------------------------------------------------------- AC-2: presence and order

AC2 = [
    ("2.1", [LOCKED, section("References")], "missing section `## References`"),
    ("2.2", [LOCKED, section("Operating envelope")], "missing section `## Operating envelope`"),
    ("2.4", [LOCKED, edit(README, "type: feature", "type: bugfix"), section("Operating envelope")], None),
    ("2.5", [LOCKED, edit(README, "type: feature", "type: research"), section("Operating envelope")], None),
    ("2.6", [LOCKED, edit(README, "type: feature", "type: experiment")], None),
    ("2.7", [edit(README, "status: building", "status: draft"), section("References"), section("Operating envelope")], None),
    ("2.8", [LOCKED, edit(README, "## Purpose\n", "## Purposeless\n"), ins(REFS, "## Purpose\n\nx\n\n")], "`## Purpose` must come after `## References`"),
    ("2.9", [LOCKED, section("Operating envelope"), ins(REFS, ENVELOPE + "\n" + ENV_HEADER + "\n|---|---|---|\n" + ENV_ROW + "\n\n")],
     "`## Operating envelope` must come after `## References`"),
    ("2.10", [LOCKED, ins(ENVELOPE, "## Notes\n\nx\n\n")], "`## Notes`"),
    ("2.11", [LOCKED, ins(ENVELOPE, "## Overview\n\nx\n\n")], "`## Overview` must come before `## References`"),
    ("2.12", [LOCKED, ins(REFS, "## Overview\n\nx\n\n")], None),
    ("2.13", [edit(README, "status: building", "status: killed"), section("References")], None),
]


@pytest.mark.parametrize("fid,ops,expected", AC2, ids=[r[0] for r in AC2])
def test_ac2_presence_and_order(tmp_path: Path, fid: str, ops: list, expected: str | None) -> None:
    # spec-references-envelope/AC-2
    assert_case(check(tmp_path, ops), expected)


def test_ac2_nested_feature_needs_the_envelope(tmp_path: Path) -> None:
    # spec-references-envelope/AC-2 (fixture 2.3)
    lines = check(tmp_path, [("family",), ("cut", "Operating envelope")], item="demo-child")  # child is at building
    assert_case(lines, "missing section `## Operating envelope`")


# ---------------------------------------------------------------- AC-3: tables

AC3 = [
    ("3.1", [LOCKED, edit(README, "| What it shows | Decision (extract", "| Shows | Decision (extract")], "table header must be | Source (file:line)"),
    ("3.2", [LOCKED, edit(README, "| Source (URL) | Date checked |", "| Source (URL) | Checked |")], "table header must be | Source (URL)"),
    ("3.3", [LOCKED, edit(README, "| If violated |", "| Then |")], "table header must be | Assumption"),
    ("3.4", [LOCKED, edit(README, WEB_HEADER + "\n|---|---|---|---|\n" + WEB_ROW + "\n", "")], "needs exactly two tables, has 1"),
    ("3.5", [LOCKED, edit(README, WEB_ROW + "\n", WEB_ROW + "\n\n" + WEB_HEADER + "\n|---|---|---|---|\n" + WEB_ROW + "\n")], "needs exactly two tables, has 3"),
    ("3.6", [LOCKED, edit(README, LOCAL_ROW + "\n", "")], "`Local` needs at least 1 row"),
    ("3.7", [LOCKED, edit(README, WEB_ROW + "\n", "")], "`Web` needs at least 1 row"),
    ("3.8", [LOCKED, edit(README, ENV_ROW + "\n", "")], "`Operating envelope` needs at least 1 row"),
    ("3.9", [LOCKED, edit(README, LOCAL_HEADER + "\n|---|---|---|---|\n", "Local: "), edit(README, WEB_HEADER + "\n|---|---|---|---|\n", "Web: ")], "needs exactly two tables, has 0"),
    ("3.10", [LOCKED], None),
]


@pytest.mark.parametrize("fid,ops,expected", AC3, ids=[r[0] for r in AC3])
def test_ac3_tables(tmp_path: Path, fid: str, ops: list, expected: str | None) -> None:
    # spec-references-envelope/AC-3
    assert_case(check(tmp_path, ops), expected)


# ---------------------------------------------------------------- AC-4: Local cells

def local(row: str) -> list:
    return [LOCKED, edit(README, LOCAL_ROW, row)]


AC4 = [
    ("4.1", local("| tests/demo_cases.txt | working | x | extract: y |"), "`source`"),
    ("4.2", local("| tests/demo_cases.txt:1 | maybe | x | extract: y |"), "`status`"),
    ("4.3", local("| tests/demo_cases.txt:1 | working | x | extend: y |"), "`decision`"),
    ("4.4", local("| tests/demo_cases.txt:1 | working | x | wrap |"), "`decision`"),
    ("4.5", local("| tests/demo_cases.txt:1 | working | x | wrap: |"), "`decision`"),
    ("4.6", local("| none found | - | nothing | n/a: greenfield |"), "Searched"),
    ("4.7", local("| none found | - | Searched D:/repo/ for `x` | n/a: greenfield |\n" + LOCAL_ROW), "`none found` must be the only row"),
    ("4.8", local("| none found | working | Searched D:/repo/ for `x` | n/a: greenfield |"), "`status`"),
    ("4.9", local("| http://x:80 | working | x | extract: y |"), "`source`"),
    ("4.10", local("| D:\\repo\\Factory\\foreman\\core\\worktrees.js:129 | working | x | extract: y |"), None),
    ("4.11", local("| none found | - | Searched D:/repo/ for `worktree` | n/a: greenfield |"), None),
]


@pytest.mark.parametrize("fid,ops,expected", AC4, ids=[r[0] for r in AC4])
def test_ac4_local_cells(tmp_path: Path, fid: str, ops: list, expected: str | None) -> None:
    # spec-references-envelope/AC-4
    assert_case(check(tmp_path, ops), expected)


# ---------------------------------------------------------------- AC-5: citation resolution

AC5 = [
    ("5.1", local("| tests/gone.txt:1 | working | x | extract: y |"), "does not exist"),
    ("5.2", local("| tests/demo_cases.txt:99999 | working | x | extract: y |"), "has fewer lines"),
    ("5.3", local("| tests/demo_cases.txt:40-30 | working | x | extract: y |"), "range"),
    ("5.4", local("| tests/demo_cases.txt:0 | working | x | extract: y |"), "line number must be at least 1"),
    ("5.6", [edit(README, ENV_ROW, "| one user at a time | tests/gone.txt:3 | refuse: exit 1 |")], "does not exist"),
    ("5.7", [edit(README, "status: building", "status: shipped"), edit(README, LOCAL_ROW, "| tests/gone.txt:1 | working | x | extract: y |")], "warn: CK-48"),
    ("5.8", local("| d:\\repo\\Factory\\foreman\\core\\merge.js:135 | working | x | extract: y |"), None),
    ("5.10", local("| ~/.claude/scripts/spec_check.py:52 | working | x | extract: y |"), None),
]


@pytest.mark.parametrize("fid,ops,expected", AC5, ids=[r[0] for r in AC5])
def test_ac5_citation_resolution(tmp_path: Path, fid: str, ops: list, expected: str | None) -> None:
    # spec-references-envelope/AC-5
    assert_case(check(tmp_path, ops), expected)


def test_ac5_oversize_file_is_too_large_to_verify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # spec-references-envelope/AC-5 (fixture 5.5)
    monkeypatch.setattr(spec_check, "MAX_CITED_BYTES", 10)
    assert_case(check(tmp_path, [LOCKED]), "too large to verify")


def test_ac5_repo_relative_citation_resolves_against_the_root() -> None:
    # spec-references-envelope/AC-5 (fixture 5.9)
    assert spec_check.resolve_citation("scripts/spec_check.py:52", CLAUDE) is None


# ---------------------------------------------------------------- AC-6: Web cells

def web(row: str) -> list:
    return [LOCKED, edit(README, WEB_ROW, row)]


AC6 = [
    ("6.1", web("| example.com | 2026-10-31 | x | ignore: y |"), "`source`"),
    ("6.2", web("| https://example.org/a | 2026-13-40 | x | ignore: y |"), "`date_checked`"),
    ("6.3", web("| https://example.org/a | 31/10/2026 | x | ignore: y |"), "`date_checked`"),
    ("6.4", web("| https://example.org/a | 2999-01-01 | x | ignore: y |"), "in the future"),
    ("6.5", web("| n/a | - | - | - |"), "`source`"),
    ("6.6", web("| n/a: purely internal refactor | 2026-10-31 | - | - |"), "`date_checked`"),
    ("6.7", web("| <https://example.org/a> | 2026-10-31 | x | ignore: y |"), "`source`"),
    ("6.8", web("| https://example.org/a | 2026-10-31 | x | ignore |"), "`decision`"),
    ("6.9", web("| https://example.org/a | 2026-10-31 | x | ignore: not relevant |"), None),
    ("6.10", web("| n/a: purely internal refactor | - | - | - |"), None),
]


@pytest.mark.parametrize("fid,ops,expected", AC6, ids=[r[0] for r in AC6])
def test_ac6_web_cells(tmp_path: Path, fid: str, ops: list, expected: str | None) -> None:
    # spec-references-envelope/AC-6
    assert_case(check(tmp_path, ops), expected)


# ---------------------------------------------------------------- AC-7: Envelope cells

def env(row: str) -> list:
    return [LOCKED, edit(README, ENV_ROW, row)]


AC7 = [
    ("7.1", env("| one user |  | refuse: x |"), "`observed`"),
    ("7.2", env("| one user | TBD | refuse: x |"), "`observed`"),
    ("7.3", env("| one user | we watch it carefully | refuse: x |"), "typed pointer"),
    ("7.4", env("| one user | AC-1 | ignore: carry on |"), "`violated`"),
    ("7.5", env("| one user | AC-1 | keep |"), "`violated`"),
    ("7.6", env("| one user | AC-1 | Keep: x |"), "`violated`"),
    ("7.7", env("|  | AC-1 | refuse: x |"), "`assumption`"),
    ("7.8", env("| one user | AC-1 | refuse: exit 1 with a named reason |"), None),
    ("7.9", env("| one user | `git status` | defer: retry within 1 h |"), None),
    ("7.10", env("| one user | https://example.org/a | flag: warn line, no block |"), None),
]


@pytest.mark.parametrize("fid,ops,expected", AC7, ids=[r[0] for r in AC7])
def test_ac7_envelope_cells(tmp_path: Path, fid: str, ops: list, expected: str | None) -> None:
    # spec-references-envelope/AC-7
    assert_case(check(tmp_path, ops), expected)


# ---------------------------------------------------------------- AC-10: standard, templates, reviewer text

STANDARD = (CLAUDE / "skills" / "dark-factory" / "WORK-ITEM-STANDARD.md").read_text(encoding="utf-8")
TEMPLATES = CLAUDE / "skills" / "dark-factory" / "templates" / "work-item"
REVIEWER = (CLAUDE / "agents" / "reviewer.md").read_text(encoding="utf-8")


def h2(text: str) -> list[str]:
    body = text.split("\n---\n", 1)[1] if text.startswith("---\n") else text  # the frontmatter is not markdown
    return [t for lvl, t, _ in work_item_md.Doc(body).headings if lvl == 2]


def test_ac10_templates_carry_both_sections_with_the_model_headers() -> None:
    # spec-references-envelope/AC-10 (fixtures 10.1 to 10.4)
    readme = (TEMPLATES / "README.md").read_text(encoding="utf-8")
    heads = [h for h in h2(readme) if h != "Overview"]
    assert heads[:2] == ["References", "Operating envelope"]
    for model in (work_item_md.LocalRefRow, work_item_md.WebRefRow, work_item_md.EnvelopeRow):
        assert "| " + " | ".join(model.HEADER) + " |" in readme, model.__name__
    experiment = (TEMPLATES / "README.experiment.md").read_text(encoding="utf-8")
    assert [h for h in h2(experiment) if h != "Overview"][0] == "References"
    assert "optional" in experiment.split("## Operating envelope", 1)[1][:300].lower()


def test_ac10_standard_vocabularies_and_rule_rows_match_the_constants() -> None:
    # spec-references-envelope/AC-10 (fixtures 10.5 to 10.7)
    for word in (*work_item_md.VIOLATED, *work_item_md.LOCAL_STATUSES, *work_item_md.DECISIONS):
        assert f"`{word}`" in STANDARD, word
    for rule in ("CK-47", "CK-48", "CK-49"):
        assert f"| {rule} |" in STANDARD, rule
        assert rule in spec_check.STATIC
    assert "CK-1..CK-49" in STANDARD


def test_ac10_rating_and_citation_sentences_are_present() -> None:
    # spec-references-envelope/AC-10 (fixtures 10.8 to 10.10)
    for text in (STANDARD, REVIEWER):
        assert "can break silently" in text or "can break SILENTLY" in text
        assert "cited local line" in text.lower()


# ---------------------------------------------------------------- review round 1 regressions (2026-10-31)

SPACED = ("write", "my dir/two.txt", "one\ntwo\n")
PROSE = [
    ("R2.1", [LOCKED, edit(README, ENV_ROW, "| one user at a time | curl http://127.0.0.1:8080/health, AC-1 | refuse: exit 1 |")], None),
    ("R2.2", [LOCKED, edit(README, ENV_ROW, "| one user at a time | measured 3.5:1 read/write ratio, AC-1 | refuse: exit 1 |")], None),
    ("R2.3", local("| docs/work/demo/README.md:1 | working | handles v1.2:3 tags | extract: reuse it |"), None),
    ("R2.4", [SPACED, *local("| `my dir/two.txt:2` | working | a path with a space | extract: reuse it |")], None),
    ("R2.5", [SPACED, *local("| `my dir/two.txt:3` | working | one past the end | extract: reuse it |")], "fewer lines (2)"),
    ("R2.6", local("| docs/work/demo/README.md:1: the parent, cited mid-sentence | working | x | extract: y |"), None),
    ("R4.1", [SPACED, *local("| docs/work/demo/README.md:1 | working | cites `my dir/two.txt:2` exactly | extract: x |")], None),
    ("R4.2", [SPACED, *local("| docs/work/demo/README.md:1 | working | cites `my dir/two.txt:2-3` | extract: x |")], "fewer lines (2)"),
]


@pytest.mark.parametrize("fid,ops,expected", PROSE, ids=[c[0] for c in PROSE])
def test_review_prose_is_not_a_citation_and_the_last_line_is_the_boundary(tmp_path: Path, fid: str, ops: list,
                                                                             expected: str | None) -> None:
    # spec-references-envelope/AC-5 (review findings 2 and 4)
    assert_case(check(tmp_path, ops), expected)
