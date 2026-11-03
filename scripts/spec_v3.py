"""Work-Item Standard v3 rules: the profile a `standard: 3` README owes at its status (work item spec-standard-v3).

    spec_check.check_work_item  -> spec_v3.check(item, v3, rep, live)      the checker's early branch
    review_record.required_records -> spec_v3.lock_exempt(...)            which locks need no design record
    spec_gate.lifecycle_problem / record_problem -> frozen_set_problem, raises_scrutiny, involves_v3, live_of

Standard: ~/.claude/skills/dark-factory/SPEC-STANDARD-V3.md. Every flag, dimension and level comes from
contracts/work-item.v3.json through work_item_schema.load_contract(); this module names none of them as a list.

What each tool owns (a rule with an off-the-shelf tool does not get a hand-written one):
  frontmatter                    work_item_schema.read_v3: PyYAML + jsonschema against the contract
  markdown structure             markdown-it-py through work_item_md.Doc (headings, tables, fences) and MD tokens (links, prose)
  table rows                     work_item_md.parse_rows with pydantic row models
  `path:line` citations          work_item_md.citations and spec_check.resolve_citation (v2 CK-48's resolver)
  test citations (CK-20)         spec_check.check_test_citations, shared with v2

Searched scripts/ for "judge a frontmatter profile": found spec_check.check_work_item and work_item_schema; extending
both, with this module added for the v3 rules only.
Searched scripts/ and hooks/ for a `deploymentTier` parser: found fleet_status.tier (takes a repo Path and reads the
disk) and session_context.TIER (a display regex); both match the key anywhere, prose and code fences included, and
neither takes text. `live_of` keeps their key grammar (`deploymentTier: <word>`) and adds the text input, the fence and
prose exclusion and the exact-word match.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from pydantic import Field, field_validator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spec_check  # noqa: E402
import work_item_schema  # noqa: E402
from work_item_md import MD, VIOLATED, AcRow, Doc, Fence, Row, ck, norm, parse_rows, word_reason  # noqa: E402

TIER_RULE, OUT_RULE, BUG_RULE, DOC_RULE = "CK-V3-TIER", "CK-V3-OUT", "CK-V3-BUG", "CK-V3-DOC"
LIVE = "live"            # the one derived flag (FR-3): the repo's CLAUDE.md says `deploymentTier: live`
CONTRACT_FLAG = "contract"  # the one flag that adds a section (FR-4)
T1_MAX_ACS = 5
MAX_ACS = spec_check.MAX_ACS
BUGFIX_MAX_ACS = 3
MIN_REASON_WORDS = 3
PLACEHOLDER_WORDS = {"n/a", "none", "-", "tbd", "todo", "not", "applicable"}  # an L1 reason made only of these is none
TIER_RANK = {"T1": 1, "T2": 2}
DRAFT = "draft"
FEATURE_SECTIONS = ["Purpose", "Goals and non-goals", "Behaviour", "Outcomes"]
FEATURE_T2_SECTIONS = ["Approach", "Assumptions", "Probe"]
BUGFIX_SECTIONS = ["Symptom", "Reproduce", "Expected", "Actual", "Must not change", "Root cause"]
OUTCOMES_HEADER = ["Dimension", "Level", "Row or n/a reason", "AC"]
AMENDMENTS_HEADER = ["Change", "Why (what the test exposed)", "Test"]
OPEN_MARKER = re.compile(r"\[NEEDS CLARIFICATION|\bTBD\b", re.I)
AC_ID = re.compile(r"^AC-\d+$")


# ---------------------------------------------------------------- the repo's tier: `live`

DECLARED_AT_LINE_START = re.compile(r"^[ \t]*(?:[-*+][ \t]+)?\**deploymentTier\**:\**[ \t]*`?([a-z-]+)(?!\w)")
DECLARED_IN_CODE_SPAN = re.compile(r"`deploymentTier:[ \t]*([a-z-]+)(?!\w)")


def live_of(claude_md: str | None) -> bool:
    """Whether the first `deploymentTier:` declaration in a CLAUDE.md is exactly `live`. A declaration is a line that
    starts with the key, inside a code fence or not (the fleet writes it fenced: D:/repo/SaaS/cashcow/CLAUDE.md:11),
    or a backticked `deploymentTier: word` span; prose, comments and look-alikes (`live-later`, `live_x`) are not.
    Reading a fenced example as live only makes an item stricter. A missing file or no declaration is not live (the
    global default: pre-traffic)."""
    for line in (claude_md or "").splitlines():
        if m := DECLARED_AT_LINE_START.match(line) or DECLARED_IN_CODE_SPAN.search(line):
            return m.group(1) == LIVE
    return False


# ---------------------------------------------------------------- the computed tier

def effective_flags(v3: work_item_schema.V3Frontmatter, live: bool) -> list[str]:
    """The declared flags plus `live` whenever the repo says so, whatever `risk` says (FR-3)."""
    return [*v3.risk, *([LIVE] if live and LIVE not in v3.risk else [])]


def computed_tier(v3: work_item_schema.V3Frontmatter, ac_count: int, live: bool) -> str:
    """T1, T2 or SPLIT: more than 5 ACs or any flag is T2; more than 15 ACs has no tier."""
    if ac_count > MAX_ACS:
        return "SPLIT"
    return "T2" if ac_count > T1_MAX_ACS or effective_flags(v3, live) else "T1"


def effective_tier(v3: work_item_schema.V3Frontmatter, ac_count: int, live: bool) -> str:
    """The higher of the declared and the computed tier: a declaration can raise the scrutiny, never lower it."""
    computed = computed_tier(v3, ac_count, live)
    return "T2" if computed != "T1" or v3.tier == "T2" else "T1"


# ---------------------------------------------------------------- row models for the v3-only tables

class MncRow(Row):
    HEADER, RULE = ["ID", "Must not change", "Test"], BUG_RULE
    mnc: str = Field(pattern=r"^MNC-\d+$", json_schema_extra=ck(BUG_RULE))
    must_not_change: str = Field(min_length=1, json_schema_extra=ck(BUG_RULE))
    test: str = Field(min_length=1, json_schema_extra=ck(BUG_RULE))


class AssumptionRow(Row):
    HEADER, RULE = ["Assumption", "Observed", "If violated"], DOC_RULE
    assumption: str = Field(min_length=1, json_schema_extra=ck(DOC_RULE))
    observed: str = Field(min_length=1, json_schema_extra=ck(DOC_RULE))
    violated: str = Field(min_length=1, json_schema_extra=ck(DOC_RULE))

    @field_validator("violated")
    @classmethod
    def fail_safe(cls, v: str) -> str:
        return word_reason(v, VIOLATED, "checked syntactically only")


# ---------------------------------------------------------------- the AC table

def ac_section_title(v3: work_item_schema.V3Frontmatter) -> str:
    return "Expected" if v3.type == "bugfix" else "Behaviour"


def ac_table(doc: Doc, v3: work_item_schema.V3Frontmatter):
    """(section, rows, findings): the AC table of Behaviour (feature) or Expected (bugfix)."""
    section = doc.section(ac_section_title(v3))
    table = section.first_table if section else None
    rows, found = parse_rows(table, AcRow)
    return section, rows, found


def body_of(text: str) -> str:
    m = work_item_schema.FRONTMATTER.match(text)
    return text[m.end():] if m else text


def ac_count(text: str, v3: work_item_schema.V3Frontmatter) -> int | None:
    """The number of AC rows, or None when the table cannot be read (none, a second table, a wrong header or a bad row)."""
    section, rows, found = ac_table(Doc(body_of(text)), v3)
    return len(rows) if section and len(section.tables) == 1 and rows and not found else None


# ---------------------------------------------------------------- the lock rule (review_record.required_records)

def lock_exempt(tree: spec_check.Tree, item_dir: str, live: bool | None) -> bool:
    """True when the STAGED README is a v3 T1 feature or an unflagged v3 bugfix: its lock needs no design record (FR-10).
    The tier is computed from the AC count and the flags, never from the declaration alone. Anything unreadable (an
    absent or look-alike frontmatter, a missing contract, an unreadable AC table) is not exempt: it fails closed."""
    text = tree.read(f"{item_dir}/README.md") or ""
    try:
        v3 = work_item_schema.read_v3(text)
    except (work_item_schema.V3Refusal, work_item_schema.ContractError):
        return False
    if v3 is None:
        return False
    if live is None:
        live = live_of(tree.read("CLAUDE.md"))
    count = ac_count(text, v3)
    if count is None or effective_flags(v3, live):
        return False
    return v3.type == "bugfix" or (v3.tier == "T1" and count <= T1_MAX_ACS)


# ---------------------------------------------------------------- the frozen set (spec_gate.lifecycle_problem)

def involves_v3(*texts: str | None) -> bool:
    """Whether any README text carries a v3 key (`standard`, `tier` or `risk`), readable or not."""
    return any(fm is not None and any(k in fm for k in work_item_schema.V3_KEYS)
               for fm in map(work_item_schema.frontmatter_of, texts))


def _side(text: str | None):
    """(kind, status, v3): kind is `v3`, `other` (a readable README with no v3 key), `refused` or `unreadable`."""
    fm = work_item_schema.frontmatter_of(text)
    if fm is None:
        return "unreadable", None, None
    try:
        v3 = work_item_schema.read_v3(text)
    except work_item_schema.V3Refusal:
        return "refused", None, None
    return ("v3", v3.status, v3) if v3 else ("other", str(fm.get("status")), None)


def frozen_set_problem(head_text: str | None, staged_text: str | None) -> str | None:
    """FR-11. When HEAD's copy is past draft and either copy is v3: `standard` and `type` equal HEAD's; `tier` does not
    fall and `risk` loses no flag (as sets) unless the staged status is `draft`. None when HEAD is unreadable (the repair
    path) or the staged copy is refused by the checker anyway."""
    head_kind, head_status, head = _side(head_text)
    staged_kind, staged_status, staged = _side(staged_text)
    if head_kind in ("unreadable", "refused") or staged_kind in ("unreadable", "refused"):
        return None
    if head_status in (None, DRAFT) or (head_kind == "other" and staged_kind == "other"):
        return None
    shown = {"v3": f"{work_item_schema.V3_STANDARD}", "other": "absent"}
    if head_kind != staged_kind:
        return (f"`standard` changed from {shown[head_kind]} to {shown[staged_kind]} after the lock "
                f"(HEAD is `{head_status}`); it never changes once the item leaves draft")
    if head.type != staged.type:
        return f"`type` changed from {head.type} to {staged.type} after the lock (HEAD is `{head_status}`)"
    if staged_status == DRAFT:
        return None  # the lifecycle allows draft only from spec-locked: the lowering route
    back = "; to lower it move the item back to draft first (only from spec-locked)"
    if TIER_RANK.get(staged.tier, 0) < TIER_RANK.get(head.tier, 0):
        return f"`tier` fell from {head.tier} to {staged.tier} after the lock (HEAD is `{head_status}`){back}"
    if lost := sorted(set(head.risk) - set(staged.risk)):
        return f"`risk` lost flag(s) {', '.join(lost)} after the lock (HEAD is `{head_status}`){back}"
    return None


def raises_scrutiny(head_text: str | None, staged_text: str | None) -> bool:
    """FR-11: a v3 item past draft in HEAD and in the staged copy whose declared tier rose or that gained a flag. The
    gate then treats the commit as a lock edge: it needs a fresh design record for the staged content."""
    head_kind, head_status, head = _side(head_text)
    staged_kind, staged_status, staged = _side(staged_text)
    if head_kind != "v3" or staged_kind != "v3" or DRAFT in (head_status, staged_status):
        return False
    return TIER_RANK.get(staged.tier, 0) > TIER_RANK.get(head.tier, 0) or bool(set(staged.risk) - set(head.risk))


# ---------------------------------------------------------------- the checker: spec_check.check_work_item's v3 branch

def check(item: spec_check.Item, v3: work_item_schema.V3Frontmatter, rep: spec_check.Report, live: bool | None) -> None:
    """Judge a v3 item at its status. Report.err drops a rule the status does not enable, so each rule is simply raised."""
    contract = work_item_schema.load_contract()
    if live is None:
        live = live_of(item.tree.read("CLAUDE.md"))
    if str(item.fm["id"]) != item.id:
        rep.err("CK-2", "README.md", f"`id` ({item.fm['id']}) must equal the folder name ({item.id})")
    for name in spec_check.LAYER_FILES.values():
        if item.texts[name] is not None:
            rep.err("CK-3", name, f"{name} exists, but a v3 item has no layer files: its content lives in the README")
    flags = effective_flags(v3, live)
    section, ac_rows, ac_found = ac_table(item.doc, v3)
    ac_ids = [r.ac for r in ac_rows]
    rows_in_table = len(section.first_table.rows) if section and section.first_table else 0
    tier = effective_tier(v3, rows_in_table, live)

    check_diagram(item, rep)
    check_sections(item, v3, rep, flags, tier)
    check_ac_table(item, v3, rep, section, ac_rows, ac_found, rows_in_table)
    if v3.type == "feature":
        check_tier(v3, rep, rows_in_table, flags, live)
        check_outcomes(item, rep, contract, flags, tier, ac_ids)
    else:
        check_must_not_change(item, rep)
    check_amendments(item, rep)
    check_assumptions(item, rep)
    check_probe(item, rep)
    check_open_markers(item, rep)
    if "CK-20" in rep.enabled:
        spec_check.check_test_citations(item, rep, "README.md", [(r.ac, r.test) for r in ac_rows])
        if v3.type == "bugfix":
            spec_check.check_test_citations(item, rep, "README.md", [(r.mnc, r.test) for r in mnc_rows(item)[0][0]])


def check_diagram(item: spec_check.Item, rep: spec_check.Report) -> None:
    """One Mermaid block before the first H2."""
    for level, block in item.doc.blocks:
        if level == 2:
            break
        if isinstance(block, Fence) and block.lang == "mermaid":
            return
    rep.err("CK-6", "README.md", "needs a ```mermaid block before the first `##` heading")


def required_sections(v3: work_item_schema.V3Frontmatter, flags: list[str], tier: str) -> list[str]:
    if v3.type == "bugfix":
        return [*BUGFIX_SECTIONS, *(["Probe"] if flags else [])]
    return [*FEATURE_SECTIONS, *(FEATURE_T2_SECTIONS if tier == "T2" else []),
            *(["Contracts"] if CONTRACT_FLAG in v3.risk else [])]


def check_sections(item: spec_check.Item, v3, rep: spec_check.Report, flags: list[str], tier: str) -> None:
    for title in required_sections(v3, flags, tier):
        if item.doc.section(title) is None:
            rep.err("CK-4", "README.md", f"missing section `## {title}`")


def check_ac_table(item, v3, rep, section, rows: list[AcRow], found: list[tuple[str, str]], count: int) -> None:
    title = ac_section_title(v3)
    if section is None:
        return  # CK-4 names the missing section
    if len(section.tables) > 1:
        rep.err("CK-11", "README.md", f"`{title}` holds {len(section.tables)} tables; it must hold exactly one table")
    if section.first_table is None:
        rep.err("CK-11", "README.md", f"`{title}` has no acceptance criteria table")
        return
    rep.add("README.md", found)
    if not rows and not found:
        rep.err("CK-11", "README.md", f"`{title}` has no AC-n rows")
    ids = [r.ac for r in rows]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        rep.err("CK-11", "README.md", f"duplicate {dup}")
    if v3.type == "bugfix" and count > BUGFIX_MAX_ACS:
        rep.err("CK-11", "README.md", f"`{title}` has {count} rows: a spec change, not a bug (1 to {BUGFIX_MAX_ACS} rows)")


def check_tier(v3, rep: spec_check.Report, count: int, flags: list[str], live: bool) -> None:
    computed = computed_tier(v3, count, live)
    if computed == "SPLIT":
        rep.err(TIER_RULE, "README.md", f"{count} ACs is over {MAX_ACS}: split the change (T3 stays on v2 nesting)")
    elif computed == "T2" and v3.tier == "T1":
        why = ([f"{count} ACs (more than {T1_MAX_ACS})"] if count > T1_MAX_ACS else []) + [
            f"flag `{f}`" + (" (CLAUDE.md says deploymentTier: live)" if f == LIVE and LIVE not in v3.risk else "")
            for f in flags]
        rep.err(TIER_RULE, "README.md", f"declares T1 but the computed tier is T2: {', '.join(why)}")


def check_outcomes(item, rep: spec_check.Report, contract, flags: list[str], tier: str, ac_ids: list[str]) -> None:
    section = item.doc.section("Outcomes")
    if section is None:
        return
    if len(section.tables) > 1:
        rep.err(OUT_RULE, "README.md", f"`Outcomes` holds {len(section.tables)} tables; it must hold exactly one table")
    table = section.first_table
    if table is None:
        rep.err(OUT_RULE, "README.md", "`Outcomes` needs the table | " + " | ".join(OUTCOMES_HEADER) + " |")
        return
    if norm(table.header) != norm(OUTCOMES_HEADER):
        rep.err(OUT_RULE, "README.md", "`Outcomes` table header must be | " + " | ".join(OUTCOMES_HEADER) + " |")
        return
    level_of: dict[str, str] = {}
    seen: set[str] = set()
    for n, cells in enumerate(table.rows, start=1):
        if len(cells) != len(OUTCOMES_HEADER):
            rep.err(OUT_RULE, "README.md", f"`Outcomes` row {n} has {len(cells)} cells, expected {len(OUTCOMES_HEADER)}")
            continue
        dim, level, why, ac = cells
        if dim not in contract.dimensions:
            rep.err(OUT_RULE, "README.md", f"unknown dimension `{dim}` (spelled exactly as in the contract)")
            continue
        if dim in seen:
            rep.err(OUT_RULE, "README.md", f"dimension `{dim}` appears more than once")
            continue
        seen.add(dim)
        if level not in contract.levels:
            rep.err(OUT_RULE, "README.md", f"`{dim}`: level `{level}` is not one of {', '.join(contract.levels)}")
            continue
        level_of[dim] = level
        for problem in row_problems(level, why, ac, ac_ids):
            rep.err(OUT_RULE, "README.md", f"`{dim}`: {problem}")
    for dim in contract.dimensions:
        if dim not in seen:
            rep.err(OUT_RULE, "README.md", f"dimension `{dim}` is missing")
    forced = {d: f for f in flags for d in contract.flag_to_dimensions.get(f, ())}
    for dim, level in level_of.items():
        if dim in forced and level != "L3":
            rep.err(OUT_RULE, "README.md", f"`{dim}` is {level}; flag `{forced[dim]}` forces it to L3")
        elif tier == "T1" and dim in contract.t1_l3 and level != "L3":
            rep.err(OUT_RULE, "README.md", f"`{dim}` is {level}; a T1 item needs it at L3")
        elif tier == "T2" and level == "L2":
            rep.err(OUT_RULE, "README.md", f"`{dim}` is L2; a T2 item allows no L2 row")


def row_problems(level: str, why: str, ac: str, ac_ids: list[str]) -> list[str]:
    if level == "L1":
        words = why.lower().split()
        if len(words) < MIN_REASON_WORDS or set(words) <= PLACEHOLDER_WORDS:
            return [f"an L1 row needs a reason of at least {MIN_REASON_WORDS} words that is not a placeholder, got `{why}`"]
    elif not why:
        return [f"an {level} row needs its text"]
    if level == "L3" and not (AC_ID.match(ac) and ac in ac_ids):
        return [f"an L3 row must name an existing AC, got `{ac}`" + (" (not an AC of this item)" if AC_ID.match(ac) else "")]
    return []


def mnc_rows(item: spec_check.Item):
    section = item.doc.section("Must not change")
    return parse_rows(section.first_table if section else None, MncRow), section


def check_must_not_change(item, rep: spec_check.Report) -> None:
    (rows, found), section = mnc_rows(item)
    if section is None:
        return
    if section.first_table is None:
        rep.err(BUG_RULE, "README.md", "`Must not change` needs the table | " + " | ".join(MncRow.HEADER) + " |")
        return
    rep.add("README.md", [(r, f"`Must not change`: {m}") for r, m in found])
    if not rows and not found:
        rep.err(BUG_RULE, "README.md", "`Must not change` needs at least 1 row")
    ids = [r.mnc for r in rows]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        rep.err(BUG_RULE, "README.md", f"duplicate {dup}")


def check_amendments(item, rep: spec_check.Report) -> None:
    section = item.doc.section("Build amendments")
    if section is None:
        return
    table = section.first_table
    if table is None or norm(table.header) != norm(AMENDMENTS_HEADER):
        rep.err(DOC_RULE, "README.md", "`Build amendments` table header must be | " + " | ".join(AMENDMENTS_HEADER) + " |")
        return
    for n, cells in enumerate(table.rows, start=1):
        empty = [AMENDMENTS_HEADER[i] for i in range(len(AMENDMENTS_HEADER)) if i >= len(cells) or not cells[i]]
        if empty or len(cells) != len(AMENDMENTS_HEADER):
            rep.err(DOC_RULE, "README.md", f"`Build amendments` row {n} needs every cell filled (empty: {', '.join(empty) or 'width'})")


def check_assumptions(item, rep: spec_check.Report) -> None:
    section = item.doc.section("Assumptions")
    if section is None:
        return
    if section.first_table is None:
        rep.err(DOC_RULE, "README.md", "`Assumptions` needs the table | " + " | ".join(AssumptionRow.HEADER) + " |")
        return
    rows, found = parse_rows(section.first_table, AssumptionRow)
    rep.add("README.md", [(r, f"`Assumptions`: {m}") for r, m in found])
    if not rows and not found:
        rep.err(DOC_RULE, "README.md", "`Assumptions` needs at least 1 row")
    spec_check.cite_findings(item, DOC_RULE, rep, [r.observed for r in rows])


def links_under(body: str, title: str) -> list[str]:
    """The href of every Markdown link in the H2 section `title`."""
    hrefs: list[str] = []
    current = ""
    tokens = MD.parse(body)
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open" and tok.tag == "h2":
            current = tokens[i + 1].content.strip().lower()
        elif tok.type == "inline" and current == title.lower():
            hrefs += [child.attrGet("href") or "" for child in tok.children or [] if child.type == "link_open"]
    return hrefs


def check_probe(item, rep: spec_check.Report) -> None:
    if item.doc.section("Probe") is None:
        return
    links = links_under(item.body, "Probe")
    if not links:
        rep.err(DOC_RULE, "README.md", "`Probe` needs a link to a file under evidence/")
    evidence = f"{item.dir}/evidence/"
    for href in links:
        path = None if "://" in href else spec_check.inside(item.dir, href.split("#", 1)[0])
        if path is None or not path.startswith(evidence) or not item.tree.is_file(path):
            rep.err(DOC_RULE, "README.md", f"`Probe` link `{href}` must name an existing file under evidence/")


def check_open_markers(item, rep: spec_check.Report) -> None:
    """`[NEEDS CLARIFICATION` and `TBD` in prose (not in inline code or a fence) are open questions."""
    found: set[str] = set()
    for tok in MD.parse(item.body):
        if tok.type == "inline":
            text = "".join(c.content for c in tok.children or [] if c.type != "code_inline")
            found |= {m.group(0).upper() for m in OPEN_MARKER.finditer(text)}
    for marker in sorted(found):
        rep.err(DOC_RULE, "README.md", f"open marker `{marker}` is left in the spec; resolve it before the lock")
