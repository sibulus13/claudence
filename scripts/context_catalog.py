"""Which lifecycle class is a fleet doc in? Its own frontmatter `lifecycle:` wins; otherwise the first matching glob in
`<fleet docs>/lifecycle.json` ({"rules": [{"glob", "lifecycle", "updatedBy"?}]}) decides.

  live       kept current by a named trigger (`updatedBy`, or `updated-by:` in frontmatter)
  generated  built from a source of truth; never edited by hand
  snapshot   written once and dated; archived when unread, never deleted
  scratch    made for one task; archived when unread, then deleted
"""
from __future__ import annotations

import json
import re
from fnmatch import fnmatchcase
from pathlib import Path

CLASSES = ("live", "generated", "snapshot", "scratch")
CATALOGUE = "lifecycle.json"
SKIP_PARTS = {".git", "archive", "node_modules"}
FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)


def rules(fleet: Path) -> list[dict]:
    path = fleet / CATALOGUE
    return json.loads(path.read_text(encoding="utf-8")).get("rules", []) if path.exists() else []


def frontmatter(p: Path) -> dict[str, str]:
    m = FRONTMATTER.match(p.read_text(encoding="utf-8", errors="replace"))
    pairs = (line.split(":", 1) for line in m.group(1).splitlines() if ":" in line) if m else []
    return {k.strip(): v.strip().strip("\"'") for k, v in pairs}


def docs(fleet: Path) -> list[Path]:
    return sorted(p for p in fleet.rglob("*.md") if not SKIP_PARTS & set(p.relative_to(fleet).parts))


def classify(fleet: Path, p: Path, catalogue: list[dict]) -> dict | None:
    fm = frontmatter(p)
    if fm.get("lifecycle"):
        return {"lifecycle": fm["lifecycle"], "updatedBy": fm.get("updated-by")}
    rel = p.relative_to(fleet).as_posix()
    return next((r for r in catalogue if fnmatchcase(rel, r["glob"])), None)
