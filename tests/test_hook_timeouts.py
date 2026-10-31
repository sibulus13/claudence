"""Every hook we own declares a bounded timeout, so a hung hook cannot stall a session.

    python -m pytest ~/.claude/tests/test_hook_timeouts.py -q

Plugin hooks are not ours to edit (the plugin cache is overwritten on update); this covers the settings files we own.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

OWNED_SETTINGS = [
    Path.home() / ".claude" / "settings.json",
    Path("D:/repo/.claude/settings.json"),
]
MAX_TIMEOUT_S = 120  # above this a hang is indistinguishable from a stall


def hooks_of(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    for event, groups in data.get("hooks", {}).items():
        for group in groups:
            for hook in group.get("hooks", []):
                yield event, hook


@pytest.mark.parametrize("path", [p for p in OWNED_SETTINGS if p.exists()], ids=str)
def test_every_owned_hook_has_a_bounded_timeout(path: Path):
    missing = [f"{ev}: {h.get('command', '')[:70]}" for ev, h in hooks_of(path)
               if not isinstance(h.get("timeout"), (int, float)) or not 0 < h["timeout"] <= MAX_TIMEOUT_S]
    assert not missing, "hooks without a bounded timeout:\n" + "\n".join(missing)
