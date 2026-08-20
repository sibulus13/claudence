#!/usr/bin/env python3
"""log-permission.py — PermissionRequest hook (port of log-permission.ps1).

OBJECTIVE — record what needed asking, so the allow list can be earned from evidence.

Distinguishes a first-time block from a repeat:
  permission_req   — first time this tool type needed approval this session
  perm_req_repeat  — same tool type blocked again; it should be in the allow list

Two upstream bugs are fixed here (see docs/MACOS-PORT.md):
  * log-permission.ps1 wrote the first-time event as 'perm_req', but every
    reader (analyze-session, classification, the Pester tests) looks for
    'permission_req' — so first-time requests were invisible to scoring and the
    repeat check never matched, meaning 'perm_req_repeat' was never emitted.
  * it wrote KPIs to telemetry/current-session.json while log-prompt.py and the
    status bar use telemetry/state-<session_id>.json, so the permission counters
    it maintained were never read by anything.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib'))

import hooklib as H   # noqa: E402

PREVIEW_LIMIT = 120


def main():
    data = H.read_stdin_json()
    if not data:
        return

    session_id = str(data.get('session_id') or 'unknown')
    tool_name = str(data.get('tool_name') or 'unknown')
    cwd = str(data.get('cwd') or os.environ.get('PWD') or os.getcwd())
    preview = H.tool_input_preview(data.get('tool_input'), PREVIEW_LIMIT)

    session_path = H.session_file(session_id)
    state_path = H.state_file(session_id)
    H.ensure_dir(H.SESSIONS_DIR)

    is_repeat = any(
        e.get('event') == 'permission_req' and e.get('tool') == tool_name
        for e in H.read_jsonl(session_path)
    )
    event_type = 'perm_req_repeat' if is_repeat else 'permission_req'

    H.append_jsonl(session_path, {
        'ts': H.now_iso(),
        'session_id': session_id,
        'event': event_type,
        'tool': tool_name,
        'input_preview': preview,
        'cwd': cwd,
    })

    state = H.read_json(state_path)
    if not isinstance(state, dict) or state.get('session_id') != session_id:
        state = {
            'session_id': session_id,
            'prompts': 0,
            'overrides': 0,
            'additions': 0,
            'denial_contexts': 0,
            'perm_reqs': 0,
            'perm_repeats': 0,
            'started_at': H.now_iso(),
        }
    key = 'perm_repeats' if is_repeat else 'perm_reqs'
    state[key] = int(state.get(key, 0)) + 1
    H.write_json(state_path, state)


if __name__ == '__main__':
    main()
