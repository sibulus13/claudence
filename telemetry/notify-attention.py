#!/usr/bin/env python3
"""notify-attention.py — cross-workspace "agent needs you" signal (port of notify-attention.ps1).

Wired into Stop and PermissionRequest. Two jobs:
  1. Drop a per-pane flag file that terminal.lua's tab bar reads, so you can see
     WHICH repo alerted even when its tab belongs to a background workspace.
  2. Play the event sound — throttled to at most once per reason per window
     across ALL sessions, so N sessions finishing together don't produce a ding
     storm. The visual flags are never throttled.

Usage: notify-attention.py --reason stop|permission [--sound NAME] [--silent]

The flag is keyed by $WEZTERM_PANE, inherited from the pane's environment. Pane
id stays reliable even when a pane's reported cwd is stale, which is why it —
not cwd — is what the status bar matches a flag to a tab by. No pane means a
headless/cron/cloud agent with nowhere to navigate to, so no flag is written.
"""

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib'))

import hooklib as H   # noqa: E402

DING_WINDOW_SECS = 60


def in_scratch_dir(cwd):
    """True for a temp/scratchpad cwd — not a workspace anyone navigates to.

    On macOS a session's temp dir is a long /var/folders/... path (and
    $TMPDIR points into it), plus /tmp and /private/tmp; flagging a tab for work
    there would light up a directory the user cannot meaningfully visit.
    """
    if not cwd:
        return False
    lowered = cwd.lower()
    roots = ['/tmp', '/private/tmp', '/private/var/folders', '/var/folders']
    tmpdir = os.environ.get('TMPDIR')
    if tmpdir:
        roots.append(H.norm_cwd(tmpdir))
    for root in roots:
        root = root.lower().rstrip('/')
        if root and (lowered == root or lowered.startswith(root + '/')):
            return True
    return False


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--reason', default='stop')
    parser.add_argument('--sound', default='ring-half')
    parser.add_argument('--silent', action='store_true',
                        help='write the flag but play nothing (Stop, where '
                             'analyze-session.py owns the chime)')
    args, _unknown = parser.parse_known_args()

    data = H.read_stdin_json() or {}
    cwd = H.norm_cwd(str(data.get('cwd') or ''))
    session_id = str(data.get('session_id') or '')
    pane = os.environ.get('WEZTERM_PANE')

    if cwd and pane and not in_scratch_dir(cwd):
        attention_dir = os.path.join(H.WORKSPACES_DIR, 'attention')
        H.ensure_dir(attention_dir)
        # One file per pane: a pane runs one Claude session at a time, so a
        # re-stop overwrites. Orphans (closed panes) are reaped by the status bar.
        H.write_json_compact(os.path.join(attention_dir, 'pane-%s.json' % pane), {
            'cwd': cwd,
            'repo': cwd.rstrip('/').split('/')[-1],
            'reason': args.reason,
            'session': session_id,
            'pane': int(pane) if str(pane).isdigit() else pane,
            'ts': int(datetime.now(timezone.utc).timestamp()),
        })

    if not args.silent:
        safe_reason = ''.join(c if c.isalnum() else '-' for c in args.reason)
        stamp = os.path.join(H.WORKSPACES_DIR, '.last-ding-%s' % safe_reason)
        if H.throttle(stamp, DING_WINDOW_SECS):
            H.play_sound(args.sound)


if __name__ == '__main__':
    main()
