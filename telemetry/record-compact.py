#!/usr/bin/env python3
"""record-compact.py — PostCompact hook (port of record-compact.ps1).

OBJECTIVE — know that context was lost, so a later gap is explained rather than mysterious.

Captures the compaction summary in the session log so a retrospective can
reconstruct what happened across a compaction boundary instead of losing the
first half of the session.

PostCompact payload fields: session_id, summary, trigger ("manual"|"auto").
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib'))

import hooklib as H   # noqa: E402


def main():
    data = H.read_stdin_json()
    if not data:
        return

    session_id = str(data.get('session_id') or 'unknown')
    H.append_jsonl(H.session_file(session_id), {
        'ts': H.now_iso(),
        'session_id': session_id,
        'event': 'compact',
        'trigger': str(data.get('trigger') or 'unknown'),
        'summary': str(data.get('summary') or ''),
    })


if __name__ == '__main__':
    main()
