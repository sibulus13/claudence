"""Acceptance tests for work item spec-standard-v3: the opt-in `standard: 3` profile (docs/work/spec-standard-v3).

Correctness first (look-alikes, thresholds, the lock and the frozen set), then the regression surface (v2 untouched, the
corpus), then the happy path. Checker tests build README text with `readme()` and judge it through the real
`spec_check.check_work_item`; gate tests make real commits in a temp repo with the real commit-msg hook.

    python -m pytest tests/test_spec_v3.py -q                 # everything
    python -m pytest tests/test_spec_v3.py -q -k corpus       # AC-1, the one-time v2 corpus acceptance check
    python -m pytest tests/test_spec_v3.py -q -k docs         # AC-15 (SPEC_V3_DOCS_ROOT overrides where the docs are read)
"""
from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import io
from pathlib import Path

import pytest

from review_helpers import stage_record
from test_spec_gate import CLAUDE, ENV, GATE, commit, git, write

sys.path.insert(0, str(CLAUDE / "scripts"))
import review_record  # noqa: E402
import spec_check  # noqa: E402
import work_item_schema  # noqa: E402

CONTRACT = CLAUDE / "contracts" / "work-item.v3.json"
PINNED_BASE = "94b1b4b"
MAIN_CLAUDE = Path("C:/Users/Michael/.claude")
FLAGS = ["contract", "data", "security", "enforcement", "concurrency", "removal", "live"]
DIMS = ["success", "invalid input", "dependency fails", "timeout", "crash mid-step", "concurrent actor",
        "duplicate or replay", "arrival channel", "performance or cost", "security", "data and compatibility",
        "operability"]
FLAG_MAP = {"contract": ["data and compatibility", "arrival channel"], "data": ["data and compatibility", "crash mid-step"],
            "security": ["security", "invalid input"], "enforcement": ["invalid input", "arrival channel"],
            "concurrency": ["concurrent actor", "duplicate or replay"], "removal": ["data and compatibility"],
            "live": ["operability", "dependency fails"]}
ITEM = "docs/work/demo"
README = f"{ITEM}/README.md"
AC_HEADER = "| AC | Traces | Given / when | Pass when | Fail when | Test |\n|---|---|---|---|---|---|"
OUT_HEADER = "| Dimension | Level | Row or n/a reason | AC |\n|---|---|---|---|"
ASSUMPTIONS = "| Assumption | Observed | If violated |\n|---|---|---|\n| the helper exists | `src/a.py:3` | keep: carry on |"


def sv3():
    return importlib.import_module("spec_v3")


# ---------------------------------------------------------------- README builder

def ac_table(n: int) -> str:
    rows = [f"| AC-{i} | CAP-{i} | given {i} | passes {i} | fails {i} | tests/test_demo.py |" for i in range(1, n + 1)]
    return "\n".join([AC_HEADER, *rows])


def outcome_table(levels: dict[str, tuple[str, str, str]] | None = None, skip: tuple[str, ...] = ()) -> str:
    """12 rows. Default: success and invalid input at L3 (AC-1), the rest L1 with a three-word reason."""
    table = {d: ("L1", "cannot occur in this check", "-") for d in DIMS}
    table["success"] = ("L3", "the happy path is asserted", "AC-1")
    table["invalid input"] = ("L3", "bad input is refused", "AC-1")
    table.update(levels or {})
    return "\n".join([OUT_HEADER, *(f"| {d} | {lv} | {why} | {ac} |" for d, (lv, why, ac) in table.items() if d not in skip)])


def forced_l3(flags: list[str]) -> dict[str, tuple[str, str, str]]:
    return {d: ("L3", f"asserted for {d}", "AC-1") for f in flags for d in FLAG_MAP.get(f, ())}


def readme(*, type: str = "feature", tier: str | None = "T1", risk: tuple[str, ...] = (), status: str = "spec-locked",
           n_acs: int | None = None, levels: dict | None = None, fm: dict | None = None, drop: tuple[str, ...] = (),
           body: dict[str, str] | None = None, extra: str = "", live: bool = False, diagram: bool = True) -> str:
    """A valid v3 README unless an override breaks it. `fm` overrides raw YAML values (None deletes the key); `body`
    overrides a section's text by title; `drop` removes sections; `extra` is appended verbatim."""
    bug = type == "bugfix"
    n_acs = n_acs if n_acs is not None else (1 if bug else 2)
    t2 = not bug and (tier == "T2" or bool(risk) or live or n_acs > 5)
    front = {"id": "demo", "type": type, "standard": "3", "tier": None if bug else tier, "risk": f"[{', '.join(risk)}]",
             "status": status, "touches": "[harness]",
             "layers": "{architecture: none, component: none, functional: none, data: none}",
             "created": '"2026-11-02"', "owner": "harness"}
    front.update(fm or {})
    head = "\n".join(f"{k}: {v}" for k, v in front.items() if v is not None)
    flags = [*risk, *(["live"] if live and "live" not in risk else [])]
    if bug:
        sections = {"Symptom": "wrong output on empty input", "Reproduce": "1. run it with empty input",
                    "Expected": ac_table(n_acs), "Actual": "```\nTraceback\n```",
                    "Must not change": "| ID | Must not change | Test |\n|---|---|---|\n| MNC-1 | the other path | tests/test_demo.py |",
                    "Root cause": "the guard is missing"}
        if flags:
            sections["Probe"] = "[probe](evidence/probe.md)"
    else:
        sections = {"Purpose": "A small change for a small reason.", "Goals and non-goals": "- goal\n- non-goal: nothing else",
                    "Behaviour": ac_table(n_acs),
                    "Outcomes": outcome_table({**forced_l3(flags), **(levels or {})})}
        if t2:
            sections["Approach"] = "Chosen: A. Option B: slower, rejected."
            sections["Assumptions"] = ASSUMPTIONS
            sections["Probe"] = "[probe](evidence/probe.md)"
        if "contract" in risk:
            sections["Contracts"] = "work-item.v3 version 1"
    sections.update(body or {})
    parts = [f"---\n{head}\n---\n# Demo\n"]
    if diagram:
        parts.append("```mermaid\nflowchart TD\n  A --> B\n```\n")
    parts += [f"## {title}\n\n{text}\n" for title, text in sections.items() if title not in drop]
    return "\n".join(parts) + extra


def cites(n_acs: int = 2, mnc: int = 1) -> str:
    return "\n".join([*(f"# demo/AC-{i}" for i in range(1, n_acs + 1)), *(f"# demo/MNC-{i}" for i in range(1, mnc + 1))]) + "\n"


def lay_out(root: Path, text: str, *, n_acs: int = 2, tests: str | None = None, claude_md: str | None = None,
            files: dict[str, str] | None = None) -> str:
    """Write the item and the files it cites under `root`; return the README's repo-relative path."""
    write(root, README, text)
    write(root, "tests/test_demo.py", tests if tests is not None else cites(n_acs))
    write(root, "src/a.py", "\n".join(f"line {i}" for i in range(1, 21)) + "\n")
    write(root, f"{ITEM}/evidence/probe.md", "# probe\n")
    if claude_md is not None:
        write(root, "CLAUDE.md", claude_md)
    for rel, body in (files or {}).items():
        write(root, rel, body)
    return README


def check(tmp: Path, text: str, *, n_acs: int = 2, **kw) -> list[str]:
    rel = lay_out(tmp, text, n_acs=n_acs, **kw)
    return spec_check.check_work_item(spec_check.DiskTree(tmp), rel)[0]


def has(errors: list[str], rule: str, *needles: str) -> bool:
    return any(e.startswith(f"{rule}:") and all(n in e for n in needles) for e in errors)


def show(errors: list[str]) -> str:
    return "\n".join(errors) or "(no errors)"


# ---------------------------------------------------------------- the happy path (valid forms read clean)

@pytest.mark.parametrize("kw", [dict(), dict(tier="T2"), dict(risk=("contract",), tier="T2"), dict(type="bugfix"),
                                dict(type="bugfix", risk=("data",)), dict(n_acs=15, tier="T2")],
                         ids=["T1", "T2", "T2-contract", "bugfix", "bugfix-flagged", "T2-15-acs"])
def test_ac2_valid_forms_pass_at_every_checked_status(tmp_path: Path, kw: dict) -> None:
    # spec-standard-v3/AC-2
    for status in ("draft", "spec-locked", "building", "shipped"):
        errors = check(tmp_path, readme(status=status, **kw), n_acs=kw.get("n_acs") or (1 if kw.get("type") else 2))
        assert errors == [], f"{status}: {show(errors)}"


# ---------------------------------------------------------------- AC-2: the one reader, look-alikes

def fm_case(**over: str | None) -> str:
    return readme(status="draft", fm=over)


LOOKALIKES = [
    ("standard-string", fm_case(standard='"3"'), "CK-1", "standard"),
    ("standard-float", fm_case(standard="3.0"), "CK-1", "standard"),
    ("standard-bool", fm_case(standard="true"), "CK-1", "standard"),
    ("standard-4", fm_case(standard="4"), "CK-1", "standard"),
    ("tier-lower", fm_case(tier="t1"), "CK-1", "tier"),
    ("tier-space", fm_case(tier='"T1 "'), "CK-1", "tier"),
    ("tier-missing-on-feature", fm_case(tier=None), "CK-1", "tier"),
    ("tier-on-bugfix", readme(type="bugfix", status="draft", fm={"tier": "T1"}), "CK-1", "tier"),
    ("risk-capital", fm_case(risk="[Security]"), "CK-1", "risk"),
    ("risk-unknown", fm_case(risk="[unknown]"), "CK-1", "unknown"),
    ("risk-scalar", fm_case(risk="security"), "CK-1", "risk"),
    ("risk-repeated", fm_case(risk="[data, data]"), "CK-1", "risk"),
    ("risk-missing", fm_case(risk=None), "CK-1", "risk"),
    ("duplicate-key", readme(status="draft").replace("owner: harness", "owner: harness\nowner: other"), "CK-1", "owner"),
    ("parent", fm_case(parent="other"), "CK-1", "parent"),
    ("children", fm_case(children="[a]"), "CK-1", "children"),
    ("nestTrigger", fm_case(nestTrigger="[size]"), "CK-1", "nestTrigger"),
    ("nestWhy", fm_case(nestWhy="x"), "CK-1", "nestWhy"),
    ("type-research", fm_case(type="research"), "CK-1", "type"),
    ("layers-not-none", fm_case(layers="{architecture: added, component: none, functional: none, data: none}"), "CK-1", "layers"),
    ("tier-without-standard", readme(status="draft").replace("standard: 3\n", ""), "CK-1", "tier"),
    ("risk-without-standard", readme(status="draft", fm={"tier": None}).replace("standard: 3\n", ""), "CK-1", "risk"),
]


@pytest.mark.parametrize("name,text,rule,key", LOOKALIKES, ids=[c[0] for c in LOOKALIKES])
def test_ac2_each_lookalike_or_unknown_form_is_refused_by_rule_and_key(tmp_path: Path, name: str, text: str, rule: str,
                                                                        key: str) -> None:
    # spec-standard-v3/AC-2
    errors = check(tmp_path, text)
    assert has(errors, rule, key), show(errors)


def test_ac2_a_layer_file_beside_a_v3_readme_is_ck3(tmp_path: Path) -> None:
    # spec-standard-v3/AC-2
    errors = check(tmp_path, readme(status="draft"), files={f"{ITEM}/architecture.md": "# x\n"})
    assert has(errors, "CK-3", "architecture.md"), show(errors)


def test_ac2_duplicate_key_check_applies_only_to_standard_3_items(tmp_path: Path) -> None:
    # spec-standard-v3/AC-2 (and AC-1: a v2 item keeps judging as before)
    v2 = ("---\nid: demo\ntype: research\nstatus: draft\ntouches: [x]\nlayers: {architecture: none, component: none, "
          "functional: none, data: none}\ncreated: \"2026-11-02\"\nowner: a\nowner: b\n---\n# Demo\n")
    assert not any("duplicate" in e for e in check(tmp_path, v2))


def test_ac2_read_v3_returns_the_fields_and_none_for_a_v2_text() -> None:
    # spec-standard-v3/AC-2
    v3 = work_item_schema.read_v3(readme(tier="T2", risk=("data", "security")))
    assert (v3.type, v3.standard, v3.tier, v3.risk, v3.status) == ("feature", 3, "T2", ["data", "security"], "spec-locked")
    assert work_item_schema.read_v3(readme(type="bugfix")).tier is None
    assert work_item_schema.read_v3(readme().replace("standard: 3\n", "").replace("tier: T1\n", "").replace("risk: []\n", "")) is None


def test_ac2_checker_gate_and_review_record_all_call_read_v3(tmp_path: Path, monkeypatch) -> None:
    # spec-standard-v3/AC-2
    calls: list[str] = []
    real = work_item_schema.read_v3

    def counting(text):
        calls.append("x")
        return real(text)

    monkeypatch.setattr(work_item_schema, "read_v3", counting)
    text = readme(status="building")
    check(tmp_path, text)
    after_checker = len(calls)
    assert after_checker >= 1
    sv3().frozen_set_problem(text, text)
    after_gate = len(calls)
    assert after_gate > after_checker
    repo = gate_repo(tmp_path)
    seed(repo, readme(status="draft"))
    git(repo, "add", "-A")
    review_record.required_records(spec_check.IndexTree(repo), ITEM, [["draft", "spec-locked"]])
    assert len(calls) > after_gate


# ---------------------------------------------------------------- AC-3: the computed tier

@pytest.mark.parametrize("n,declared,ok", [(5, "T1", True), (6, "T1", False), (6, "T2", True), (15, "T2", True)])
def test_ac3_ac_count_sets_the_computed_tier(tmp_path: Path, n: int, declared: str, ok: bool) -> None:
    # spec-standard-v3/AC-3
    errors = check(tmp_path, readme(tier=declared, n_acs=n), n_acs=n)
    if ok:
        assert errors == [], show(errors)
    else:
        assert has(errors, "CK-V3-TIER", "computed tier is T2", f"{n} ACs"), show(errors)


def test_ac3_sixteen_acs_is_a_split_error(tmp_path: Path) -> None:
    # spec-standard-v3/AC-3
    errors = check(tmp_path, readme(tier="T2", n_acs=16), n_acs=16)
    assert has(errors, "CK-V3-TIER", "split"), show(errors)


@pytest.mark.parametrize("flag", FLAGS)
def test_ac3_each_flag_makes_t2(tmp_path: Path, flag: str) -> None:
    # spec-standard-v3/AC-3
    low = check(tmp_path, readme(tier="T1", risk=(flag,)))
    assert has(low, "CK-V3-TIER", f"`{flag}`"), show(low)
    assert check(tmp_path, readme(tier="T2", risk=(flag,))) == []


def test_ac3_a_higher_declared_tier_passes(tmp_path: Path) -> None:
    # spec-standard-v3/AC-3
    assert check(tmp_path, readme(tier="T2")) == []


def test_ac3_live_comes_from_claude_md_whatever_risk_says(tmp_path: Path) -> None:
    # spec-standard-v3/AC-3
    live = "# Repo\n\n`deploymentTier: live`\n"
    errors = check(tmp_path, readme(tier="T1", risk=()), claude_md=live)
    assert has(errors, "CK-V3-TIER", "`live`"), show(errors)
    assert check(tmp_path, readme(tier="T2", risk=(), live=True), claude_md=live) == []
    assert check(tmp_path, readme(tier="T1", risk=()), claude_md="# Repo\n\ndeploymentTier: pre-traffic\n") == []
    assert check(tmp_path, readme(tier="T1", risk=())) == [], "a missing CLAUDE.md means not live"


@pytest.mark.parametrize("text,live", [
    ("deploymentTier: live\n", True),
    ("Prose first: `deploymentTier: live`.\n", True),
    ("deploymentTier: live   (owner-promoted 2026-10-31)\n", True),
    ("- deploymentTier: live\n", True),
    ("Never set deploymentTier: live without approval.\n", False),
    ("```\ndeploymentTier: live\n```\n", False),
    ("~~~md\ndeploymentTier: live\n~~~\n", False),
    ("deploymentTier: live-later\n", False),
    ("deploymentTier: live_x\n", False),
    ("deploymentTier: pre-traffic  # was live\n", False),
    ("# deploymentTier: live\n", False),
    ("<!-- deploymentTier: live -->\n", False),
    ("deploymentTier:\n", False),
    ("", False),
    (None, False),
])
def test_ac3_live_reader_refuses_lookalikes(text: str | None, live: bool) -> None:
    # spec-standard-v3/AC-3
    assert sv3().live_of(text) is live


# ---------------------------------------------------------------- AC-4: sections

SECTION_CASES = [
    ("feature-T1", dict(), ["Purpose", "Goals and non-goals", "Behaviour", "Outcomes"]),
    ("feature-T2", dict(tier="T2"), ["Purpose", "Goals and non-goals", "Behaviour", "Outcomes", "Approach", "Assumptions", "Probe"]),
    ("feature-T2-contract", dict(tier="T2", risk=("contract",)),
     ["Purpose", "Goals and non-goals", "Behaviour", "Outcomes", "Approach", "Assumptions", "Probe", "Contracts"]),
    ("bugfix", dict(type="bugfix"), ["Symptom", "Reproduce", "Expected", "Actual", "Must not change", "Root cause"]),
    ("bugfix-flagged", dict(type="bugfix", risk=("data",)),
     ["Symptom", "Reproduce", "Expected", "Actual", "Must not change", "Root cause", "Probe"]),
]
SECTION_PAIRS = [(case, title) for case in SECTION_CASES for title in case[2]]


@pytest.mark.parametrize("case,title", SECTION_PAIRS, ids=[f"{c[0]}:{t}" for c, t in SECTION_PAIRS])
def test_ac4_a_missing_required_section_is_named_at_spec_locked_and_free_at_draft(tmp_path: Path, case, title: str) -> None:
    # spec-standard-v3/AC-4
    _, kw, required = case
    n = 1 if kw.get("type") else 2
    assert check(tmp_path, readme(**kw), n_acs=n) == []
    locked = check(tmp_path, readme(drop=(title,), **kw), n_acs=n)
    assert has(locked, "CK-4", f"`## {title}`"), show(locked)
    assert check(tmp_path, readme(status="draft", drop=(title,), **kw), n_acs=n) == []


@pytest.mark.parametrize("heading,wrong", [("Behaviour", "Behaviours"), ("Assumptions", "Assumption"),
                                          ("Goals and non-goals", "Goals and Non Goals")])
def test_ac4_a_lookalike_heading_does_not_satisfy_a_required_one(tmp_path: Path, heading: str, wrong: str) -> None:
    # spec-standard-v3/AC-4
    text = readme(tier="T2").replace(f"## {heading}", f"## {wrong}")
    errors = check(tmp_path, text)
    assert has(errors, "CK-4", f"`## {heading}`"), show(errors)


def test_ac4_the_diagram_before_the_first_h2_is_required(tmp_path: Path) -> None:
    # spec-standard-v3/AC-4 (SPEC-STANDARD-V3 section table: diagram, all)
    errors = check(tmp_path, readme(diagram=False))
    assert has(errors, "CK-6", "mermaid"), show(errors)
    assert check(tmp_path, readme(diagram=False, status="draft")) == []


def test_ac4_purpose_length_and_goal_counts_are_advisory(tmp_path: Path) -> None:
    # spec-standard-v3/AC-4 (advisory content limits are not checker rules)
    long = "\n".join(f"line {i}" for i in range(12))
    assert check(tmp_path, readme(body={"Purpose": long, "Goals and non-goals": "- one"})) == []


# ---------------------------------------------------------------- AC-5: the AC table

def test_ac5_exactly_one_table_with_the_exact_header_reads(tmp_path: Path) -> None:
    # spec-standard-v3/AC-5
    assert check(tmp_path, readme()) == []


def test_ac5_a_second_table_in_behaviour_is_refused(tmp_path: Path) -> None:
    # spec-standard-v3/AC-5
    errors = check(tmp_path, readme(body={"Behaviour": ac_table(2) + "\n\nnotes\n\n| a | b |\n|---|---|\n| 1 | 2 |"}))
    assert has(errors, "CK-11", "Behaviour", "exactly one table"), show(errors)


def test_ac5_a_header_differing_by_one_word_is_refused(tmp_path: Path) -> None:
    # spec-standard-v3/AC-5
    errors = check(tmp_path, readme(body={"Behaviour": ac_table(2).replace("Pass when", "Passes when")}))
    assert has(errors, "CK-11", "header"), show(errors)


def test_ac5_a_duplicate_ac_id_is_refused(tmp_path: Path) -> None:
    # spec-standard-v3/AC-5
    errors = check(tmp_path, readme(body={"Behaviour": ac_table(2).replace("AC-2", "AC-1")}))
    assert has(errors, "CK-11", "duplicate AC-1"), show(errors)


def test_ac5_a_feature_needs_at_least_one_ac(tmp_path: Path) -> None:
    # spec-standard-v3/AC-5 (SPEC-STANDARD-V3 definition of ready: 1-15 rows)
    errors = check(tmp_path, readme(body={"Behaviour": AC_HEADER}), n_acs=0)
    assert has(errors, "CK-11", "no AC-n rows"), show(errors)


@pytest.mark.parametrize("rows,ok", [(3, True), (4, False)])
def test_ac5_a_bugfix_has_one_to_three_rows(tmp_path: Path, rows: int, ok: bool) -> None:
    # spec-standard-v3/AC-5
    errors = check(tmp_path, readme(type="bugfix", n_acs=rows), n_acs=rows)
    if ok:
        assert errors == [], show(errors)
    else:
        assert has(errors, "CK-11", "a spec change, not a bug"), show(errors)


def test_ac5_traces_is_free_text_in_a_v3_ac_table(tmp_path: Path) -> None:
    # spec-standard-v3/AC-5 (build amendment: v3 has no CAP table, so v2's "Traces `-`" restriction does not apply)
    assert check(tmp_path, readme(body={"Behaviour": ac_table(2).replace("CAP-1", "-")})) == []


# ---------------------------------------------------------------- AC-6: the Outcomes table

def outcomes_text(**kw) -> str:
    return readme(body={"Outcomes": outcome_table(**kw)})


def swap_row(table: str, dim: str, new_row: str) -> str:
    return "\n".join(new_row if line.startswith(f"| {dim} |") else line for line in table.splitlines())


def test_ac6_a_valid_twelve_row_table_reads(tmp_path: Path) -> None:
    # spec-standard-v3/AC-6
    assert check(tmp_path, readme()) == []


OUTCOME_FAULTS = [
    ("missing-dimension", lambda t: "\n".join(l for l in t.splitlines() if not l.startswith("| timeout |")), ["timeout"]),
    ("duplicated-dimension", lambda t: t + "\n| timeout | L1 | cannot occur here either | - |", ["timeout", "more than once"]),
    ("misspelled-dimension", lambda t: t.replace("| invalid input |", "| Invalid Input |"), ["Invalid Input"]),
    ("level-L4", lambda t: swap_row(t, "timeout", "| timeout | L4 | cannot occur in this check | - |"), ["L4"]),
    ("level-lowercase", lambda t: swap_row(t, "timeout", "| timeout | l3 | asserted | AC-1 |"), ["l3"]),
    ("level-lookalike", lambda t: swap_row(t, "timeout", "| timeout | L3. | asserted | AC-1 |"), ["L3."]),
    ("L3-names-missing-ac", lambda t: swap_row(t, "timeout", "| timeout | L3 | asserted | AC-9 |"), ["AC-9"]),
    ("L3-names-no-ac", lambda t: swap_row(t, "timeout", "| timeout | L3 | asserted | - |"), ["timeout", "AC"]),
    ("L1-reason-na", lambda t: swap_row(t, "timeout", "| timeout | L1 | n/a | - |"), ["timeout", "reason"]),
    ("L1-reason-tbd", lambda t: swap_row(t, "timeout", "| timeout | L1 | tbd | - |"), ["timeout", "reason"]),
    ("L1-reason-two-words", lambda t: swap_row(t, "timeout", "| timeout | L1 | no wait | - |"), ["timeout", "3 words"]),
    ("L1-reason-not-applicable", lambda t: swap_row(t, "timeout", "| timeout | L1 | not applicable | - |"), ["timeout", "reason"]),
    ("second-table", lambda t: t + "\n\nnotes\n\n| a | b |\n|---|---|\n| 1 | 2 |", ["Outcomes", "exactly one table"]),
    ("wrong-header", lambda t: t.replace("Row or n/a reason", "Reason"), ["header"]),
]


@pytest.mark.parametrize("name,fault,needles", OUTCOME_FAULTS, ids=[c[0] for c in OUTCOME_FAULTS])
def test_ac6_each_lookalike_outcomes_table_is_refused_with_a_specific_message(tmp_path: Path, name, fault, needles) -> None:
    # spec-standard-v3/AC-6
    errors = check(tmp_path, readme(body={"Outcomes": fault(outcome_table())}))
    assert has(errors, "CK-V3-OUT", *needles), show(errors)


def test_ac6_outcomes_is_a_feature_only_section(tmp_path: Path) -> None:
    # spec-standard-v3/AC-6
    assert check(tmp_path, readme(type="bugfix", body={"Outcomes": "stray text"})) == []


# ---------------------------------------------------------------- AC-7: thresholds from spec-locked

def test_ac7_t1_needs_success_and_invalid_input_at_l3(tmp_path: Path) -> None:
    # spec-standard-v3/AC-7
    for dim in ("success", "invalid input"):
        text = readme(levels={dim: ("L2", "stated in prose here", "-")})
        errors = check(tmp_path, text)
        assert has(errors, "CK-V3-OUT", f"`{dim}`", "T1", "L3"), show(errors)
        assert check(tmp_path, readme(status="draft", levels={dim: ("L2", "stated in prose here", "-")})) == []


def test_ac7_t2_allows_no_l2_row(tmp_path: Path) -> None:
    # spec-standard-v3/AC-7
    errors = check(tmp_path, readme(tier="T2", levels={"timeout": ("L2", "stated in prose here", "-")}))
    assert has(errors, "CK-V3-OUT", "`timeout`", "T2", "L2"), show(errors)
    assert check(tmp_path, readme(status="draft", tier="T2", levels={"timeout": ("L2", "stated in prose here", "-")})) == []


@pytest.mark.parametrize("flag", FLAGS)
def test_ac7_each_flag_forces_its_dimensions_to_l3(tmp_path: Path, flag: str) -> None:
    # spec-standard-v3/AC-7
    dim = FLAG_MAP[flag][0]
    errors = check(tmp_path, readme(tier="T2", risk=(flag,), levels={dim: ("L2", "stated in prose here", "-")}))
    assert has(errors, "CK-V3-OUT", f"`{dim}`", f"flag `{flag}`"), show(errors)
    assert check(tmp_path, readme(status="draft", tier="T2", risk=(flag,), levels={dim: ("L2", "stated in prose", "-")})) == []


def test_ac7_the_flag_map_in_the_contract_is_the_documented_one() -> None:
    # spec-standard-v3/AC-7
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["flag_to_dimensions"] == FLAG_MAP
    assert contract["$defs"]["flag"]["enum"] == FLAGS and contract["$defs"]["dimension"]["enum"] == DIMS
    assert contract["$defs"]["level"]["enum"] == ["L1", "L2", "L3"]


# ---------------------------------------------------------------- AC-8: bugfix MNC, amendments, citations

def bugfix(**kw) -> str:
    return readme(type="bugfix", **kw)


MNC_FAULTS = [
    ("no-table", "no rows at all", ["Must not change"]),
    ("header", "| ID | Must not change |\n|---|---|\n| MNC-1 | x |", ["header"]),
    ("bad-id", "| ID | Must not change | Test |\n|---|---|---|\n| MNC-x | x | tests/test_demo.py |", ["MNC-x"]),
    ("zero-rows", "| ID | Must not change | Test |\n|---|---|---|", ["at least 1 row"]),
    ("empty-test", "| ID | Must not change | Test |\n|---|---|---|\n| MNC-1 | x |  |", ["MNC-1"]),
]


@pytest.mark.parametrize("name,table,needles", MNC_FAULTS, ids=[c[0] for c in MNC_FAULTS])
def test_ac8_a_bad_must_not_change_table_is_refused(tmp_path: Path, name, table, needles) -> None:
    # spec-standard-v3/AC-8
    errors = check(tmp_path, bugfix(body={"Must not change": table}))
    assert has(errors, "CK-V3-BUG", *needles), show(errors)


def test_ac8_build_amendments_need_a_test_in_every_row(tmp_path: Path) -> None:
    # spec-standard-v3/AC-8
    header = "| Change | Why (what the test exposed) | Test |\n|---|---|---|"
    good = check(tmp_path, readme(extra=f"\n## Build amendments\n\n{header}\n| a change | a reason | tests/test_demo.py |\n"))
    assert good == [], show(good)
    errors = check(tmp_path, readme(extra=f"\n## Build amendments\n\n{header}\n| a change | a reason |  |\n"))
    assert has(errors, "CK-V3-DOC", "Build amendments", "Test"), show(errors)
    errors = check(tmp_path, readme(extra="\n## Build amendments\n\n| Change | Why |\n|---|---|\n| a | b |\n"))
    assert has(errors, "CK-V3-DOC", "Build amendments", "header"), show(errors)


def test_ac8_at_building_a_test_must_cite_each_ac(tmp_path: Path) -> None:
    # spec-standard-v3/AC-8 (the AC-n citation, CK-20 as in v2)
    errors = check(tmp_path, readme(status="building"), tests="# demo/AC-1\n")
    assert has(errors, "CK-20", "demo/AC-2"), show(errors)
    assert check(tmp_path, readme(status="building"), tests=cites(2)) == []
    assert check(tmp_path, readme(status="spec-locked"), tests="# nothing\n") == [], "citations are required from building"


def test_ac8_at_building_a_test_must_cite_each_mnc(tmp_path: Path) -> None:
    # spec-standard-v3/AC-8
    errors = check(tmp_path, bugfix(status="building"), tests="# demo/AC-1\n")
    assert has(errors, "CK-20", "demo/MNC-1"), show(errors)
    assert check(tmp_path, bugfix(status="building"), tests="# demo/AC-1\n# demo/MNC-1\n") == []
    assert check(tmp_path, bugfix(status="spec-locked"), tests="# nothing\n") == []


# ---------------------------------------------------------------- AC-9: Assumptions, Probe, markers

def t2(**kw) -> str:
    return readme(tier="T2", **kw)


def assumptions(row: str) -> str:
    return "| Assumption | Observed | If violated |\n|---|---|---|\n" + row


@pytest.mark.parametrize("violated", ["retry", "retry: again", "keep:", ""])
def test_ac9_a_bad_if_violated_is_refused(tmp_path: Path, violated: str) -> None:
    # spec-standard-v3/AC-9
    errors = check(tmp_path, t2(body={"Assumptions": assumptions(f"| a | `src/a.py:3` | {violated} |")}))
    assert has(errors, "CK-V3-DOC", "Assumptions"), show(errors)


def test_ac9_an_unresolved_citation_is_refused_and_a_resolved_one_reads(tmp_path: Path) -> None:
    # spec-standard-v3/AC-9
    errors = check(tmp_path, t2(body={"Assumptions": assumptions("| a | `src/a.py:99999` | keep: fine |")}))
    assert has(errors, "CK-V3-DOC", "src/a.py:99999"), show(errors)
    assert check(tmp_path, t2(body={"Assumptions": assumptions("| a | `src/a.py:3` | keep: fine |")})) == []


@pytest.mark.parametrize("observed", ["3.5:1 ratio", "v1.2:3 pinned", "127.0.0.1:8080 answers", "the ratio is 3:1"])
def test_ac9_lookalikes_of_a_citation_are_not_read_as_one(tmp_path: Path, observed: str) -> None:
    # spec-standard-v3/AC-9
    assert check(tmp_path, t2(body={"Assumptions": assumptions(f"| a | {observed} | keep: fine |")})) == []


def test_ac9_a_windows_shaped_absolute_citation_resolves(tmp_path: Path) -> None:
    # spec-standard-v3/AC-9
    cited = tmp_path / "elsewhere" / "y.py"
    write(tmp_path, "elsewhere/y.py", "\n".join(str(i) for i in range(30)) + "\n")
    ok = check(tmp_path, t2(body={"Assumptions": assumptions(f"| a | `{cited.as_posix()}:12` | keep: fine |")}))
    assert ok == [], show(ok)
    errors = check(tmp_path, t2(body={"Assumptions": assumptions("| a | `C:/nonexistent_zz/y.py:12` | keep: fine |")}))
    assert has(errors, "CK-V3-DOC", "C:/nonexistent_zz/y.py:12", "does not exist"), show(errors)


@pytest.mark.parametrize("probe,ok", [("[p](evidence/probe.md)", True), ("[p](evidence/missing.md)", False),
                                      ("[p](README.md)", False), ("[p](../other/evidence/probe.md)", False),
                                      ("[p](https://example.com/probe.md)", False), ("no link here", False)])
def test_ac9_probe_links_an_existing_file_under_evidence(tmp_path: Path, probe: str, ok: bool) -> None:
    # spec-standard-v3/AC-9
    errors = check(tmp_path, t2(body={"Probe": probe}))
    if ok:
        assert errors == [], show(errors)
    else:
        assert has(errors, "CK-V3-DOC", "Probe"), show(errors)


@pytest.mark.parametrize("prose,bad", [("Open: [NEEDS CLARIFICATION: who owns it]", True), ("Owner is TBD for now.", True),
                                       ("The value `TBD` is a literal.", False), ("The TBDs list is long.", False),
                                       ("```\nTBD in a fence\n```", False)])
def test_ac9_open_markers_are_refused_from_spec_locked_and_free_at_draft(tmp_path: Path, prose: str, bad: bool) -> None:
    # spec-standard-v3/AC-9
    errors = check(tmp_path, readme(body={"Purpose": prose}))
    if bad:
        assert has(errors, "CK-V3-DOC", "open"), show(errors)
    else:
        assert errors == [], show(errors)
    assert check(tmp_path, readme(status="draft", body={"Purpose": prose})) == []


# ---------------------------------------------------------------- AC-14 (part): rule ids are registered in the tiers

def test_ac14_every_new_rule_id_is_registered_in_the_status_tiers() -> None:
    # spec-standard-v3/AC-8 (Report.err cannot drop a rule that no tier enables)
    ids = set(re.findall(r'"(CK-V3[A-Z-]*)"', (CLAUDE / "scripts" / "spec_v3.py").read_text(encoding="utf-8")))
    assert {"CK-V3-TIER", "CK-V3-OUT", "CK-V3-BUG", "CK-V3-DOC"} <= ids
    assert '"CK-V3"' in (CLAUDE / "scripts" / "spec_check.py").read_text(encoding="utf-8")
    assert "CK-V3" in spec_check.TIERS["draft"]
    for rule in ids - {"CK-V3"}:
        assert rule in spec_check.TIERS["spec-locked"] and rule not in spec_check.TIERS["draft"], rule
    assert ids <= spec_check.TIERS["building"] and ids <= spec_check.TIERS["shipped"]


# ---------------------------------------------------------------- gate scaffolding (AC-10 to AC-13)

def gate_repo(tmp_path: Path, claude: Path = CLAUDE, claude_md: str | None = None) -> Path:
    gate = claude / "scripts" / "spec_gate.py"
    r = tmp_path / "repo"
    git(tmp_path, "init", "-q", "-b", "main", str(r))
    hooks = tmp_path / "hooks"
    hooks.mkdir(exist_ok=True)
    (hooks / "commit-msg").write_text(f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "{gate.as_posix()}" "$1"\n',
                                      encoding="utf-8", newline="\n")
    git(r, "config", "core.hooksPath", hooks.as_posix())
    write(r, "tests/test_demo.py", cites(16, 2))
    write(r, "src/a.py", "\n".join(f"line {i}" for i in range(1, 21)) + "\n")
    write(r, f"{ITEM}/evidence/probe.md", "# probe\n")
    if claude_md is not None:
        write(r, "CLAUDE.md", claude_md)
    git(r, "add", "-A")
    git(r, "commit", "-qm", "chore: init", "--no-verify")
    return r


def seed(repo: Path, text: str, rel: str = README) -> None:
    """Commit `text` as the README without the hook, so it becomes the HEAD state."""
    write(repo, rel, text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "chore: seed", "--no-verify", "--allow-empty")


def land(repo: Path, text: str, *, record: str | None = None, rel: str = README, msg: str = "docs: move") -> subprocess.CompletedProcess:
    """Stage `text` (and a fresh review record of class `record`), then run the real commit with the hook."""
    write(repo, rel, text)
    git(repo, "add", "-A", ITEM)
    if record:
        stage_record(repo, record)
    return commit(repo, "-m", msg)


def refused(r: subprocess.CompletedProcess, *needles: str) -> None:
    assert r.returncode != 0, f"the commit landed; expected a refusal with {needles}"
    assert all(n in r.stderr for n in needles), r.stderr


# ---------------------------------------------------------------- AC-10: the lock edge

def test_ac10_a_t2_feature_lock_without_a_design_record_is_refused(tmp_path: Path) -> None:
    # spec-standard-v3/AC-10
    repo = gate_repo(tmp_path)
    seed(repo, readme(status="draft", tier="T2"))
    refused(land(repo, readme(tier="T2")), "needs a fresh design review")


def test_ac10_a_flagged_bugfix_lock_without_a_design_record_is_refused(tmp_path: Path) -> None:
    # spec-standard-v3/AC-10
    repo = gate_repo(tmp_path)
    seed(repo, bugfix(status="draft", risk=("data",)))
    refused(land(repo, bugfix(risk=("data",))), "needs a fresh design review")


def test_ac10_a_t2_lock_with_a_fresh_design_record_lands(tmp_path: Path) -> None:
    # spec-standard-v3/AC-10
    repo = gate_repo(tmp_path)
    seed(repo, readme(status="draft", tier="T2"))
    r = land(repo, readme(tier="T2"), record="design")
    assert r.returncode == 0, r.stderr


def test_ac10_a_t1_feature_and_an_unflagged_bugfix_lock_on_the_mechanical_check(tmp_path: Path) -> None:
    # spec-standard-v3/AC-10
    for text_draft, text_lock in ((readme(status="draft"), readme()), (bugfix(status="draft"), bugfix())):
        sub = tmp_path / str(len(list(tmp_path.iterdir())))
        sub.mkdir()
        repo = gate_repo(sub)
        seed(repo, text_draft)
        r = land(repo, text_lock)
        assert r.returncode == 0, r.stderr


def test_ac10_a_v2_feature_lock_still_needs_the_design_record(tmp_path: Path) -> None:
    # spec-standard-v3/AC-10 (FR-10: v2 items are unchanged)
    repo = gate_repo(tmp_path)
    v2 = ("---\nid: demo\ntype: feature\nstatus: spec-locked\ntouches: [x]\nlayers: {architecture: none, component: added, "
          "functional: added, data: none}\ncreated: \"2026-11-02\"\nowner: a\n---\n# Demo\n")
    write(repo, README, v2)
    git(repo, "add", "-A")
    why = review_record.required_records(spec_check.IndexTree(repo), ITEM, [["draft", "spec-locked"]])
    assert why and "needs a fresh design review" in why


def test_ac10_the_lock_rule_uses_the_computed_tier_not_the_declaration(tmp_path: Path) -> None:
    # spec-standard-v3/AC-10 (design finding 4: tested on required_records, since the checker refuses this item first)
    repo = gate_repo(tmp_path)
    seed(repo, readme(status="draft", tier="T1", n_acs=6))
    write(repo, README, readme(tier="T1", n_acs=6))
    git(repo, "add", "-A")
    why = review_record.required_records(spec_check.IndexTree(repo), ITEM, [["draft", "spec-locked"]])
    assert why and "needs a fresh design review" in why
    refused(land(repo, readme(tier="T1", n_acs=6)), "not committable")


def test_ac10_a_declared_t2_on_a_two_ac_feature_still_needs_the_record(tmp_path: Path) -> None:
    # spec-standard-v3/AC-10 (build amendment: the effective tier is the higher of declared and computed)
    repo = gate_repo(tmp_path)
    write(repo, README, readme(tier="T2"))
    git(repo, "add", "-A")
    why = review_record.required_records(spec_check.IndexTree(repo), ITEM, [["draft", "spec-locked"]])
    assert why and "needs a fresh design review" in why


@pytest.mark.parametrize("text", [readme(fm={"standard": '"3"'}), readme(body={"Behaviour": "no table at all"}),
                                  bugfix(body={"Expected": "no table at all"}),
                                  readme(fm={"tier": "T9"}), "no frontmatter at all\n"],
                         ids=["lookalike-standard", "no-ac-table", "bugfix-no-ac-table", "bad-tier", "no-frontmatter"])
def test_ac10_required_records_fails_closed_on_an_unreadable_item(tmp_path: Path, text: str) -> None:
    # spec-standard-v3/AC-10 (design finding 4)
    repo = gate_repo(tmp_path)
    write(repo, README, text)
    git(repo, "add", "-A")
    why = review_record.required_records(spec_check.IndexTree(repo), ITEM, [["draft", "spec-locked"]])
    assert why and "needs a fresh design review" in why


def test_ac10_the_live_flag_makes_a_t1_lock_need_a_record_and_is_read_from_the_argument_or_the_tree(tmp_path: Path) -> None:
    # spec-standard-v3/AC-10
    repo = gate_repo(tmp_path, claude_md="deploymentTier: live\n")
    write(repo, README, readme(tier="T1"))
    git(repo, "add", "-A")
    tree = spec_check.IndexTree(repo)
    assert "needs a fresh design review" in (review_record.required_records(tree, ITEM, [["draft", "spec-locked"]]) or "")
    clean = tmp_path / "clean"
    clean.mkdir()
    repo2 = gate_repo(clean)
    write(repo2, README, readme(tier="T1"))
    git(repo2, "add", "-A")
    assert review_record.required_records(spec_check.IndexTree(repo2), ITEM, [["draft", "spec-locked"]]) is None
    assert "needs a fresh design review" in (review_record.required_records(spec_check.IndexTree(repo2), ITEM,
                                                                           [["draft", "spec-locked"]], live=True) or "")


def test_ac10_a_t1_lock_in_a_live_repo_needs_the_design_record_and_the_live_flag_comes_from_head(tmp_path: Path) -> None:
    # spec-standard-v3/AC-10 (design finding 3)
    repo = gate_repo(tmp_path, claude_md="deploymentTier: live\n")
    seed(repo, readme(status="draft", tier="T2", live=True))
    refused(land(repo, readme(tier="T2", live=True)), "needs a fresh design review")
    # a commit that drops the live line while locking a T1 item, with a fresh record so that only the checker can refuse
    # it, is judged by HEAD's CLAUDE.md
    seed(repo, readme(status="draft", tier="T1"))
    write(repo, "CLAUDE.md", "deploymentTier: pre-traffic\n")
    git(repo, "add", "CLAUDE.md")
    refused(land(repo, readme(tier="T1"), record="design"), "`live`")


def test_ac10_a_stale_design_record_copied_in_after_the_item_grew_is_refused(tmp_path: Path) -> None:
    # spec-standard-v3/AC-10 (an old record replayed)
    repo = gate_repo(tmp_path)
    seed(repo, readme(status="draft", tier="T2"))
    write(repo, README, readme(tier="T2"))
    git(repo, "add", "-A", ITEM)
    stage_record(repo, "design")
    write(repo, README, readme(tier="T2", body={"Purpose": "The text changed after the review."}))
    git(repo, "add", "-A", ITEM)
    refused(commit(repo, "-m", "docs: lock"), "stale")


def test_ac10_a_ship_needs_a_code_record_for_a_v3_t1_feature(tmp_path: Path) -> None:
    # spec-standard-v3/AC-10
    repo = gate_repo(tmp_path)
    seed(repo, readme(status="building"))
    refused(land(repo, readme(status="shipped")), "needs a fresh code review")
    r = land(repo, readme(status="shipped"), record="code")
    assert r.returncode == 0, r.stderr


def test_ac10_a_git_error_while_reading_refuses(tmp_path: Path) -> None:
    # spec-standard-v3/AC-10
    repo = gate_repo(tmp_path)
    seed(repo, readme(status="draft"))
    write(repo, README, readme())
    git(repo, "add", "-A")
    msg = tmp_path / "msg.txt"
    msg.write_text("docs: lock\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(GATE), str(msg)], cwd=repo, capture_output=True, text=True, timeout=60,
                       env={**ENV, "GIT_INDEX_FILE": str(tmp_path / "no-such-index")})
    assert r.returncode == 1 and "fails closed" in r.stderr, r.stderr


def test_ac10_a_v3_item_that_stays_in_its_status_is_still_judged(tmp_path: Path) -> None:
    # spec-standard-v3/AC-10 (build amendment: the v2 "historical" pardon for a README without References never applies to v3)
    repo = gate_repo(tmp_path)
    seed(repo, readme(status="building"))
    refused(land(repo, readme(status="building", body={"Behaviour": "the table is gone"})), "not committable")


# ---------------------------------------------------------------- AC-11: the frozen set

def stat(text: str, status: str) -> str:
    return re.sub(r"^status: .*$", f"status: {status}", text, count=1, flags=re.M)


HEAD_STATUSES = ["spec-locked", "building", "shipped"]
LOWERINGS = {
    "tier-lowered": (readme(tier="T2"), readme(tier="T1"), "`tier`"),
    "flag-removed": (readme(tier="T2", risk=("data", "security")), readme(tier="T2", risk=("data",)), "`risk`"),
    "type-changed": (readme(), bugfix(), "`type`"),
    "standard-deleted": (readme(), readme().replace("standard: 3\n", "").replace("tier: T1\n", "").replace("risk: []\n", ""),
                         "`standard`"),
    "v2-gains-standard": (readme().replace("standard: 3\n", "").replace("tier: T1\n", "").replace("risk: []\n", ""),
                          readme(), "`standard`"),
}


@pytest.mark.parametrize("status", HEAD_STATUSES)
@pytest.mark.parametrize("name", list(LOWERINGS))
def test_ac11_a_frozen_key_cannot_change_past_draft(name: str, status: str) -> None:
    # spec-standard-v3/AC-11
    head, staged, key = LOWERINGS[name]
    why = sv3().frozen_set_problem(stat(head, status), stat(staged, status))
    assert why and key in why, why


@pytest.mark.parametrize("status", HEAD_STATUSES)
def test_ac11_a_reorder_is_no_change_and_a_raise_is_not_a_freeze_problem(status: str) -> None:
    # spec-standard-v3/AC-11
    a = stat(readme(tier="T2", risk=("data", "security")), status)
    b = stat(readme(tier="T2", risk=("security", "data")), status)
    assert sv3().frozen_set_problem(a, b) is None and sv3().raises_scrutiny(a, b) is False
    raised = stat(readme(tier="T2", risk=("data", "security", "removal")), status)
    assert sv3().frozen_set_problem(a, raised) is None and sv3().raises_scrutiny(a, raised) is True
    tier_up = stat(readme(tier="T1"), status), stat(readme(tier="T2"), status)
    assert sv3().frozen_set_problem(*tier_up) is None and sv3().raises_scrutiny(*tier_up) is True


def test_ac11_a_repeated_flag_is_the_checkers_refusal_not_a_freeze_problem(tmp_path: Path) -> None:
    # spec-standard-v3/AC-11
    head = stat(readme(tier="T2", risk=("data",)), "building")
    repeated = stat(readme(tier="T2", risk=("data", "data")), "building")
    assert sv3().frozen_set_problem(head, repeated) is None
    assert has(check(tmp_path, repeated), "CK-1", "risk")


def test_ac11_draft_changes_freely_and_a_spec_locked_item_moved_to_draft_may_lower() -> None:
    # spec-standard-v3/AC-11
    sv = sv3()
    assert sv.frozen_set_problem(readme(status="draft", tier="T2"), readme(status="draft", tier="T1")) is None
    lowered = readme(status="draft", tier="T1")
    assert sv.frozen_set_problem(readme(status="spec-locked", tier="T2"), lowered) is None
    assert sv.frozen_set_problem(readme(status="spec-locked", tier="T2"), readme(status="draft", type="bugfix")) is not None
    assert sv.raises_scrutiny(readme(status="spec-locked", tier="T1"), readme(status="draft", tier="T2")) is False
    assert sv.raises_scrutiny(readme(status="draft", tier="T1"), readme(status="spec-locked", tier="T2")) is False


def test_ac11_an_unreadable_head_skips_the_frozen_set() -> None:
    # spec-standard-v3/AC-11 (verify 4: the repair path)
    broken = "---\nid: demo\nstatus: [oops\n---\n# x\n"
    assert sv3().frozen_set_problem(broken, readme(tier="T1")) is None


def test_ac11_a_lowering_commit_is_refused_by_the_gate_naming_the_key(tmp_path: Path) -> None:
    # spec-standard-v3/AC-11
    repo = gate_repo(tmp_path)
    seed(repo, readme(status="building", tier="T2"))
    refused(land(repo, readme(status="building", tier="T1")), "`tier`")


def test_ac11_deleting_standard_past_draft_is_refused_by_the_gate(tmp_path: Path) -> None:
    # spec-standard-v3/AC-11
    repo = gate_repo(tmp_path)
    seed(repo, readme(status="building"))
    stripped = readme(status="building").replace("standard: 3\n", "").replace("tier: T1\n", "").replace("risk: []\n", "")
    refused(land(repo, stripped), "`standard`")


def test_ac11_a_raise_during_building_needs_a_fresh_design_record(tmp_path: Path) -> None:
    # spec-standard-v3/AC-11 (design finding 1)
    repo = gate_repo(tmp_path)
    seed(repo, readme(status="building"))
    raised = readme(status="building", tier="T2", n_acs=6)
    refused(land(repo, raised), "needs a fresh design review")
    r = land(repo, raised, record="design")
    assert r.returncode == 0, r.stderr


def test_ac11_a_flag_added_during_building_needs_a_fresh_design_record(tmp_path: Path) -> None:
    # spec-standard-v3/AC-11
    repo = gate_repo(tmp_path)
    seed(repo, readme(status="building", tier="T2"))
    flagged = readme(status="building", tier="T2", risk=("data",))
    refused(land(repo, flagged), "needs a fresh design review")
    assert land(repo, flagged, record="design").returncode == 0


def test_ac11_a_raise_during_shipped_needs_a_record_too(tmp_path: Path) -> None:
    # spec-standard-v3/AC-11 (the synthetic lock edge is added even when no recorded state is the move's target)
    repo = gate_repo(tmp_path)
    seed(repo, readme(status="shipped"))
    refused(land(repo, readme(status="shipped", tier="T2")), "needs a fresh design review")


def test_ac11_spec_locked_back_to_draft_may_lower_the_tier_and_lands(tmp_path: Path) -> None:
    # spec-standard-v3/AC-11
    repo = gate_repo(tmp_path)
    seed(repo, readme(status="spec-locked", tier="T2"))
    r = land(repo, readme(status="draft", tier="T1"))
    assert r.returncode == 0, r.stderr


def test_ac11_spec_locked_to_draft_with_a_raise_in_the_same_commit_lands_without_a_record(tmp_path: Path) -> None:
    # spec-standard-v3/AC-11 (verify 1: the raise rule applies only when the staged status is past draft)
    repo = gate_repo(tmp_path)
    seed(repo, readme(status="spec-locked", tier="T1"))
    r = land(repo, readme(status="draft", tier="T2", n_acs=6))
    assert r.returncode == 0, r.stderr


def test_ac11_a_draft_item_changes_freely(tmp_path: Path) -> None:
    # spec-standard-v3/AC-11
    repo = gate_repo(tmp_path)
    seed(repo, readme(status="draft", tier="T2"))
    assert land(repo, readme(status="draft", type="bugfix", tier=None).replace("feature", "bugfix")).returncode == 0


def test_ac11_an_unreadable_head_frontmatter_is_judged_as_today(tmp_path: Path) -> None:
    # spec-standard-v3/AC-11 (verify 4)
    repo = gate_repo(tmp_path)
    seed(repo, "---\nid: demo\nstatus: [oops\n---\n# x\n")
    r = land(repo, readme(status="draft", tier="T2"))
    assert r.returncode == 0, r.stderr


def test_ac11_a_first_commit_at_spec_locked_has_no_head_copy_and_is_refused(tmp_path: Path) -> None:
    # spec-standard-v3/AC-11 (design finding 7: first commit or import)
    repo = gate_repo(tmp_path)
    refused(land(repo, readme(status="spec-locked", tier="T2")), "move not allowed")


SPEC_DIR = CLAUDE / "docs" / "work" / "spec-standard-v3"


def test_ac11_the_item_carries_its_build_amendments() -> None:
    # spec-standard-v3/AC-11 (the spec text the build amended: envelope citation, probe note, inventory row)
    readme_text = (SPEC_DIR / "README.md").read_text(encoding="utf-8")
    row = next(line for line in readme_text.splitlines() if "A local hook sees the commit" in line)
    assert "spec_gate.py:225-265" in row
    assert "## Build amendments" in readme_text
    assert "a raise (tier up or a flag added) during `building` with a fresh design record" in (
        SPEC_DIR / "functional.md").read_text(encoding="utf-8")
    assert "superseded by FR-11 and D41" in (SPEC_DIR / "evidence" / "probe.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------- AC-12: merge, squash, revert

def branch_lock(repo: Path, text_draft: str, text_lock: str, *, record: str | None, hook: bool) -> None:
    seed(repo, text_draft)
    git(repo, "checkout", "-q", "-b", "feat")
    write(repo, README, text_lock)
    git(repo, "add", "-A", ITEM)
    if record:
        stage_record(repo, record)
    r = commit(repo, "-m", "docs: lock") if hook else commit(repo, "-m", "docs: lock", "--no-verify")
    assert r.returncode == 0, r.stderr
    git(repo, "checkout", "-q", "main")


def test_ac12_a_merge_of_a_branch_that_locked_a_t1_item_lands(tmp_path: Path) -> None:
    # spec-standard-v3/AC-12
    repo = gate_repo(tmp_path)
    branch_lock(repo, readme(status="draft"), readme(), record=None, hook=True)
    write(repo, "notes.md", "main moved on\n")
    git(repo, "add", "-A")
    assert commit(repo, "-m", "docs: notes").returncode == 0
    r = git(repo, "merge", "--no-ff", "-q", "-m", "Merge feat", "feat", check=False)
    assert r.returncode == 0, r.stderr


def test_ac12_a_squash_of_a_t2_lock_with_its_design_record_lands(tmp_path: Path) -> None:
    # spec-standard-v3/AC-12
    repo = gate_repo(tmp_path)
    branch_lock(repo, readme(status="draft", tier="T2"), readme(tier="T2"), record="design", hook=True)
    git(repo, "merge", "--squash", "-q", "feat")
    r = commit(repo, "-m", "docs: squash")
    assert r.returncode == 0, r.stderr


def test_ac12_a_squash_of_a_t2_lock_without_the_record_is_refused_like_a_plain_commit(tmp_path: Path) -> None:
    # spec-standard-v3/AC-12
    repo = gate_repo(tmp_path)
    branch_lock(repo, readme(status="draft", tier="T2"), readme(tier="T2"), record=None, hook=False)
    git(repo, "merge", "--squash", "-q", "feat")
    refused(commit(repo, "-m", "docs: squash"), "needs a fresh design review")


def test_ac12_a_revert_of_a_lock_commit_lands(tmp_path: Path) -> None:
    # spec-standard-v3/AC-12
    repo = gate_repo(tmp_path)
    seed(repo, readme(status="draft"))
    assert land(repo, readme()).returncode == 0
    r = git(repo, "revert", "--no-edit", "HEAD", check=False)
    assert r.returncode == 0, r.stderr
    assert "status: draft" in (repo / README).read_text(encoding="utf-8")


def test_ac12_a_merge_whose_resolved_readme_lowers_the_tier_is_refused(tmp_path: Path) -> None:
    # spec-standard-v3/AC-12 (a merged README equal to neither side is judged against HEAD like a plain commit)
    repo = gate_repo(tmp_path)
    base = readme(status="spec-locked", tier="T2")
    seed(repo, base)
    git(repo, "checkout", "-q", "-b", "feat")
    write(repo, README, base.replace("tier: T2", "tier: T1"))
    git(repo, "add", "-A")
    assert commit(repo, "-m", "docs: lower", "--no-verify").returncode == 0
    git(repo, "checkout", "-q", "main")
    write(repo, README, base.replace("A small change for a small reason.", "A small change, reworded on main."))
    git(repo, "add", "-A")
    assert commit(repo, "-m", "docs: reword", "--no-verify").returncode == 0
    git(repo, "merge", "--no-ff", "--no-commit", "-q", "feat")
    refused(commit(repo, "-m", "Merge feat"), "`tier`")


def test_ac12_a_merge_of_a_gated_re_lock_that_equals_a_side_lands_even_though_it_lowers_the_tier(tmp_path: Path) -> None:
    # spec-standard-v3/AC-12 (design finding 5: the exemption reuses merged_item_equals_a_side)
    repo = gate_repo(tmp_path)
    seed(repo, readme(status="spec-locked", tier="T2"))
    git(repo, "checkout", "-q", "-b", "feat")
    assert land(repo, readme(status="draft", tier="T2")).returncode == 0
    assert land(repo, readme(status="draft", tier="T1")).returncode == 0
    assert land(repo, readme(status="spec-locked", tier="T1")).returncode == 0
    git(repo, "checkout", "-q", "main")
    write(repo, "notes.md", "main moved on\n")
    git(repo, "add", "-A")
    assert commit(repo, "-m", "docs: notes").returncode == 0
    r = git(repo, "merge", "--no-ff", "-q", "-m", "Merge feat", "feat", check=False)
    assert r.returncode == 0, r.stderr


# ---------------------------------------------------------------- AC-13 and AC-14: the contract, from a copy of the harness

def claude_copy(tmp_path: Path) -> Path:
    """A copy of scripts/ and contracts/ the test may edit (the checker and the gate derive the contract path from their own location)."""
    home = tmp_path / "claude-copy"
    shutil.copytree(CLAUDE / "scripts", home / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(CLAUDE / "contracts", home / "contracts", ignore=shutil.ignore_patterns("fixtures"))
    return home


def cli_check(home: Path, root: Path, text: str, *, n_acs: int = 2) -> subprocess.CompletedProcess:
    rel = lay_out(root, text, n_acs=n_acs)
    return subprocess.run([sys.executable, str(home / "scripts" / "spec_check.py"), str(root / rel), "--root", str(root)],
                          capture_output=True, text=True, timeout=120)


V2_DRAFT = ("---\nid: demo\ntype: research\nstatus: draft\ntouches: [x]\nlayers: {architecture: none, component: none, "
            "functional: none, data: none}\ncreated: \"2026-11-02\"\nowner: a\n---\n# Demo\n")


def corrupt(contract: Path, how: str) -> None:
    if how == "deleted":
        contract.unlink()
    elif how == "invalid-json":
        contract.write_text("{not json", encoding="utf-8")
    else:
        contract.write_text(json.dumps({"version": 1, "$defs": {"flag": {"enum": "contract"}}}), encoding="utf-8")


@pytest.mark.parametrize("how", ["deleted", "invalid-json", "fails-its-schema"])
def test_ac13_a_missing_or_corrupt_contract_refuses_v3_items_by_name_and_leaves_v2_alone(tmp_path: Path, how: str) -> None:
    # spec-standard-v3/AC-13
    home = claude_copy(tmp_path)
    intact = cli_check(home, tmp_path / "a", V2_DRAFT)
    corrupt(home / "contracts" / "work-item.v3.json", how)
    v2 = cli_check(home, tmp_path / "b", V2_DRAFT)
    assert (v2.returncode, v2.stdout) == (intact.returncode, intact.stdout) and "V3" not in v2.stdout
    v3 = cli_check(home, tmp_path / "c", readme(status="draft"))
    assert v3.returncode == 1 and "CK-V3: README.md: contract" in v3.stdout and "work-item.v3.json" in v3.stdout, v3.stdout
    assert "CK-1" not in v3.stdout.replace("CK-V3", ""), "a v3 item must not fall back to v2 rules"


def test_ac13_a_commit_with_no_v3_item_never_reads_the_contract(tmp_path: Path) -> None:
    # spec-standard-v3/AC-13
    home = claude_copy(tmp_path)
    corrupt(home / "contracts" / "work-item.v3.json", "deleted")
    repo = gate_repo(tmp_path, claude=home)
    write(repo, "notes.md", "docs only\n")
    git(repo, "add", "-A")
    assert commit(repo, "-m", "docs: notes").returncode == 0


def test_ac13_the_contract_is_loaded_once_per_process_and_only_on_the_first_v3_item(monkeypatch) -> None:
    # spec-standard-v3/AC-13, AC-14 (a lazy, cached load)
    reads: list[Path] = []
    real = Path.read_text

    def spy(self, *a, **k):
        if self.name == "work-item.v3.json":
            reads.append(self)
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", spy)
    work_item_schema.reset_contract()
    assert work_item_schema.read_v3(V2_DRAFT) is None and reads == []
    work_item_schema.read_v3(readme())
    work_item_schema.read_v3(readme())
    assert len(reads) == 1


def extended(home: Path) -> None:
    """Add a flag and a dimension and change a map entry in the copy's contract."""
    path = home / "contracts" / "work-item.v3.json"
    c = json.loads(path.read_text(encoding="utf-8"))
    c["$defs"]["flag"]["enum"].append("audit")
    c["$defs"]["dimension"]["enum"].append("latency budget")
    c["flag_to_dimensions"]["audit"] = ["latency budget"]
    c["flag_to_dimensions"]["removal"] = ["data and compatibility", "operability"]
    path.write_text(json.dumps(c, indent=2), encoding="utf-8")


def with_extra_dimension(text: str, level: str) -> str:
    row = f"| latency budget | {level} | {'asserted' if level == 'L3' else 'stated in prose'} | {'AC-1' if level == 'L3' else '-'} |"
    return text.replace("| operability |", f"{row}\n| operability |", 1)


def test_ac14_a_value_added_to_the_contract_is_accepted_and_enforced_by_the_checker(tmp_path: Path) -> None:
    # spec-standard-v3/AC-14
    home = claude_copy(tmp_path)
    extended(home)
    good = with_extra_dimension(readme(tier="T2", risk=("audit",), levels={"operability": ("L3", "asserted", "AC-1")}), "L3")
    ok = cli_check(home, tmp_path / "ok", good)
    assert ok.returncode == 0, ok.stdout
    weak = cli_check(home, tmp_path / "weak", with_extra_dimension(readme(tier="T2", risk=("audit",)), "L2"))
    assert "`latency budget`" in weak.stdout and "flag `audit`" in weak.stdout, weak.stdout
    removal = cli_check(home, tmp_path / "rem", with_extra_dimension(readme(tier="T2", risk=("removal",)), "L3"))
    assert "`operability`" in removal.stdout and "flag `removal`" in removal.stdout, removal.stdout


def test_ac14_a_value_absent_from_the_copy_is_rejected_by_the_checker(tmp_path: Path) -> None:
    # spec-standard-v3/AC-14
    home = claude_copy(tmp_path)
    path = home / "contracts" / "work-item.v3.json"
    c = json.loads(path.read_text(encoding="utf-8"))
    c["$defs"]["flag"]["enum"].remove("live")
    del c["flag_to_dimensions"]["live"]
    path.write_text(json.dumps(c), encoding="utf-8")
    out = cli_check(home, tmp_path / "x", readme(tier="T2", risk=("live",), status="draft"))
    assert "CK-1" in out.stdout and "live" in out.stdout, out.stdout


def test_ac14_the_gate_reads_flags_from_the_contract_too(tmp_path: Path) -> None:
    # spec-standard-v3/AC-14
    home = claude_copy(tmp_path)
    extended(home)
    repo = gate_repo(tmp_path, claude=home)
    head = with_extra_dimension(readme(status="building", tier="T2", risk=("audit",)), "L3")
    seed(repo, head)
    lowered = with_extra_dimension(readme(status="building", tier="T2", risk=()), "L3")
    refused(land(repo, lowered), "`risk`", "audit")


def test_ac14_no_module_outside_the_contract_keeps_a_list_of_flags_or_dimensions() -> None:
    # spec-standard-v3/AC-14, NFR-1 (scan covers .py under scripts/ and hooks/ and the contract)
    for folder in ("scripts", "hooks"):
        for path in (CLAUDE / folder).rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            flags = [f for f in FLAGS if re.search(rf"""["']{re.escape(f)}["']""", text)]
            dims = [d for d in DIMS if re.search(rf"""["']{re.escape(d)}["']""", text)]
            assert len(flags) < 4 and len(dims) < 4, f"{path.name}: {flags} {dims}"
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    enums = []

    def walk(node) -> None:
        if isinstance(node, dict):
            enums.extend(node["enum"] for _ in [0] if "enum" in node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(contract["frontmatter"])
    assert not [e for e in enums if len(set(e) & set(FLAGS + DIMS)) > 1], "the frontmatter schema must $ref the lists"
    assert "#/$defs/flag" in json.dumps(contract["frontmatter"])


# ---------------------------------------------------------------- AC-15: the docs (written by the parent session)

DOCS = Path(os.environ.get("SPEC_V3_DOCS_ROOT", CLAUDE))


def doc(rel: str) -> str:
    return (DOCS / rel).read_text(encoding="utf-8")


def test_ac15_docs_v3_standard_is_short_names_the_contract_and_every_flag() -> None:
    # spec-standard-v3/AC-15
    text = doc("skills/dark-factory/SPEC-STANDARD-V3.md")
    assert len(text.splitlines()) <= 200
    assert "contracts/work-item.v3.json" in text
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for flag in contract["$defs"]["flag"]["enum"]:
        assert f"`{flag}`" in text, flag


def test_ac15_docs_restated_flag_map_equals_the_contract() -> None:
    # spec-standard-v3/AC-15
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))["flag_to_dimensions"]
    rows = {}
    for line in doc("skills/dark-factory/SPEC-STANDARD-V3.md").splitlines():
        m = re.match(r"^\|\s*(\w+)\s*\|\s*([a-z ,-]+?)\s*\|\s*$", line)
        if m and m.group(1) in contract:
            rows[m.group(1)] = [d.strip() for d in m.group(2).split(",")]
    assert rows == contract


def test_ac15_docs_v2_standard_opens_with_a_banner_pointing_to_v3() -> None:
    # spec-standard-v3/AC-15
    assert "SPEC-STANDARD-V3.md" in "\n".join(doc("skills/dark-factory/WORK-ITEM-STANDARD.md").splitlines()[:6])


def test_ac15_docs_dispatch_playbook_has_the_tier_table_security_reviewer_and_probe() -> None:
    # spec-standard-v3/AC-15
    text = doc("playbooks/agent-dispatch.md")
    assert "T1" in text and "T2" in text and re.search(r"cap", text, re.I)
    assert re.search(r"(2\+|2 or more) flags.{0,80}security reviewer", text, re.I | re.S)
    assert re.search(r"probe first|probe.{0,60}before the draft", text, re.I | re.S)


def test_ac15_docs_reviewer_persona_files_a_missing_risk_flag_as_breaking() -> None:
    # spec-standard-v3/AC-15
    text = doc("agents/reviewer.md")
    assert re.search(r"risk flag.{0,200}breaking", text, re.I | re.S)


# ---------------------------------------------------------------- AC-1: v2 judged byte-identically (one-time corpus check)

CORPUS_ROOTS = [Path("D:/repo"), MAIN_CLAUDE]
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".next", "dist", "build", ".pnpm-store"}
MIN_ITEMS = 54


def corpus_readmes() -> list[str]:
    found: list[str] = []
    for top in CORPUS_ROOTS:
        for here, dirs, _ in os.walk(top):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".wt-") and "worktrees" not in d]
            p = Path(here)
            if p.name == "work" and p.parent.name == "docs":
                found += [str(c / "README.md") for c in sorted(p.iterdir()) if (c / "README.md").is_file()]
    posix = [f.replace("\\", "/") for f in found]
    return sorted(f for f in set(posix) if "/.git/" not in f and "/.wt-" not in f and "worktrees" not in f)


def junction(link: Path, target: Path) -> None:
    out = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr + out.stdout


def checker_dir(tmp: Path, name: str, shared_cache: Path) -> Path:
    home = tmp / name
    home.mkdir()
    junction(home / "node_modules", MAIN_CLAUDE / "node_modules")
    junction(home / "cache", shared_cache)
    return home


@pytest.mark.corpus
def test_ac1_corpus_v2_items_judge_byte_identically_against_the_pinned_base(tmp_path: Path) -> None:
    # spec-standard-v3/AC-1
    if subprocess.run(["git", "-C", str(MAIN_CLAUDE), "cat-file", "-e", f"{PINNED_BASE}^{{commit}}"],
                      capture_output=True).returncode:
        pytest.skip(f"corpus: the pinned base {PINNED_BASE} is absent from {MAIN_CLAUDE}")
    if not Path("D:/repo").is_dir():
        pytest.skip("corpus: D:/repo is absent")
    if not (MAIN_CLAUDE / "scripts" / "spec_lint.mjs").is_file() or not (MAIN_CLAUDE / "node_modules").is_dir():
        pytest.skip(f"corpus: {MAIN_CLAUDE}/node_modules is absent (the checker's lint tools)")
    readmes = corpus_readmes()
    assert len(readmes) >= MIN_ITEMS, f"the corpus has {len(readmes)} items, the probe found {MIN_ITEMS}"
    cache = tmp_path / "shared-cache"
    cache.mkdir()
    old, new = checker_dir(tmp_path, "old", cache), checker_dir(tmp_path, "new", cache)
    archive = subprocess.run(["git", "-C", str(MAIN_CLAUDE), "archive", "--format=tar", PINNED_BASE, "scripts", "contracts"],
                             capture_output=True, check=True).stdout
    tarfile.open(fileobj=io.BytesIO(archive)).extractall(old, filter="data")
    shutil.copytree(CLAUDE / "scripts", new / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(CLAUDE / "contracts", new / "contracts")
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps(readmes), encoding="utf-8")
    outputs = {}
    for label, home in (("old", old), ("new", new)):
        out = tmp_path / f"{label}.json"
        r = subprocess.run([sys.executable, str(Path(__file__).with_name("corpus_batch.py")), str(home / "scripts"), str(cases),
                            str(out)], capture_output=True, text=True, timeout=3000)
        assert r.returncode == 0, r.stderr[-2000:]
        outputs[label] = json.loads(out.read_text(encoding="utf-8"))
    assert len(outputs["old"]) == len(readmes) * 18
    diffs = [k for k in outputs["old"] if outputs["old"][k] != outputs["new"].get(k)]
    assert not diffs, f"{len(diffs)} of {len(outputs['old'])} results differ, first: {diffs[:3]}"
    print(f"corpus: {len(readmes)} items x 18 cases = {len(outputs['old'])} results, 0 diffs")
