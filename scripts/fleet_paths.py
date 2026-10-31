"""Where the fleet lives: the one owner of the repo-tree root and of the private fleet docs folder.

- `REPO_ROOT`: env `FLEET_ROOT`, else `D:/repo` (the tree of project repos).
- `fleet_docs_dir()`: env `FLEET_DOCS`, else `REPO_ROOT/docs` (the private fleet documentation repo: ledger, plans,
  audits, upkeep config). Read at call time so a test can point it at a temp dir.
Everything that needs either path imports it from here; nothing else spells them.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(os.environ.get("FLEET_ROOT") or "D:/repo")


def fleet_docs_dir() -> Path:
    return Path(os.environ.get("FLEET_DOCS") or REPO_ROOT / "docs")
