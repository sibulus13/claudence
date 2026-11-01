"""Work-item frontmatter validation: contracts/work-item.v2.json (JSON Schema 2020-12) checked with jsonschema.

The schema is the single source of truth for the frontmatter rules. Each failing keyword is mapped to a checker rule
id by the `x-ck` annotation of the sub-schema that failed ({keyword: CK id, '*': default}).
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "contracts" / "work-item.v2.json"
VALIDATOR = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
FALLBACK_RULE = "CK-1"


def rule_of(error) -> str:
    table = error.schema.get("x-ck", {}) if isinstance(error.schema, dict) else {}
    return table.get(error.validator) or table.get("*") or FALLBACK_RULE


def message_of(error) -> str:
    where = ".".join(str(p) for p in error.absolute_path) or "frontmatter"
    if isinstance(error.instance, (datetime.date, datetime.datetime)):
        return f"`{where}` parsed as a date: quote it (created: \"YYYY-MM-DD\")"
    return f"`{where}`: {error.message}"


def findings(frontmatter: dict) -> list[tuple[str, str]]:
    """(rule id, message) for every schema violation, in a stable order."""
    errors = sorted(VALIDATOR.iter_errors(frontmatter), key=lambda e: [str(p) for p in e.absolute_path])
    found = list(dict.fromkeys((rule_of(e), message_of(e)) for e in errors))
    created = frontmatter.get("created")
    if isinstance(created, str) and len(created) == len("YYYY-MM-DD"):
        try:
            datetime.date.fromisoformat(created)
        except ValueError:
            found.append((FALLBACK_RULE, f"`created` {created} is not a real date"))  # the schema pattern alone accepts it
    return found
