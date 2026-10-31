"""The CK-4 heading config is generated from the standard's tables and must not drift from them.

    python -m pytest ~/.claude/tests/test_gen_heading_config.py -q
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CLAUDE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLAUDE / "scripts"))
import gen_heading_config  # noqa: E402


def test_committed_config_matches_the_standard() -> None:
    # spec-gate-checker/AC-2
    r = subprocess.run([sys.executable, str(CLAUDE / "scripts" / "gen_heading_config.py"), "--check"], capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, "contracts/work-item.headings.v2.json is stale: run scripts/gen_heading_config.py"


def test_generated_tables_carry_the_standards_headings() -> None:
    # spec-gate-checker/AC-2
    cfg = gen_heading_config.generate()
    assert cfg["readme"]["feature"]["headings"] == cfg["l0"]["full"] and len(cfg["l0"]["full"]) == 8
    assert cfg["readme"]["integration"]["headings"][-1] == "External contract"
    assert cfg["readme"]["data-collection"]["headings"][-2:] == ["Sample size", "Stopping rule"]
    assert cfg["readme"]["experiment"]["conditional"] == [{"heading": "Promoted to", "status": "promoted"}]
    assert cfg["nestedBase"] == cfg["l0"]["lite"]
    arch = {e["heading"]: e for e in cfg["files"]["architecture.md"]}
    assert arch["Components"]["types"] == ["feature", "integration"]
    assert arch["Lifecycle"]["when"] == "lifecycle"
    assert arch["Work breakdown"]["when"] == "multi-package"
    assert arch["Call chains"]["when"] == "architecture"
    assert [e["heading"] for e in cfg["files"]["data.md"]] == ["Schema", "Contracts", "Migration and back-compat"]
    assert json.loads((CLAUDE / "contracts" / "work-item.headings.v2.json").read_text(encoding="utf-8")) == cfg
