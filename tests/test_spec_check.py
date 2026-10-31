"""Acceptance tests for scripts/spec_check.py (work items: docs/work/spec-gate and docs/work/spec-gate-checker).

Each CK rule has a passing and a failing fixture: the tree under tests/fixtures/work-items/base (a valid building
feature) with a small edit applied. Rules are told apart by the rule id at the start of the output line.

    python -m pytest ~/.claude/tests/test_spec_check.py -q
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

CLAUDE = Path(__file__).resolve().parents[1]
SCRIPT = CLAUDE / "scripts" / "spec_check.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "work-items"
W = "docs/work/demo/"
README, ARCH, COMP, FUNC = W + "README.md", W + "architecture.md", W + "components.md", W + "functional.md"
CASES_FILE = "tests/demo_cases.txt"
CHILD = "docs/work/demo-child/README.md"
LINE = re.compile(r"^(warn: )?CK-\d+: \S+: .+$")


def build(tmp: Path, ops: list[tuple]) -> Path:
    """Copy the base fixture into tmp and apply edit ops. Returns the repo root."""
    root = tmp / "repo"
    shutil.copytree(FIXTURES / "base", root)
    for op in ops:
        apply(root, op)
    return root


def apply(root: Path, op: tuple) -> None:
    kind = op[0]
    if kind == "family":  # add the nested child and list it in the parent
        shutil.copytree(FIXTURES / "child", root, dirs_exist_ok=True)
        apply(root, ("edit", README, "lifecycle: false\n", "lifecycle: false\nchildren: [demo-child]\n"))
        apply(root, ("append", COMP, "\n## child-part\nNested spec: `docs/work/demo-child/`. Trigger: contract.\n"))
    elif kind == "acs":  # grow the AC table to op[1] rows, each cited by the cases file
        rows = "".join(f"| AC-{n} | CAP-1 | g | p | f | {CASES_FILE} |\n" for n in range(5, op[1] + 1))
        apply(root, ("append", FUNC, rows))
        apply(root, ("append", CASES_FILE, "".join(f"demo/AC-{n}\n" for n in range(5, op[1] + 1))))
    elif kind == "edit":
        p = root / op[1]
        text = p.read_text(encoding="utf-8")
        assert op[2] in text, f"fixture edit target missing in {op[1]}: {op[2]!r}"
        p.write_text(text.replace(op[2], op[3], 1), encoding="utf-8", newline="\n")
    elif kind == "append":
        with (root / op[1]).open("a", encoding="utf-8", newline="\n") as f:
            f.write(op[2])
    elif kind == "write":
        p = root / op[1]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(op[2], encoding="utf-8", newline="\n")
    elif kind == "rm":
        (root / op[1]).unlink()
    else:
        raise AssertionError(kind)


def run(root: Path, *flags: str, item: str = "demo") -> subprocess.CompletedProcess:
    readme = root / "docs" / "work" / item / "README.md"
    return subprocess.run([sys.executable, str(SCRIPT), str(readme), "--root", str(root), *flags], capture_output=True,
                          text=True, timeout=30)


def has(r: subprocess.CompletedProcess, rule: str, *, warn: bool = False) -> bool:
    prefix = "warn: " if warn else ""
    return any(line.startswith(f"{prefix}{rule}: ") for line in r.stdout.splitlines())


def edit(rel: str, old: str, new: str) -> tuple:
    return ("edit", rel, old, new)


# rule -> (ops for the passing fixture, ops for the failing fixture, flags, failing finding is a warning)
CASES: dict[str, tuple[list, list, tuple, bool]] = {
    "CK-1": ([], [edit(README, "owner: harness\n", "")], (), False),
    "CK-2": ([], [edit(README, "type: feature", "type: gizmo")], (), False),
    "CK-3": ([], [("rm", ARCH)], (), False),
    "CK-4": ([], [edit(README, "## Patterns applied", "## Patterns")], (), False),
    "CK-5": ([edit(README, "| Queue | medium", "| Cache | low | low | low | low | low | rejected: x |\n| Queue | medium")],
             [edit(README, "| chosen |", "| rejected: also |")], (), False),
    "CK-6": ([], [edit(FUNC, "```mermaid", "```text")], (), False),
    "CK-7": ([], [edit(README, "The user can run the demo", "Run the demo")], (), False),
    "CK-8": ([], [edit(README, "p95 latency <= 200 ms", "fast")], (), False),
    "CK-9": ([], [edit(README, "latency-bench: time", "stopwatch: time")], (), False),
    "CK-10": ([], [edit(README, "| AC-3 |", "| AC-1 |")], (), False),
    "CK-11": ([], [edit(FUNC, "| Pass when |", "| Passes when |")], (), False),
    "CK-12": ([], [edit(FUNC, "| CAP-5, NFR-2 |", "| NFR-2 |")], (), False),
    "CK-13": ([], [edit(FUNC, "| CAP-1, FR-1 |", "| CAP-1, FR-9 |")], (), False),
    "CK-14": ([], [edit(FUNC, "CAP-2, CAP-3, FR-2", "CAP-2, CAP-3")], (), True),
    "CK-15": ([edit(README, "lifecycle: false", "lifecycle: true"),
               ("append", ARCH, "\n## Lifecycle\n```mermaid\nstateDiagram-v2\n  [*] --> Up\n  Up --> [*]\n```\n")],
              [("append", ARCH, "\n## Lifecycle\n```mermaid\nstateDiagram-v2\n  [*] --> Up\n```\n")], (), False),
    "CK-16": ([], [edit(COMP, "### Budget", "### Cost")], (), False),
    "CK-17": ([("family",)], [("family",), edit(CHILD, "nestWhy: other code calls its plug-in contract\n", "")], (), False),
    "CK-18": ([("family",)], [("family",), edit(README, "children: [demo-child]\n", "")], (), False),
    "CK-19": ([], [edit(README, "| adapter |", "| <pattern> |")], (), False),
    "CK-20": ([], [edit(CASES_FILE, "demo/AC-4", "")], (), False),
    "CK-21": ([edit(README, "status: building", "status: killed\nsupersededBy: other"),
                ("write", "docs/work/other/README.md", "x\n")],
               [edit(README, "status: building", "status: building\nsupersededBy: other"),
                ("write", "docs/work/other/README.md", "x\n")], (), False),
    "CK-22": ([], [edit(ARCH, "  participant C as Caller\n", "  participant C as Caller\n  participant D\n  participant E\n  participant F\n")],
              (), False),
    "CK-23": ([("acs", 15)], [("acs", 16)], (), False),
    "CK-24": ([], [edit(README, "config:rules/rules.cfg", "config:rules/gone.cfg")], (), False),
    "CK-25": ([edit(README, "status: building", "status: shipped"), ("write", W + "evidence/demo.webm", "x")],
              [edit(README, "status: building", "status: shipped")], (), False),
    "CK-26": ([], [edit(README, "status: building", "status: spec-locked")], ("--for-source-commit",), False),
}
ITEM = {"CK-17": "demo-child", "CK-18": "demo-child"}  # rules that judge the child, not the parent


def check_pair(tmp_path: Path, rules: list[str]) -> None:
    for rule in rules:
        ok_ops, bad_ops, flags, is_warn = CASES[rule]
        good = run(build(tmp_path / f"{rule}-ok", ok_ops), *flags, item=ITEM.get(rule, "demo"))
        assert good.returncode == 0 and good.stdout == "", f"{rule} passing fixture: {good.stdout}{good.stderr}"
        bad = run(build(tmp_path / f"{rule}-bad", bad_ops), *flags, item=ITEM.get(rule, "demo"))
        assert has(bad, rule, warn=is_warn), f"{rule} silent on its failing fixture: {bad.stdout}{bad.stderr}"
        assert bad.returncode == (0 if is_warn else 1), f"{rule}: {bad.stdout}"
        assert all(LINE.match(line) for line in bad.stdout.splitlines()), bad.stdout


def test_base_fixture_is_valid(tmp_path: Path) -> None:
    # spec-gate/AC-1
    r = run(build(tmp_path, []))
    assert r.returncode == 0 and r.stdout == "", r.stdout + r.stderr


def test_ac1_well_formed_building_item_with_traced_tests_passes(tmp_path: Path) -> None:
    # spec-gate/AC-1
    r = run(build(tmp_path, []))
    assert r.returncode == 0 and r.stdout == ""


def test_ac2_missing_field_bad_enum_or_no_ac_table_fail_naming_the_piece(tmp_path: Path) -> None:
    # spec-gate/AC-2
    no_owner = run(build(tmp_path / "a", [edit(README, "owner: harness\n", "")]))
    assert no_owner.returncode == 1 and "CK-1" in no_owner.stdout and "owner" in no_owner.stdout
    bad_status = run(build(tmp_path / "b", [edit(README, "status: building", "status: wip")]))
    assert bad_status.returncode == 1 and "CK-2" in bad_status.stdout and "status" in bad_status.stdout
    no_table = run(build(tmp_path / "c", [edit(FUNC, "## Acceptance criteria", "## Other")]))
    assert no_table.returncode == 1 and "CK-11" in no_table.stdout and "acceptance" in no_table.stdout.lower()


def test_ac3_missing_or_untraced_test_fails_naming_the_ac(tmp_path: Path) -> None:
    # spec-gate/AC-3
    missing = run(build(tmp_path / "a", [edit(FUNC, "| tests/demo_cases.txt::case |", "| tests/nope.txt |")]))
    assert missing.returncode == 1 and "CK-20" in missing.stdout and "AC-2" in missing.stdout
    untraced = run(build(tmp_path / "b", [edit(CASES_FILE, "demo/AC-2", "")]))
    assert untraced.returncode == 1 and "demo/AC-2" in untraced.stdout


def test_ac3_citation_is_exact_not_a_substring(tmp_path: Path) -> None:
    # spec-gate/AC-3
    root = build(tmp_path, [("write", CASES_FILE, "demo/AC-10 x-demo/AC-1 demo/AC-2 demo/AC-3 demo/AC-4\n")])
    r = run(root)
    assert r.returncode == 1 and "demo/AC-1" in r.stdout and "AC-2" not in r.stdout


def test_ac4_draft_item_needs_no_tests_placeholders_or_sections(tmp_path: Path) -> None:
    # spec-gate/AC-4
    root = build(tmp_path, [edit(README, "status: building", "status: draft"), edit(README, "## Patterns applied", "## Patterns"),
                            edit(README, "| adapter |", "| <pattern> |"), ("rm", CASES_FILE)])
    r = run(root)
    assert r.returncode == 0 and r.stdout == "", r.stdout


def test_ac11_the_real_spec_gate_item_is_valid_and_fast() -> None:
    # spec-gate/AC-11
    started = time.monotonic()
    r = subprocess.run([sys.executable, str(SCRIPT), str(CLAUDE / "docs" / "work" / "spec-gate" / "README.md")],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
    assert time.monotonic() - started <= 5


def test_ac11_the_real_spec_gate_checker_item_is_valid() -> None:
    # spec-gate-checker/AC-10
    r = subprocess.run([sys.executable, str(SCRIPT), str(CLAUDE / "docs" / "work" / "spec-gate-checker" / "README.md")],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr


# ---- spec-gate-checker: one test per AC group, each running its rules' pass/fail fixture pairs ----

def test_checker_ac1_frontmatter_enums_layers(tmp_path: Path) -> None:
    # spec-gate-checker/AC-1
    check_pair(tmp_path, ["CK-1", "CK-2", "CK-3"])
    unquoted = run(build(tmp_path / "date", [edit(README, 'created: "2026-10-31"', "created: 2026-10-31")]))
    assert has(unquoted, "CK-1") and "quote" in unquoted.stdout
    bad_yaml = run(build(tmp_path / "yaml", [edit(README, "touches: [core]", "touches: [core")]))
    assert has(bad_yaml, "CK-1")
    wrong_id = run(build(tmp_path / "id", [edit(README, "id: demo", "id: other")]))
    assert has(wrong_id, "CK-2")
    bad_trigger = run(build(tmp_path / "trig", [("family",), edit(CHILD, "[contract]", "[vibes]")]), item="demo-child")
    assert has(bad_trigger, "CK-2")
    extra = run(build(tmp_path / "extra", [("write", W + "data.md", "# x\n")]))
    assert has(extra, "CK-3", warn=True) and extra.returncode == 0
    profile = run(build(tmp_path / "prof", [edit(README, "functional: added", "functional: none")]))
    assert has(profile, "CK-3")


def test_checker_ac2_headings_and_visual_first(tmp_path: Path) -> None:
    # spec-gate-checker/AC-2
    check_pair(tmp_path, ["CK-4", "CK-6"])
    no_flow = run(build(tmp_path / "flow", [edit(README, "flowchart TD", "graph TD")]))
    assert has(no_flow, "CK-6")
    no_subgraph = run(build(tmp_path / "sub", [edit(ARCH, "subgraph After", "subgraph Later")]))
    assert has(no_subgraph, "CK-6")
    text_first = run(build(tmp_path / "text", [edit(ARCH, "```mermaid", "Some words.\n\n```mermaid")]))
    assert has(text_first, "CK-6")
    no_call_heading = run(build(tmp_path / "comp", [edit(ARCH, "## Components", "## Parts")]))
    assert has(no_call_heading, "CK-4")


def test_checker_ac3_l0_tables(tmp_path: Path) -> None:
    # spec-gate-checker/AC-3
    check_pair(tmp_path, ["CK-5", "CK-7", "CK-8", "CK-9"])
    one_row = run(build(tmp_path / "one", [edit(README, "| Queue | medium | medium | high | high | high | rejected: too heavy |\n", "")]))
    assert has(one_row, "CK-5")
    empty = run(build(tmp_path / "empty", [edit(README, "| adapter | comp-b | isolates the external system |", "| adapter | | x |")]))
    assert has(empty, "CK-5") or has(empty, "CK-19")
    few = run(build(tmp_path / "few", [edit(README, "| CAP-5 | The service must keep its boundary |\n", ""),
                                       edit(FUNC, "| CAP-5, NFR-2 |", "| NFR-2 |")]))
    assert has(few, "CK-7", warn=True) and few.returncode == 0
    dup = run(build(tmp_path / "dup", [edit(README, "| CAP-2 |", "| CAP-1 |")]))
    assert has(dup, "CK-7")
    nfr_dup = run(build(tmp_path / "nfr", [edit(README, "| NFR-2 |", "| NFR-1 |")]))
    assert has(nfr_dup, "CK-8")


def test_checker_ac4_nfr_coverage_and_evidence(tmp_path: Path) -> None:
    # spec-gate-checker/AC-4
    check_pair(tmp_path, ["CK-10"])
    untraced = run(build(tmp_path / "u", [edit(FUNC, "| CAP-4, NFR-1 |", "| CAP-4 |")]))
    assert has(untraced, "CK-10")
    bad_format = run(build(tmp_path / "f", [edit(README, "| AC-3 |", "| later |")]))
    assert has(bad_format, "CK-10")
    no_config = run(build(tmp_path / "c", [edit(README, "| AC-4 + config:rules/rules.cfg |", "| AC-4 |")]))
    assert has(no_config, "CK-10")
    spike_ok = [edit(README, "| NFR-2 | no import", "| NFR-3 | bounded in 30 s | spike: try it | AC-3 + decision:R-1 |\n| NFR-2 | no import"),
                edit(FUNC, "| CAP-4, NFR-1 |", "| CAP-4, NFR-1, NFR-3 |")]
    assert run(build(tmp_path / "s1", spike_ok)).returncode == 0
    spike_bad = [edit(README, "| NFR-2 | no import", "| NFR-3 | bounded in 30 s | spike: try it | AC-3 |\n| NFR-2 | no import"),
                 edit(FUNC, "| CAP-4, NFR-1 |", "| CAP-4, NFR-1, NFR-3 |")]
    assert has(run(build(tmp_path / "s2", spike_bad)), "CK-10")


def test_checker_ac5_ac_table_and_traces(tmp_path: Path) -> None:
    # spec-gate-checker/AC-5
    check_pair(tmp_path, ["CK-11", "CK-12", "CK-13", "CK-14"])
    empty_cell = run(build(tmp_path / "e", [edit(FUNC, "| it answers |", "|  |")]))
    assert has(empty_cell, "CK-11")
    dup = run(build(tmp_path / "d", [edit(FUNC, "| AC-2 |", "| AC-1 |")]))
    assert has(dup, "CK-11")
    dash = run(build(tmp_path / "dash", [edit(FUNC, "| CAP-1, FR-1 |", "| - |")]))
    assert has(dash, "CK-11")


def test_checker_ac6_lifecycle_components_participants(tmp_path: Path) -> None:
    # spec-gate-checker/AC-6
    check_pair(tmp_path, ["CK-15", "CK-16", "CK-22"])
    stray = run(build(tmp_path / "s", [("append", ARCH, "\n## Lifecycle\n```mermaid\nstateDiagram-v2\n  [*] --> Up\n```\n")]))
    assert has(stray, "CK-15")
    no_state = run(build(tmp_path / "n", [edit(README, "lifecycle: false", "lifecycle: true"),
                                          ("append", ARCH, "\n## Lifecycle\nnothing\n")]))
    assert has(no_state, "CK-15")
    no_seq = run(build(tmp_path / "q", [edit(ARCH, "sequenceDiagram", "flowchart TD")]))
    assert has(no_seq, "CK-15")
    swapped = run(build(tmp_path / "o", [edit(COMP, "### Data", "### Zzz")]))
    assert has(swapped, "CK-16")
    bad_stub = run(build(tmp_path / "stub", [("family",), edit(README, "children: [demo-child]\n", "children: [x]\n")]))
    assert has(bad_stub, "CK-16")


def test_checker_ac7_nesting_mirror_and_ac_cap(tmp_path: Path) -> None:
    # spec-gate-checker/AC-7
    check_pair(tmp_path, ["CK-17", "CK-18", "CK-23"])
    size = run(build(tmp_path / "size", [("family",), edit(CHILD, "[contract]", "[size]")]),
               item="demo-child")
    assert has(size, "CK-17")
    orphan = run(build(tmp_path / "orphan", [("family",), edit(CHILD, "parent: demo", "parent: ghost")]),
                 item="demo-child")
    assert has(orphan, "CK-18")
    warn_only = run(build(tmp_path / "w", [("family",), ("acs", 16)]))
    assert has(warn_only, "CK-23", warn=True) and warn_only.returncode == 0, warn_only.stdout


def test_checker_ac8_placeholders(tmp_path: Path) -> None:
    # spec-gate-checker/AC-8
    check_pair(tmp_path, ["CK-19"])
    for bad in ["EXAMPLE (replace) x", "YYYY-MM-DD", "<...>", "AC-<n>", "<need>"]:
        r = run(build(tmp_path / re.sub(r"\W", "", bad), [edit(README, "| adapter |", f"| {bad} |")]))
        assert has(r, "CK-19"), bad
    span = run(build(tmp_path / "span", [edit(README, "| adapter |", "| `Map<string>` |")]))
    assert not has(span, "CK-19"), span.stdout
    ops = run(build(tmp_path / "ops", [edit(README, "| NFR-1 | p95 latency <= 200 ms |", "| NFR-1 | p95 latency <= 200 ms and < 5 errors > 0 |")]))
    assert not has(ops, "CK-19"), ops.stdout


def test_checker_ac9_exec_tier(tmp_path: Path) -> None:
    # spec-gate-checker/AC-9
    check_pair(tmp_path, ["CK-20", "CK-24", "CK-25"])
    locked = run(build(tmp_path / "locked", [edit(README, "status: building", "status: spec-locked"), ("rm", CASES_FILE)]))
    assert locked.returncode == 0, locked.stdout
    bad_decision = run(build(tmp_path / "dec", [edit(README, "| NFR-2 | no import", "| NFR-3 | bounded in 30 s | spike: try it | AC-3 + decision:R-2 |\n| NFR-2 | no import"),
                                                edit(FUNC, "| CAP-4, NFR-1 |", "| CAP-4, NFR-1, NFR-3 |")]))
    assert has(bad_decision, "CK-24")


def test_checker_ac10_killed_promoted_flag_format_and_warnings(tmp_path: Path) -> None:
    # spec-gate-checker/AC-10
    check_pair(tmp_path, ["CK-21", "CK-26", "CK-14"])
    promoted = run(build(tmp_path / "p", [edit(README, "status: building", "status: promoted")]))
    assert has(promoted, "CK-21")
    killed = run(build(tmp_path / "k", [edit(README, "status: building", "status: killed"), edit(README, "## Patterns applied", "## Patterns"),
                                        ("rm", CASES_FILE)]))
    assert killed.returncode == 0 and killed.stdout == ""
    ghost = run(build(tmp_path / "g", [edit(README, "status: building", "status: killed\nsupersededBy: ghost")]))
    assert has(ghost, "CK-21")
    shipped_flag = run(build(tmp_path / "sf", [edit(README, "status: building", "status: shipped"), ("write", W + "evidence/demo.webm", "x")]),
                       "--for-source-commit")
    assert shipped_flag.returncode == 0
    draft_flag = run(build(tmp_path / "df", [edit(README, "status: building", "status: draft")]), "--for-source-commit")
    assert has(draft_flag, "CK-26")
    missing = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / "nope" / "README.md")], capture_output=True, text=True,
                             timeout=30)
    assert missing.returncode == 2


# ---- spec-gate-checker/AC-11: legacy docs/specs mode (v1 rules and output) ----

LEGACY_HEADER = "| AC | Given / when | Pass when | Fail when | Test |\n|---|---|---|---|---|\n"


def legacy_spec(root: Path, *, status: str = "locked", rows: str | None = None, front: str | None = None) -> Path:
    rows = rows if rows is not None else "| AC-1 | x happens | y | z | tests/test_x.py |\n"
    front = front if front is not None else f"id: demo\nkind: feature\nstatus: {status}\ncreated: 2026-10-31\n"
    p = root / "docs" / "specs" / "demo.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{front}---\n# Demo\n\n## Acceptance criteria\n{LEGACY_HEADER}{rows}", encoding="utf-8")
    return p


def legacy_check(path: Path, root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), str(path), "--root", str(root)], capture_output=True, text=True, timeout=30)


def test_checker_ac11_legacy_locked_spec_with_traced_tests_passes(tmp_path: Path) -> None:
    # spec-gate-checker/AC-11
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_a():  # demo/AC-1\n    pass\n", encoding="utf-8")
    r = legacy_check(legacy_spec(tmp_path), tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_checker_ac11_legacy_problems_keep_the_v1_wording(tmp_path: Path) -> None:
    # spec-gate-checker/AC-11
    no_kind = legacy_check(legacy_spec(tmp_path, front="id: demo\nstatus: draft\ncreated: 2026-10-31\n"), tmp_path)
    assert no_kind.returncode == 1 and "kind" in no_kind.stdout and "CK-" not in no_kind.stdout
    missing = legacy_check(legacy_spec(tmp_path), tmp_path)
    assert missing.returncode == 1 and "AC-1" in missing.stdout
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("# demo/AC-10 and x-demo/AC-1\n", encoding="utf-8")
    exact = legacy_check(legacy_spec(tmp_path), tmp_path)
    assert exact.returncode == 1 and "demo/AC-1" in exact.stdout
    assert legacy_check(legacy_spec(tmp_path, status="draft"), tmp_path).returncode == 0


def test_checker_ac11_legacy_nodeid_cells_non_utf8_files_and_example_tables(tmp_path: Path) -> None:
    # spec-gate-checker/AC-11
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_bytes(b"# demo/AC-1 \xff\xfe\n")
    p = legacy_spec(tmp_path, rows="| AC-1 | x | y | z | tests/test_x.py::test_a |\n")
    p.write_text(p.read_text(encoding="utf-8") + "\n```\n| AC-9 | example | a | b | nope.py |\n```\n", encoding="utf-8")
    r = legacy_check(p, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
