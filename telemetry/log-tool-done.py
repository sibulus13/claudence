#!/usr/bin/env python3
"""log-tool-done.py — PostToolUse hook (port of log-tool-done.ps1).

Logs every tool completion so analyze-session.py can pair it with a preceding
PermissionRequest and infer approve-vs-deny: a request with a matching later
completion was approved, one without was denied.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib'))

import hooklib as H   # noqa: E402

PREVIEW_LIMIT = 80


def main():
    data = H.read_stdin_json()
    if not data:
        return

    session_id = str(data.get('session_id') or 'unknown')
    H.append_jsonl(H.session_file(session_id), {
        'ts': H.now_iso(),
        'session_id': session_id,
        'event': 'tool_done',
        'tool': str(data.get('tool_name') or 'unknown'),
        'input_preview': H.tool_input_preview(data.get('tool_input'), PREVIEW_LIMIT),
    })


if __name__ == '__main__':
    main()
