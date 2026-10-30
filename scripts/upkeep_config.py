"""Shared runtime config for the harness upkeep scripts (harness_lint, ledger_draft, projects_sweep, tasks_audit).

Private inventory (repo tree, deny patterns, task names, skip lists) is never committed here: it is read from
`<root>/docs/fleet/upkeep.config.json` (docs/fleet is a private, git-ignored folder). Every key is optional.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

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
    "ledgerDraftLookbackDays": 7,
    "sweepMinAgeDays": 7,
    "sweepTempPatterns": [  # projects/ dir-name regexes (cwd under Temp or a probe) that are clutter
        r"-AppData-Local-Temp-remember-summarizer-cwd-",
        r"-AppData-Local-Temp-claude-.*-scratchpad",
        r"^harness-e2e-",
        r"^pp-probe-",
        r"^tmp-",
    ],
    "sweepWorktreePatterns": [r"--git-foreman-worktrees-", r"-\.claude-worktrees-"],
    "tasksFailingResultsAllowed": [0, 267009, 267011],  # 0 ok; 267009 running; 267011 not yet run
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
