"""Work-item frontmatter validation: contracts/work-item.v2.json (JSON Schema 2020-12) checked with jsonschema.

The schema is the single source of truth for the frontmatter rules. Each failing keyword is mapped to a checker rule
id by the `x-ck` annotation of the sub-schema that failed ({keyword: CK id, '*': default}).

Standard v3 (work item spec-standard-v3): `read_v3` is the ONE reader of a `standard: 3` frontmatter, used by spec_check,
spec_gate and review_record. It loads contracts/work-item.v3.json lazily (the first v3 item in the process), so a v2 item
never reads it.
"""
from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, SchemaError, ValidationError
from jsonschema import validate as validate_shape

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


def findings(frontmatter: dict, validator: Draft202012Validator = VALIDATOR) -> list[tuple[str, str]]:
    """(rule id, message) for every schema violation, in a stable order."""
    errors = sorted(validator.iter_errors(frontmatter), key=lambda e: [str(p) for p in e.absolute_path])
    found = list(dict.fromkeys((rule_of(e), message_of(e)) for e in errors))
    created = frontmatter.get("created")
    if isinstance(created, str) and len(created) == len("YYYY-MM-DD"):
        try:
            datetime.date.fromisoformat(created)
        except ValueError:
            found.append((FALLBACK_RULE, f"`created` {created} is not a real date"))  # the schema pattern alone accepts it
    return found


# ---------------------------------------------------------------- standard v3: the contract and the one reader

V3_CONTRACT_PATH = Path(__file__).resolve().parents[1] / "contracts" / "work-item.v3.json"
FRONTMATTER = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?", re.S)  # the block spec_check.Item reads, so every reader agrees
V3_KEYS = ("standard", "tier", "risk")
V3_STANDARD = 3

# Structure only (no flag, dimension or level is named here): a contract that fails it is refused by name.
_LIST_OF_STRINGS = {"type": "array", "items": {"type": "string"}}
_CONTRACT_SHAPE = {
    "type": "object",
    "required": ["$defs", "flag_to_dimensions", "t1_l3_dimensions", "frontmatter"],
    "properties": {
        "$defs": {"type": "object", "required": ["flag", "dimension", "level"],
                  "additionalProperties": {"type": "object"},
                  "properties": {k: {"type": "object", "required": ["enum"],
                                     "properties": {"enum": {**_LIST_OF_STRINGS, "minItems": 1, "uniqueItems": True}}}
                                 for k in ("flag", "dimension", "level")}},
        "flag_to_dimensions": {"type": "object", "additionalProperties": _LIST_OF_STRINGS},
        "t1_l3_dimensions": _LIST_OF_STRINGS,
        "frontmatter": {"type": "object"},
    },
}


class ContractError(RuntimeError):
    """The v3 contract is missing, unparseable or invalid. The message is `contract <path> <reason>`."""

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"contract {path.as_posix()} {reason}")


class V3Refusal(ValueError):
    """A frontmatter the v3 reader refuses: (rule id, message) findings, never a fall-back to v2."""

    def __init__(self, found: list[tuple[str, str]]) -> None:
        super().__init__("; ".join(m for _, m in found))
        self.findings = found


@dataclass(frozen=True)
class Contract:
    flags: tuple[str, ...]
    dimensions: tuple[str, ...]
    levels: tuple[str, ...]
    flag_to_dimensions: dict[str, tuple[str, ...]]
    t1_l3: tuple[str, ...]
    validator: Draft202012Validator = field(repr=False)


@dataclass(frozen=True)
class V3Frontmatter:
    id: str
    type: str
    standard: int
    status: str
    touches: list
    layers: dict
    created: str
    owner: str
    tier: str | None
    risk: list[str]


_contracts: dict[tuple, Contract] = {}


def reset_contract() -> None:
    _contracts.clear()


def load_contract() -> Contract:
    """The v3 contract, read once per process (read again only when the file changes). Raises ContractError by name."""
    path = V3_CONTRACT_PATH
    try:
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        if key in _contracts:
            return _contracts[key]
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise ContractError(path, f"cannot be read: {e}") from e
    except ValueError as e:
        raise ContractError(path, f"is not valid JSON: {e}") from e
    try:
        validate_shape(raw, _CONTRACT_SHAPE)
        defs = raw["$defs"]
        flags, dims = defs["flag"]["enum"], defs["dimension"]["enum"]
        named = [(k, flags) for k in raw["flag_to_dimensions"]] + [(d, dims) for v in raw["flag_to_dimensions"].values()
                                                                    for d in v] + [(d, dims) for d in raw["t1_l3_dimensions"]]
        stray = [value for value, allowed in named if value not in allowed]
        if stray:
            raise ContractError(path, f"names `{stray[0]}`, which its flag and dimension lists do not hold")
        Draft202012Validator.check_schema(raw["frontmatter"])
    except (ValidationError, SchemaError) as e:
        raise ContractError(path, f"is invalid: {e.message[:200]}") from e
    contract = Contract(tuple(flags), tuple(dims), tuple(defs["level"]["enum"]),
                        {k: tuple(v) for k, v in raw["flag_to_dimensions"].items()}, tuple(raw["t1_l3_dimensions"]),
                        Draft202012Validator({**raw["frontmatter"], "$defs": defs}))
    _contracts.clear()
    _contracts[key] = contract
    return contract


def frontmatter_of(text: str | None) -> dict | None:
    """The frontmatter mapping of a README as Item reads it; None when absent, unparseable or not a mapping."""
    m = FRONTMATTER.match(text or "")
    try:
        loaded = yaml.safe_load(m.group(1)) if m else None
    except yaml.YAMLError:
        return None
    return loaded if isinstance(loaded, dict) else None


class _UniqueKeyLoader(yaml.SafeLoader):
    """safe_load that refuses a repeated key (PyYAML keeps the last one silently)."""


def _construct_unique(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    seen: set = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise V3Refusal([("CK-1", f"duplicate key `{key}` in the frontmatter")])
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique)


def read_v3(text: str) -> V3Frontmatter | None:
    """None when the README has no frontmatter mapping or none of `standard`, `tier`, `risk`. Otherwise the v3 reading,
    or V3Refusal: `standard` must be exactly the integer 3, `tier` and `risk` need it, a repeated key is refused, and
    the rest is the contract's frontmatter schema. Raises ContractError when the contract cannot be loaded."""
    fm = frontmatter_of(text)
    if fm is None or not any(k in fm for k in V3_KEYS):
        return None
    if "standard" not in fm:
        raise V3Refusal([("CK-1", f"`{k}` is only valid with `standard: {V3_STANDARD}`") for k in V3_KEYS if k in fm])
    if type(fm["standard"]) is not int or fm["standard"] != V3_STANDARD:
        raise V3Refusal([("CK-1", f"`standard` must be exactly the integer {V3_STANDARD}, got {fm['standard']!r}")])
    yaml.load(FRONTMATTER.match(text).group(1), Loader=_UniqueKeyLoader)  # noqa: S506 - a SafeLoader subclass
    found = findings(fm, load_contract().validator)
    if found:
        raise V3Refusal(found)
    return V3Frontmatter(str(fm["id"]), fm["type"], fm["standard"], fm["status"], fm["touches"], fm["layers"],
                         fm["created"], fm["owner"], fm.get("tier"), list(fm["risk"]))
