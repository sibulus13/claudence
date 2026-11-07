"""The context index: a table of contents of local context, by role and topic, that the researcher reads first and
grows as it explores (docs/work/context-index).

  $FLEET_DOCS/CONTEXT_INDEX.md      root: one row per area, linking its file
  $FLEET_DOCS/context/<area>.md     | Topic | Where | Kind | Summary | Verified |
                                    Where = an absolute `file:line`, or a link to another area file (nesting)

    python context_index.py lookup <term> [<term> ...]   entries whose row holds every term, with their area
    python context_index.py check                        broken paths, area files not reachable from the root, undated entries
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from fleet_paths import fleet_docs_dir

ROOT = "CONTEXT_INDEX.md"
AREAS = "context"
LINK = re.compile(r"\]\(([^)#\s]+\.md)\)")
CODE_PATH = re.compile(r"`([A-Za-z]:/[^`]+?)(?::\d+(?:-\d+)?)?`")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
COLUMNS = ("topic", "where", "kind", "summary", "verified")


def rows(p: Path) -> list[list[str]]:
    """Body rows of the markdown tables in one file, as stripped cells."""
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    return [[c.strip() for c in line.strip().strip("|").split("|")] for i, line in enumerate(lines)
            if line.startswith("|") and not line.startswith("|-")
            and not (i + 1 < len(lines) and lines[i + 1].startswith("|-"))]


def area_files(fleet: Path) -> list[Path]:
    d = fleet / AREAS
    return sorted(d.glob("*.md")) if d.is_dir() else []


def entries(fleet: Path) -> list[dict]:
    out = []
    for p in area_files(fleet):
        for r in rows(p):
            if len(r) >= len(COLUMNS):
                out.append({"area": p.name, **dict(zip(COLUMNS, r)), "file": p})
    return out


def lookup(fleet: Path, terms: list[str]) -> list[dict]:
    wanted = [t.lower() for t in terms]
    return [e for e in entries(fleet)
            if all(t in " ".join(e[c] for c in COLUMNS).lower() for t in wanted)]


def reachable(fleet: Path) -> set[Path]:
    """Area files reachable from the root by links, following nesting."""
    seen: set[Path] = set()
    todo = [fleet / ROOT]
    while todo:
        p = todo.pop()
        if not p.exists():
            continue
        for target in LINK.findall(p.read_text(encoding="utf-8", errors="replace")):
            q = (p.parent / target).resolve()
            if q not in seen and q.parent == (fleet / AREAS).resolve():
                seen.add(q)
                todo.append(q)
    return seen


def check(fleet: Path) -> list[dict]:
    """Findings as {path, detail, key}: a missing root, broken references, orphan areas, undated entries."""
    if not (fleet / ROOT).exists():
        return [{"path": ROOT, "detail": "area files exist but no context index root", "key": "root"}] if area_files(fleet) else []
    out = []
    linked = reachable(fleet)
    for p in area_files(fleet):
        if p.resolve() not in linked:
            out.append({"path": f"{AREAS}/{p.name}", "detail": "area file not reachable from CONTEXT_INDEX.md",
                        "key": f"orphan|{p.name}"})
    for e in entries(fleet):
        where = f"{AREAS}/{e['area']}"
        for target in CODE_PATH.findall(e["where"]):
            if not Path(target).exists():
                out.append({"path": where, "detail": f"{e['topic']}: {target} does not exist", "key": f"gone|{target}"})
        for target in LINK.findall(e["where"]):
            if not (e["file"].parent / target).exists():
                out.append({"path": where, "detail": f"{e['topic']}: link {target} is broken", "key": f"link|{target}"})
        if not DATE.match(e["verified"]):
            out.append({"path": where, "detail": f"{e['topic']}: no Verified date", "key": f"date|{e['topic']}"})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("lookup").add_argument("terms", nargs="+")
    sub.add_parser("check")
    args = ap.parse_args(argv)
    fleet = fleet_docs_dir()
    if args.cmd == "lookup":
        hits = lookup(fleet, args.terms)
        for e in hits:
            print(f"[{e['area']}] {e['topic']} | {e['where']} | {e['kind']} | {e['summary']} | {e['verified']}")
        if not hits:
            print(f"no entry for {' '.join(args.terms)}: explore, then add one to {(fleet / AREAS).as_posix()}/<area>.md")
        return 0
    found = check(fleet)
    for f in found:
        print(f"{f['path']}: {f['detail']}")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
