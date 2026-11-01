"""Generate contracts/work-item.headings.v2.json (the CK-4 required headings per file type) from the standard's tables.

    python gen_heading_config.py            # rewrite the JSON
    python gen_heading_config.py --check    # exit 1 if the committed JSON is stale

Source of truth: skills/dark-factory/WORK-ITEM-STANDARD.md, "Required headings per type". spec_check.py feeds the result to
markdownlint rule MD043 (see spec_lint.mjs).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from work_item_md import Doc  # noqa: E402

CLAUDE = Path(__file__).resolve().parents[1]
STANDARD = CLAUDE / "skills" / "dark-factory" / "WORK-ITEM-STANDARD.md"
OUTPUT = CLAUDE / "contracts" / "work-item.headings.v2.json"
TYPES = ("feature", "integration", "data-collection", "experiment", "research", "bugfix", "refactor")
TICKS = re.compile(r"`([^`]+)`")
WHEN = {"multi-package": "multi-package", "lifecycle: true": "lifecycle", "layers.architecture": "architecture"}


def names(text: str) -> list[str]:
    return TICKS.findall(text)


def readme_entry(cell: str, l0: dict[str, list[str]]) -> dict:
    conditional = [{"heading": m.group(1), "status": m.group(2)}
                   for m in re.finditer(r"\(`([^`]+)` added when status is `([^`]+)`\)", cell)]
    optional = [h for m in re.finditer(r"\(optional: ([^)]*)\)", cell) for h in names(m.group(1))]
    cell = re.sub(r"\([^)]*\)", "", cell)
    base = next((l0[k] for k in ("full", "lite") if f"L0 {k}" in cell), [])
    entry = {"headings": [*base, *names(cell)]}
    return {**entry, **({"conditional": conditional} if conditional else {}),
            **({"optional": optional} if optional else {})}


def file_entries(cell: str) -> list[dict]:
    entries = []
    for item in cell.split(";"):
        cut = re.search(r" iff | \(", item)
        head, tail = (item[:cut.start()], item[cut.start():]) if cut else (item, "")
        if not names(head) or names(head)[0].startswith("##"):
            continue  # components.md: one `## <component>` per component, checked by spec_check itself
        paren = tail.split("(", 1)[1] if "(" in tail else ""
        types = [t for t in TYPES if re.search(rf"\b{t}\b", paren.split("when")[0])] if tail.strip().startswith("(") else []
        when = [w for text, w in WHEN.items() if text in tail]
        for heading in names(head):
            entries.append({"heading": heading, **({"types": types} if types else {}), **({"when": when[0]} if when else {})})
    return entries


def generate(standard: Path = STANDARD) -> dict:
    doc = Doc(standard.read_text(encoding="utf-8"))
    intro = next(t.text for s in doc.sections(3) if s.title.startswith("Required headings per type") for t in s.blocks
                 if hasattr(t, "text") and "L0 full" in t.text)
    full, lite = (names(re.search(rf'"L0 {k}"(?: headings)?:([^.]*)\.', intro).group(1)) for k in ("full", "lite"))
    l0 = {"full": full, "lite": lite}
    leading = names(re.search(r"The leading headings, in order[^:]*:([^(]*)\(", intro).group(1))
    tables = [t for s in doc.sections(3) if s.title.startswith("Required headings per type") for t in s.tables]
    readme, nested, files = {}, [], {}
    for row in tables[0].rows:
        if row[0].startswith("nested spec"):
            nested = readme_entry(row[1], l0)["headings"]
        else:
            readme[row[0]] = readme_entry(row[1], l0)
    for row in tables[1].rows:
        files[row[0].strip("`")] = file_entries(row[1])
    return {"source": "skills/dark-factory/WORK-ITEM-STANDARD.md", "l0": l0, "leading": leading, "readme": readme,
            "nestedBase": nested, "files": files}


def render(standard: Path = STANDARD) -> str:
    return json.dumps(generate(standard), indent=2) + "\n"


def stale(output: Path = OUTPUT, standard: Path = STANDARD) -> str:
    """`stale` when the committed config differs from a fresh generation, else an empty string."""
    return "" if output.read_text(encoding="utf-8") == render(standard) else "stale"


def main(argv: list[str]) -> int:
    if "--check" in argv:
        verdict = stale()
        if verdict:
            print(f"{OUTPUT.name} is {verdict}: run python scripts/gen_heading_config.py", file=sys.stderr)
        return 1 if verdict else 0
    OUTPUT.write_text(render(), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
