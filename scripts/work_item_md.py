"""Markdown reading for work items: markdown-it-py parses the file, pydantic v2 models validate the table rows.

Headings, fences and tables come from the CommonMark token stream, so anything inside a code fence is never a heading
or a table. Row models carry the rule id of each field in `json_schema_extra={"ck": ...}`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import ClassVar

from markdown_it import MarkdownIt
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

MD = MarkdownIt("commonmark").enable("table")
NFR_KINDS = ("fault-injection", "latency-bench", "cost-budget", "extensibility", "fitness", "observability",
             "clock-kill", "spike")
EVIDENCE_TOKEN = r"(?:AC-\d+|config:[^\s+]+|decision:[\w.-]+)"
TARGET = re.compile(r"\d|<=|>=|<|>|\b(?:no|zero|never)\b", re.I)


# ---------------------------------------------------------------- the document

@dataclass(frozen=True)
class Fence:
    lang: str
    body: str
    line: int


@dataclass(frozen=True)
class Table:
    header: list[str]
    rows: list[list[str]]
    line: int


@dataclass(frozen=True)
class Text:
    text: str  # first line of a non-table, non-fence block ("" when the block has no inline text)
    line: int


@dataclass
class Section:
    level: int
    title: str
    blocks: list  # Fence | Table | Text, sub-sections included
    subs: list["Section"] = field(default_factory=list)

    @property
    def tables(self) -> list[Table]:
        return [b for b in self.blocks if isinstance(b, Table)]

    @property
    def fences(self) -> list[Fence]:
        return [b for b in self.blocks if isinstance(b, Fence)]

    @property
    def first_table(self) -> Table | None:
        return next(iter(self.tables), None)

    @property
    def first_text(self) -> str:
        return next((b.text for b in self.blocks if isinstance(b, Text) and b.text), "")


class Doc:
    def __init__(self, text: str) -> None:
        self.blocks: list[tuple[int, object]] = []  # (heading level or 0, block) in document order
        self.headings: list[tuple[int, str, int]] = []  # level, title, index into self.blocks
        tokens = MD.parse(text)
        i = 0
        while i < len(tokens):
            t = tokens[i]
            line = t.map[0] if t.map else 0
            if t.type == "heading_open":
                self.headings.append((int(t.tag[1]), tokens[i + 1].content.strip(), len(self.blocks)))
                self.blocks.append((int(t.tag[1]), None))
            elif t.type == "fence":
                self.blocks.append((0, Fence(t.info.split()[0] if t.info.strip() else "", t.content.rstrip("\n"), line)))
            elif t.type == "table_open":
                end = next(j for j in range(i, len(tokens)) if tokens[j].type == "table_close")
                rows: list[list[str]] = []
                for tok in tokens[i:end]:
                    if tok.type == "tr_open":
                        rows.append([])
                    elif tok.type == "inline":
                        rows[-1].append(tok.content.strip())
                self.blocks.append((0, Table(rows[0], rows[1:], line)))
                i = end
            elif t.nesting == 1 and t.level == 0:
                inline = tokens[i + 1].content.splitlines()[0] if tokens[i + 1].type == "inline" and tokens[i + 1].content else ""
                self.blocks.append((0, Text(inline, line)))
            if t.nesting == 1 and t.level == 0 and t.type not in ("heading_open", "table_open"):
                i = next(j for j in range(i, len(tokens)) if tokens[j].level == 0 and tokens[j].nesting == -1)
            i += 1

    def _section(self, k: int) -> Section:
        level, title, start = self.headings[k]
        end = len(self.blocks)
        subs = []
        for j in range(k + 1, len(self.headings)):
            lvl, _, at = self.headings[j]
            if lvl <= level:
                end = at
                break
            if lvl == level + 1:
                subs.append(self._section(j))
        return Section(level, title, [b for _, b in self.blocks[start + 1:end] if b is not None], subs)

    def sections(self, level: int) -> list[Section]:
        return [self._section(k) for k, (lvl, _, _) in enumerate(self.headings) if lvl == level]

    def section(self, title: str, level: int = 2) -> Section | None:
        return next((s for s in self.sections(level) if s.title.lower() == title.lower()), None)

    @property
    def fences(self) -> list[Fence]:
        return [b for _, b in self.blocks if isinstance(b, Fence)]

    @property
    def tables(self) -> list[Table]:
        return [b for _, b in self.blocks if isinstance(b, Table)]

    def first_block_after_h1(self) -> object | None:
        h1 = next((at for lvl, _, at in self.headings if lvl == 1), None)
        return next((b for _, b in self.blocks[h1 + 1:] if b is not None), None) if h1 is not None else None


# ---------------------------------------------------------------- row models


def ck(rule: str | dict[str, str]) -> dict:
    return {"ck": rule if isinstance(rule, dict) else {"*": rule}}


class Row(BaseModel):
    """A table row: fields are filled by position. Subclasses set HEADER (expected column names) and RULE."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    HEADER: ClassVar[list[str]]
    RULE: ClassVar[str]


class CapRow(Row):
    HEADER, RULE = ["CAP", "Statement"], "CK-7"
    cap: str = Field(pattern=r"^CAP-\d+$", json_schema_extra=ck("CK-7"))
    statement: str = Field(pattern=r"^The (?:user can|service must)\b", json_schema_extra=ck("CK-7"))


class NfrRow(Row):
    HEADER, RULE = ["NFR", "Target", "Method", "Evidence"], "CK-8"
    nfr: str = Field(pattern=r"^NFR-\d+$", json_schema_extra=ck("CK-8"))
    target: str = Field(min_length=1, json_schema_extra=ck("CK-8"))
    method: str = Field(pattern=rf"^(?:{'|'.join(NFR_KINDS)})\b", json_schema_extra=ck("CK-9"))
    evidence: str = Field(min_length=1, pattern=rf"^{EVIDENCE_TOKEN}(?: \+ {EVIDENCE_TOKEN})*$",
                          json_schema_extra=ck({"string_too_short": "CK-8", "*": "CK-10"}))

    @field_validator("target")
    @classmethod
    def measurable(cls, v: str) -> str:
        if not TARGET.search(v):
            raise ValueError(f"target `{v}` is not measurable (needs a number, a comparison, or no/zero/never)")
        return v


class TradeoffRow(Row):
    HEADER = ["Option", "Latency", "Cost", "Maintenance", "Extensibility", "Refactorability", "Verdict"]
    RULE = "CK-5"
    option: str = Field(min_length=1, json_schema_extra=ck("CK-5"))
    latency: str = Field(min_length=1, json_schema_extra=ck("CK-5"))
    cost: str = Field(min_length=1, json_schema_extra=ck("CK-5"))
    maintenance: str = Field(min_length=1, json_schema_extra=ck("CK-5"))
    extensibility: str = Field(min_length=1, json_schema_extra=ck("CK-5"))
    refactorability: str = Field(min_length=1, json_schema_extra=ck("CK-5"))
    verdict: str = Field(min_length=1, json_schema_extra=ck("CK-5"))


class ChosenRow(Row):
    HEADER, RULE = ["Need", "Chosen (off the shelf)", "Rejected", "Why rejected"], "CK-5"
    need: str = Field(min_length=1, json_schema_extra=ck("CK-5"))
    chosen: str = Field(min_length=1, json_schema_extra=ck("CK-5"))
    rejected: str = Field(min_length=1, json_schema_extra=ck("CK-5"))
    why_rejected: str = Field(min_length=1, json_schema_extra=ck("CK-5"))


class PatternRow(Row):
    HEADER, RULE = ["Pattern", "Where", "Why"], "CK-5"
    pattern: str = Field(min_length=1, json_schema_extra=ck("CK-5"))
    where: str = Field(min_length=1, json_schema_extra=ck("CK-5"))
    why: str = Field(min_length=1, json_schema_extra=ck("CK-5"))


class AcRow(Row):
    HEADER, RULE = ["AC", "Traces", "Given / when", "Pass when", "Fail when", "Test"], "CK-11"
    ac: str = Field(pattern=r"^AC-\d+$", json_schema_extra=ck("CK-11"))
    traces: str = Field(min_length=1, json_schema_extra=ck("CK-11"))
    given_when: str = Field(min_length=1, json_schema_extra=ck("CK-11"))
    pass_when: str = Field(min_length=1, json_schema_extra=ck("CK-11"))
    fail_when: str = Field(min_length=1, json_schema_extra=ck("CK-11"))
    test: str = Field(min_length=1, json_schema_extra=ck("CK-11"))

    @property
    def trace_ids(self) -> list[str]:
        return [t.strip() for t in self.traces.split(",") if t.strip()]


class FrRow(Row):
    HEADER, RULE = ["FR", "Requirement"], "CK-13"
    fr: str = Field(pattern=r"^FR-\d+$", json_schema_extra=ck("CK-13"))
    requirement: str = Field(min_length=1, json_schema_extra=ck("CK-13"))


def norm(cells: list[str]) -> list[str]:
    return [re.sub(r"\s+", " ", c).strip().lower() for c in cells]


def parse_rows(table: Table | None, model: type[Row]) -> tuple[list, list[tuple[str, str]]]:
    """Validated rows plus (rule id, message) findings. A wrong header or width is reported under the model's RULE."""
    if table is None:
        return [], []
    if norm(table.header) != norm(model.HEADER):
        return [], [(model.RULE, f"table header must be | {' | '.join(model.HEADER)} |")]
    rows, found = [], []
    names = list(model.model_fields)
    for n, cells in enumerate(table.rows, start=1):
        if len(cells) != len(names):
            found.append((model.RULE, f"row {n} has {len(cells)} cells, expected {len(names)}"))
            continue
        try:
            rows.append(model.model_validate(dict(zip(names, cells))))
        except ValidationError as e:
            for err in e.errors():
                name = str(err["loc"][0]) if err["loc"] else "row"
                rules = (model.model_fields[name].json_schema_extra or {}).get("ck", {}) if name in model.model_fields else {}
                rule = rules.get(err["type"]) or rules.get("*") or model.RULE
                found.append((rule, f"{cells[0] or f'row {n}'}: `{name}` {err['msg'].removeprefix('Value error, ')}"))
    return rows, found
