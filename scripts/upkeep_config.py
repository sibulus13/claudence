"""Shared runtime config for the harness upkeep scripts (harness_lint, ledger_draft, projects_sweep, tasks_audit).

Private inventory (repo tree, deny patterns, task names, skip lists) is never committed here: it is read from
`<root>/docs/fleet/upkeep.config.json` (docs/fleet is a private, git-ignored folder). Every key is optional.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
from pathlib import Path

# Child processes (git, powershell) must not flash a console window when a daemon launches the scripts.
HIDDEN: dict = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}

DEFAULTS: dict = {
    "repoRoot": None,  # tree holding the project repos (ledger drafts, repo CLAUDE.md budgets)
    "repoSkip": ["node_modules", "_Archive", ".venv", "worktrees", "foreman-worktrees", ".next"],
    "denyList": [],  # harness_lint: [{"pattern": regex, "label": str}]
    "denyIgnoreLine": None,  # harness_lint: a deny hit on a line matching this regex is history, not a finding
    "pathCheckSkip": [],  # harness_lint: globs relative to root whose paths are historical
    "fleetMemoryDir": None,  # harness_lint: name of the fleet-wide memory dir under projects/
    "budgets": {
        "globalClaudeMdLines": 120,
        "fleetIndexLines": 15,
        "projectIndexLines": 70,
        "projectIndexBytes": 25_000,
        "repoClaudeMdLines": 200,
    },
    "ledgerFile": "docs/fleet/LEDGER.md",
    "draftsDir": "docs/fleet/drafts",
    "ledgerDraftMinCommits": 10,  # a day above this with no LEDGER row is flagged
    "sweepMinAgeDays": 7,
    "sweepTempPatterns": [  # projects/ dir-name regexes (cwd under Temp or a probe) that are clutter
        r"-AppData-Local-Temp-remember-summarizer-cwd-",
        r"-AppData-Local-Temp-claude-.*-scratchpad",
        r"^harness-e2e-",
        r"^pp-probe-",
        r"^tmp-",
    ],
    "sweepWorktreePatterns": [r"--git-foreman-worktrees-", r"--claude-worktrees-"],  # a "/." in a cwd encodes to "--"
    "tasksFailingResultsAllowed": [0, 267009, 267011],  # 0 ok; 267009 running; 267011 not yet run
    "tasksIgnoreRegex": ["^NVIDIA", "^OneDrive", "^Adobe", "^Google", "^MicrosoftEdge"],  # vendor updaters
    "tasksDeadDays": 30,
    "tasksNextRunFarDays": 365,
}


def config_path(root: Path) -> Path:
    return root / "docs" / "fleet" / "upkeep.config.json"


def load_config(path: Path) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    if path.exists():
        user = json.loads(path.read_text(encoding="utf-8"))
        cfg["budgets"].update(user.pop("budgets", {}))
        cfg.update(user)
    return cfg


# ---- seen vs delivered ---------------------------------------------------------------------------------------------
# A scan writes `<name>.pending.json`. The committed `<name>.json` is the baseline for "new" and moves only on
# `--commit`, which the Cortex job calls after the TeleFi publish succeeded (or when there was nothing to publish).
# A failed publish leaves the baseline alone, so the same findings are new again next run. A finding that was fixed
# and committed as fixed, then reappears, is new again by design.

def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def pending_path(out: Path) -> Path:
    return out.with_name(out.stem + ".pending.json")


def previous_ids(out: Path) -> set[str] | None:
    """Ids in the committed report; None (no baseline: everything is new) when it is missing or unreadable."""
    try:
        return {f["id"] for f in json.loads(out.read_text(encoding="utf-8"))["findings"]}
    except (OSError, ValueError, KeyError, TypeError):  # boundary: a torn or hand-edited baseline must not stop the job
        return None


def store_pending(out: Path, report: dict) -> None:
    write_atomic(pending_path(out), json.dumps(report, indent=1))


def commit_pending(out: Path) -> bool:
    pending = pending_path(out)
    if not pending.exists():
        return False
    os.replace(pending, out)
    return True
