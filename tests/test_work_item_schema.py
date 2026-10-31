"""Contract tests for contracts/work-item.v2.json (JSON Schema, draft 2020-12): the frontmatter rules CK-1/2/3/17/21/25.

The fixtures under contracts/fixtures/work-item.v2/ are the shared examples: Catwalk's zod schema is to be tested
against the same files. Each invalid fixture names, on its first line, the CK id its first finding must carry.

    python -m pytest ~/.claude/tests/test_work_item_schema.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

CLAUDE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLAUDE / "scripts"))
import work_item_schema  # noqa: E402

FIXTURES = CLAUDE / "contracts" / "fixtures" / "work-item.v2"


def load(path: Path) -> tuple[str, dict]:
    text = path.read_text(encoding="utf-8")
    expect = text.splitlines()[0].removeprefix("# expect:").strip()
    return expect, yaml.safe_load(text)


def test_schema_is_itself_a_valid_draft_2020_12_schema() -> None:
    # spec-gate-checker/AC-1
    schema = json.loads((CLAUDE / "contracts" / "work-item.v2.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


@pytest.mark.parametrize("path", sorted((FIXTURES / "valid").glob("*.yaml")), ids=lambda p: p.stem)
def test_valid_fixture_has_no_findings(path: Path) -> None:
    # spec-gate-checker/AC-1
    _, fm = load(path)
    assert work_item_schema.findings(fm) == []


@pytest.mark.parametrize("path", sorted((FIXTURES / "invalid").glob("*.yaml")), ids=lambda p: p.stem)
def test_invalid_fixture_is_reported_under_its_ck_id(path: Path) -> None:
    # spec-gate-checker/AC-1
    expect, fm = load(path)
    found = work_item_schema.findings(fm)
    assert found, "an invalid fixture produced no finding"
    assert expect in {ck for ck, _ in found}, found
    assert all(msg for _, msg in found)


def test_every_ck_the_schema_owns_has_an_invalid_fixture() -> None:
    # spec-gate-checker/AC-1
    owned = {load(p)[0] for p in (FIXTURES / "invalid").glob("*.yaml")}
    assert {"CK-1", "CK-2", "CK-3", "CK-17", "CK-21", "CK-25"} <= owned
