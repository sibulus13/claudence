"""AC-9 of docs/work/spec-references-envelope: the new rules never turn an existing item from passing to failing.

Standalone (no --require-sections), CK-47/48/49 may only ERROR on a README that already has a References or Operating
envelope heading; on every other README a missing section is a warning. Walks every work item in the fleet.

    python -m pytest ~/.claude/tests/test_new_rules_regression.py -q
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

CLAUDE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLAUDE / "scripts"))
import fleet_paths  # noqa: E402
import spec_check  # noqa: E402

LEADING = re.compile(r"^## (References|Operating envelope)\s*$", re.M | re.I)
ROOTS = [*fleet_paths.REPO_ROOT.glob("*/*/docs/work"), *fleet_paths.REPO_ROOT.glob("*/docs/work"), CLAUDE / "docs" / "work"]
READMES = sorted({p for root in ROOTS if "_Archive" not in root.parts for p in root.glob("*/README.md")})


def test_walk_roots_exist() -> None:
    # spec-references-envelope/AC-9 (fixture 9.3)
    assert (CLAUDE / "docs" / "work").is_dir() and READMES


@pytest.mark.parametrize("readme", READMES, ids=[p.relative_to(p.parents[3]).as_posix() for p in READMES])
def test_new_rules_only_error_where_the_sections_exist(readme: Path) -> None:
    # spec-references-envelope/AC-9 (fixtures 9.1, 9.2)
    if LEADING.search(readme.read_text(encoding="utf-8", errors="replace")):
        pytest.skip("item carries the sections: CK-47..49 errors there are its own")
    try:
        errors, _ = spec_check.check_item(readme, readme.parents[3])
    except (OSError, ValueError, spec_check.ToolError) as e:
        pytest.skip(f"not a v2 item here: {e}")
    new = [e for e in errors if e.split(":", 1)[0] in ("CK-47", "CK-48", "CK-49")]
    assert new == [], new
