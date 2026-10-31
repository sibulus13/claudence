"""Regression tests for the code-review findings on spec_check.py, plus the tool-backed rules (markdownlint, mermaid).

Each test cites the work item AC it belongs to.

    python -m pytest ~/.claude/tests/test_spec_check_findings.py -q
"""
from __future__ import annotations

from pathlib import Path

from test_spec_check import ARCH, CASES_FILE, CHILD, COMP, FUNC, README, W, build, edit, has, run


def lines(r) -> list[str]:
    return r.stdout.splitlines()


def test_ck19_br_tags_are_not_placeholders(tmp_path: Path) -> None:
    # spec-gate-checker/AC-8
    r = run(build(tmp_path, [edit(README, "isolates the external system", "isolates<br>the<br/>external system")]))
    assert r.returncode == 0 and r.stdout == "", r.stdout


def test_ck25_null_or_scalar_evidence_is_an_error_when_shipped(tmp_path: Path) -> None:
    # spec-gate-checker/AC-9
    shipped = edit(README, "status: building", "status: shipped")
    for i, value in enumerate(["evidence:", "evidence: nope"]):
        r = run(build(tmp_path / str(i), [shipped, edit(README, "evidence: { demo: evidence/demo.webm }", value)]))
        assert has(r, "CK-25"), (value, r.stdout)


def test_ck25_evidence_path_must_stay_inside_the_item_folder(tmp_path: Path) -> None:
    # spec-gate-checker/AC-9
    ops = [edit(README, "status: building", "status: shipped"),
           edit(README, "evidence/demo.webm", "../../../tests/demo_cases.txt")]
    r = run(build(tmp_path, ops))
    assert has(r, "CK-25") and "inside" in r.stdout


def test_ck10_untraced_nfr_is_named_in_its_own_message(tmp_path: Path) -> None:
    # spec-gate-checker/AC-4
    r = run(build(tmp_path, [edit(FUNC, "| CAP-4, NFR-1 |", "| CAP-4 |")]))
    assert any("NFR-1 is not traced by any AC" in ln for ln in lines(r)), r.stdout


def test_ck3_profile_must_be_none_rules(tmp_path: Path) -> None:
    # spec-gate-checker/AC-1
    for name, new_type, layer in [("exp", "experiment", "architecture"), ("res", "research", "architecture"),
                                  ("res2", "research", "component"), ("dc", "data-collection", "architecture"),
                                  ("ref", "refactor", "functional")]:
        r = run(build(tmp_path / name, [edit(README, "type: feature", f"type: {new_type}")]))
        assert any(ln.startswith("CK-3:") and f"layers.{layer}" in ln and "none" in ln for ln in lines(r)), (name, r.stdout)


def test_ck16_h3_order_swapped_is_an_error(tmp_path: Path) -> None:
    # spec-gate-checker/AC-6
    swap = [edit(COMP, "### Data", "### TMPX"), edit(COMP, "### Failure modes", "### Data"),
            edit(COMP, "### TMPX", "### Failure modes")]
    r = run(build(tmp_path, swap))
    assert has(r, "CK-16") and "in order" in r.stdout


def test_ck18_parent_sees_a_child_that_names_a_different_parent(tmp_path: Path) -> None:
    # spec-gate-checker/AC-7
    r = run(build(tmp_path, [("family",), edit(CHILD, "parent: demo", "parent: other")]))
    assert any(ln.startswith("CK-18:") and "does not name" in ln for ln in lines(r)), r.stdout


def test_ck1_created_format_alone(tmp_path: Path) -> None:
    # spec-gate-checker/AC-1
    r = run(build(tmp_path, [edit(README, '"2026-10-31"', '"2026/10/31"')]))
    assert any(ln.startswith("CK-1:") and "created" in ln for ln in lines(r)), r.stdout


def test_ck24_a_decision_that_is_not_yet_confirmed_fails(tmp_path: Path) -> None:
    # spec-gate-checker/AC-9
    spike = [edit(README, "| NFR-2 | no import", "| NFR-3 | bounded in 30 s | spike: try it | AC-3 + decision:R-3 |\n| NFR-2 | no import"),
             edit(FUNC, "| CAP-4, NFR-1 |", "| CAP-4, NFR-1, NFR-3 |"),
             edit("docs/DECISIONS.md", "| R-2 |", "| R-3 | Try it | not yet confirmed |\n| R-2 |")]
    assert has(run(build(tmp_path, spike)), "CK-24")
    confirmed = spike[:2] + [edit("docs/DECISIONS.md", "| R-2 |", "| R-3 | Try it | confirmed |\n| R-2 |")]
    assert run(build(tmp_path / "ok", confirmed)).returncode == 0


def test_missing_call_chains_reports_ck4_and_missing_ac_section_reports_ck11(tmp_path: Path) -> None:
    # spec-gate-checker/AC-2
    r = run(build(tmp_path / "a", [edit(ARCH, "## Call chains", "## Chains")]))
    assert any(ln.startswith("CK-4:") and "Call chains" in ln for ln in lines(r)), r.stdout
    assert not any(ln.startswith("CK-15:") for ln in lines(r))
    r = run(build(tmp_path / "b", [edit(FUNC, "## Acceptance criteria", "## Other")]))
    assert has(r, "CK-11") and not has(r, "CK-4"), r.stdout


def test_nested_items_of_any_type_need_the_lite_l0_headings(tmp_path: Path) -> None:
    # spec-gate-checker/AC-2
    r = run(build(tmp_path, [("family",), edit(CHILD, "type: feature", "type: bugfix")]), item="demo-child")
    assert any(ln.startswith("CK-4:") and "Capabilities" not in ln and "Root cause" in ln for ln in lines(r)), r.stdout
    exp = run(build(tmp_path / "e", [("family",), edit(CHILD, "type: feature", "type: experiment")]), item="demo-child")
    assert any(ln.startswith("CK-4:") and "Capabilities" in ln for ln in lines(exp)) or has(exp, "CK-4"), exp.stdout


def test_lifecycle_true_with_architecture_none_is_an_error(tmp_path: Path) -> None:
    # spec-gate-checker/AC-6
    ops = [edit(README, "lifecycle: false", "lifecycle: true"), edit(README, "architecture: added", "architecture: none"),
           ("rm", ARCH)]
    r = run(build(tmp_path, ops))
    assert any(ln.startswith("CK-15:") and "architecture" in ln for ln in lines(r)), r.stdout


def test_children_must_be_a_list(tmp_path: Path) -> None:
    # spec-gate-checker/AC-1
    r = run(build(tmp_path, [edit(README, "lifecycle: false", "lifecycle: false\nchildren: demo-child")]))
    assert has(r, "CK-1") and "children" in r.stdout


def test_ck20_test_path_must_be_inside_the_repo_and_be_a_test_file(tmp_path: Path) -> None:
    # spec-gate-checker/AC-9
    outside = run(build(tmp_path / "o", [edit(FUNC, "| tests/demo_cases.txt |", "| ../outside.txt |")]))
    assert any(ln.startswith("CK-20:") and "inside" in ln for ln in lines(outside)), outside.stdout
    notes = [("write", "docs/notes.txt", "demo/AC-1 demo/AC-2 demo/AC-3 demo/AC-4\n"),
             edit(FUNC, "| tests/demo_cases.txt |", "| docs/notes.txt |")]
    r = run(build(tmp_path / "n", notes))
    assert any(ln.startswith("CK-20:") and "test file" in ln for ln in lines(r)), r.stdout


# ---- tool-backed rules: markdownlint MD043 (CK-4) and the mermaid parser (CK-6, CK-15, CK-22) ----

def test_ck4_is_reported_through_markdownlint_md043(tmp_path: Path) -> None:
    # spec-gate-checker/AC-2
    r = run(build(tmp_path, [edit(README, "## Gate plan", "## Plan")]))
    assert any(ln.startswith("CK-4:") and "Gate plan" in ln and "MD043" in ln for ln in lines(r)), r.stdout


def test_a_heading_inside_a_code_fence_does_not_satisfy_ck4(tmp_path: Path) -> None:
    # spec-gate-checker/AC-2
    r = run(build(tmp_path, [edit(README, "## Gate plan", "```text\n## Gate plan\n```\n\n## Plan")]))
    assert any(ln.startswith("CK-4:") and "Gate plan" in ln for ln in lines(r)), r.stdout


def test_ck4_heading_match_is_case_insensitive(tmp_path: Path) -> None:
    # spec-gate-checker/AC-2
    r = run(build(tmp_path, [edit(README, "## Gate plan", "## GATE PLAN")]))
    assert not has(r, "CK-4"), r.stdout


def test_a_mermaid_diagram_that_does_not_parse_is_a_ck6_finding(tmp_path: Path) -> None:
    # spec-gate-checker/AC-2
    r = run(build(tmp_path, [edit(FUNC, "I[Input] --> P{valid?}", "I[Input --> P{valid?}")]))
    assert any(ln.startswith("CK-6:") and "does not parse" in ln for ln in lines(r)), r.stdout


def test_ck22_counts_participants_with_the_mermaid_parser(tmp_path: Path) -> None:
    # spec-gate-checker/AC-6
    implicit = "  C->>D: x\n  C->>E: y\n  C->>F: z\n"
    r = run(build(tmp_path, [edit(ARCH, "  B-->>A: result\n", "  B-->>A: result\n" + implicit)]))
    assert any(ln.startswith("CK-22:") and "6" in ln for ln in lines(r)), r.stdout


def test_ck15_diagram_kind_comes_from_the_parser(tmp_path: Path) -> None:
    # spec-gate-checker/AC-6
    life = "\n## Lifecycle\n```mermaid\nflowchart TD\n  A --> B\n```\n"
    r = run(build(tmp_path, [edit(README, "lifecycle: false", "lifecycle: true"), ("append", ARCH, life)]))
    assert any(ln.startswith("CK-15:") and "stateDiagram" in ln for ln in lines(r)), r.stdout


def test_a_failing_tool_is_a_named_failure_not_a_pass(tmp_path: Path, monkeypatch) -> None:
    # spec-gate-checker/AC-10
    import subprocess
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import spec_check

    def boom(*a, **k):
        raise subprocess.TimeoutExpired("node", 1)

    monkeypatch.setattr(spec_check.subprocess, "run", boom)
    root = build(tmp_path, [edit(README, "Show a valid work item for the checker fixtures.", f"Unique text {tmp_path.name}")])
    try:
        spec_check.check_item(root / W / "README.md", root)
    except spec_check.ToolError as e:
        assert "timed out" in str(e)
    else:
        raise AssertionError("a tool timeout must raise ToolError")
