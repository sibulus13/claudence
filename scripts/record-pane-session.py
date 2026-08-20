#!/usr/bin/env python3
"""record-pane-session.py — bind a WezTerm pane to its Claude session (port of

OBJECTIVE — a terminal pane can be traced back to the session that owns it.
record-pane-session.ps1).

terminal.lua uses this to restore the EXACT conversation on restart
(`claude --resume <id>`) instead of guessing the cwd's most recent one
(`claude --continue`) — the guess is wrong whenever a repo holds more than one
session.

Wired into SessionStart, which fires on startup / resume / clear: every point at
which a pane's session id is established or changes. The id and cwd arrive in the
hook payload; the pane comes from $WEZTERM_PANE, inherited from the pane's
environment. No pane means a headless/cron/cloud agent with nothing to restore
into, so nothing is written.
"""

import os
import re
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'telemetry', 'lib'))

import hooklib as H   # noqa: E402

ORPHAN_MAX_AGE_DAYS = 7


def main():
    data = H.read_stdin_json() or {}
    session_id = str(data.get('session_id') or '')
    cwd = H.norm_cwd(str(data.get('cwd') or ''))
    pane = os.environ.get('WEZTERM_PANE')

    if not session_id or not pane:
        return

    pane_dir = os.path.join(H.WORKSPACES_DIR, 'pane-sessions')
    H.ensure_dir(pane_dir)
    H.write_json_compact(os.path.join(pane_dir, 'pane-%s.json' % pane), {
        'session': session_id,
        'cwd': cwd,
        'pane': int(pane) if str(pane).isdigit() else pane,
        'ts': int(datetime.now(timezone.utc).timestamp()),
    })

    # Reap mappings for panes closed long ago. An active pane rewrites its file
    # on every SessionStart, so only truly dead panes expire — and a missing file
    # just degrades restore to `claude --continue`, never a crash.
    cutoff = time.time() - ORPHAN_MAX_AGE_DAYS * 86400
    try:
        for name in os.listdir(pane_dir):
            if not re.match(r'^pane-.+\.json$', name):
                continue
            path = os.path.join(pane_dir, name)
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
    except Exception:
        pass


if __name__ == '__main__':
    main()
