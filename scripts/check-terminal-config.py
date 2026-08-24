#!/usr/bin/env python3
"""check-terminal-config.py — PostToolUse guard: did that edit break the live terminal?

OBJECTIVE — a WezTerm config that crashes on reload is reported to the agent that
broke it, in the same turn, instead of to the user as a popup.

tests/configload.test.lua already catches this, and its own header records the two
days a missing module threw a runtime error on every reload. It ran only when
someone ran the suite by hand, so the same failure recurred on 2026-08-24:
terminal.lua gained a `dofile` of a module not yet symlinked into ~/.claude,
WezTerm hot-reloaded inside that window, and the first report came from the user's
screen. A check that is not attached to the event that breaks the thing is a check
that reports the breakage late.

Fires only on an edit to a Lua file the live config loads, and exits 2 on failure
so the message reaches the model as feedback rather than the transcript as
decoration. WezTerm's own exit code cannot be used here — it falls back to its
default config and exits 0 — hence the pcall-and-report-through-a-file harness.
"""

import json
import os
import subprocess
import sys

LOAD_TIMEOUT_S = 20      # a cold wezterm config load is ~0.3 s; this is a hang guard
LIVE_CONFIG = os.path.expanduser('~/.claude/terminal.lua')


def edited_path(payload):
    tool_input = payload.get('tool_input') or {}
    return str(tool_input.get('file_path') or tool_input.get('path') or '')


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0

    path = edited_path(payload)
    if not path.endswith('.lua'):
        return 0

    # The checkout is wherever ~/.claude/terminal.lua points. No install, nothing to
    # protect; not a symlink, and this machine is not running from a checkout.
    if not os.path.islink(LIVE_CONFIG):
        return 0
    repo = os.path.dirname(os.path.realpath(LIVE_CONFIG))
    harness = os.path.join(repo, 'tests', 'configload.test.lua')
    if not os.path.exists(harness):
        return 0

    # Only Lua that the config actually loads — a .lua file elsewhere on disk is
    # none of this hook's business.
    real = os.path.realpath(path)
    if not (real.startswith(repo + os.sep)
            or real.startswith(os.path.realpath(os.path.expanduser('~/.claude')) + os.sep)):
        return 0

    result = os.path.join(repo, 'tests', '.last-load-results.txt')
    try:
        os.remove(result)
    except OSError:
        pass
    try:
        subprocess.run(['wezterm', '--config-file', harness, 'show-keys'],
                       capture_output=True, timeout=LOAD_TIMEOUT_S)
    except Exception:
        return 0      # no wezterm, no mux, no verdict — never block on the guard itself

    try:
        with open(result) as fh:
            report = fh.read().strip()
    except OSError:
        return 0

    if 'FAIL' not in report:
        return 0

    sys.stderr.write(
        'The live WezTerm config no longer loads after editing %s:\n%s\n'
        'Every reload of the user\'s terminal now throws this. Fix it before doing '
        'anything else — a `dofile` of a module in ~/.claude needs that module '
        'symlinked there (setup.sh LINKS), not just present in the checkout.\n'
        % (path, report))
    return 2


if __name__ == '__main__':
    sys.exit(main())
