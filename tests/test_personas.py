"""The persona registry (agents/README.md) and its persona files agree (owner 2026-11-04, D64)."""
import re
from pathlib import Path

AGENTS = Path(__file__).resolve().parent.parent / "agents"
CORE = ("implementer", "researcher", "designer", "reviewer")
SHARED = "agents/README.md` § Shared rules"


def frontmatter(name: str) -> dict[str, str]:
    text = (AGENTS / f"{name}.md").read_text(encoding="utf-8")
    block = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert block, f"{name}: no frontmatter"
    return dict(re.findall(r"^(\w+):\s*(.+)$", block.group(1), re.M))


def personas() -> list[str]:
    return sorted(p.stem for p in AGENTS.glob("*.md") if p.stem != "README")


def test_exactly_the_four_lifecycle_personas_exist() -> None:
    # D65: adversary and security are reviewer modes, architect is the designer's decision mode
    assert personas() == sorted(CORE)


def test_the_folded_personas_live_on_as_modes() -> None:
    reviewer = (AGENTS / "reviewer.md").read_text(encoding="utf-8")
    designer = (AGENTS / "designer.md").read_text(encoding="utf-8")
    for mode in ("adversary", "design", "code", "security", "verify"):
        assert re.search(rf"^- \*\*{mode}\*\*", reviewer, re.M), mode
    assert "decision mode" in designer and "Reversibility" in designer


def test_every_persona_defaults_to_opus_at_medium_effort() -> None:
    for name in personas():
        fm = frontmatter(name)
        assert fm.get("model") == "opus", name
        assert fm.get("effort") == "medium", name


def test_every_persona_loads_the_shared_rules_first() -> None:
    for name in personas():
        text = (AGENTS / f"{name}.md").read_text(encoding="utf-8")
        assert SHARED in text, name


def test_the_registry_table_matches_each_persona_file() -> None:
    table = (AGENTS / "README.md").read_text(encoding="utf-8")
    for name in personas():
        row = re.search(rf"^\| {name} \|[^\n]*\| (\w+) \| (\w+) \|", table, re.M)
        assert row, f"README has no row for {name}"
        fm = frontmatter(name)
        assert (row.group(1), row.group(2)) == (fm["model"], fm["effort"]), name


def test_the_shared_rules_name_the_denial_rule_and_verbatim_quotes() -> None:
    text = (AGENTS / "README.md").read_text(encoding="utf-8")
    shared = text.split("## Shared rules", 1)[1].split("\n## ", 1)[0]
    assert re.search(r"denies.{0,120}stop", shared, re.I | re.S)
    assert re.search(r"verbatim", shared, re.I)
    assert re.search(r"D63", shared)


def test_the_research_page_runs_the_owners_study_flow_in_order() -> None:
    # owner 2026-11-08: direction, local state, fan-out, online, gap, adopt-or-continue
    text = (AGENTS.parent / "skills" / "research-page" / "SKILL.md").read_text(encoding="utf-8")
    steps = ("**Direction.**", "**Local first.**", "**Have.**", "**Investigate.**", "**Online.**", "**Gap.**", "**Adopt or continue.**", "**Persist.**")
    positions = [text.index(step) for step in steps]
    assert positions == sorted(positions)
    for source in ("GitHub", "Reddit", "Hacker News", "Y Combinator", "Coverage line", "`continue local`"):
        assert source in text, source
