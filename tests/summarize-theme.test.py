#!/usr/bin/env python3
"""summarize-theme.test.py — unit tests for telemetry/summarize-theme.py's pure logic.

Mocks the actual `claude` subprocess call — the test suite must never make a real
external/API call. Only gather_prompts(), build_message_block(), clean_summary(),
and write_back() are exercised here.

  ./tests/summarize-theme.test.py     exit 0 = all pass, 1 = a failure
"""

import importlib.util
import json
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'telemetry', 'lib'))
import hooklib as H   # noqa: E402

_spec = importlib.util.spec_from_file_location(
    'summarize_theme', os.path.join(REPO, 'telemetry', 'summarize-theme.py'))
st = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(st)

PASS = 0
FAIL = 0
FAILURES = []


def check(name, actual, expected):
    global PASS, FAIL
    if actual == expected:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append('%s\n    expected %r, got %r' % (name, expected, actual))


with tempfile.TemporaryDirectory() as tmp:
    real_home = H.HOME
    H.HOME = tmp
    H.CLAUDE_DIR = os.path.join(tmp, '.claude')
    H.TELEMETRY_DIR = os.path.join(H.CLAUDE_DIR, 'telemetry')
    H.SESSIONS_DIR = os.path.join(H.TELEMETRY_DIR, 'sessions')
    os.makedirs(H.SESSIONS_DIR)
    st.H = H

    sid = 'test-session'
    session_path = H.session_file(sid)
    events = [
        {'event': 'prompt', 'ts': '2026-08-31T10:00:00-07:00', 'classification': 'first_prompt',
         'prompt_text': 'First message of the theme'},
        {'event': 'prompt', 'ts': '2026-08-31T10:00:05-07:00', 'classification': 'system_notification',
         'prompt_text': '<task-notification>ignore me</task-notification>'},
        {'event': 'prompt', 'ts': '2026-08-31T10:01:00-07:00', 'classification': 'addition',
         'prompt_text': 'Second, related message'},
        {'event': 'prompt', 'ts': '2026-08-31T09:59:00-07:00', 'classification': 'followup',
         'prompt_text': 'A message from BEFORE this theme started — excluded'},
    ]
    with open(session_path, 'w', encoding='utf-8') as fh:
        for e in events:
            fh.write(json.dumps(e) + '\n')

    gathered = st.gather_prompts(sid, '2026-08-31T10:00:00-07:00')
    check('gather_prompts: excludes system_notification', gathered,
          ['First message of the theme', 'Second, related message'])
    check('gather_prompts: unknown theme_ts -> empty', st.gather_prompts(sid, 'not-a-date'), [])

    block = st.build_message_block(['one', 'two', 'three'])
    check('build_message_block: joins with a separator', block, 'one\n---\ntwo\n---\nthree')
    check('build_message_block: empty in -> empty out', st.build_message_block([]), '')

    long_texts = ['x' * 3000, 'y' * 3000]
    capped = st.build_message_block(long_texts)
    check('build_message_block: respects the total char budget',
          len(capped) <= st.MAX_PROMPT_CHARS + 10, True)

    check('clean_summary: short text passes through unchanged',
          st.clean_summary('Fix the login bug'), 'Fix the login bug')
    check('clean_summary: multi-line input takes only the first line',
          st.clean_summary('First line here\nsecond line ignored'), 'First line here')
    long_summary = 'a very long summary sentence that clearly exceeds the sixty character budget here'
    result = st.clean_summary(long_summary)
    check('clean_summary: truncates at a word boundary with an ellipsis',
          result.endswith('…') and len(result) <= st.MAX_LABEL_CHARS + 1, True)
    check('clean_summary: no mid-word cut',
          any(long_summary.startswith(result[:-1].rstrip('.,;:!?')) for _ in [0]), True)

    state_path = H.state_file(sid)
    H.write_json(state_path, {
        'session_id': sid,
        'themes': [
            {'label': 'old extractive label', 'ts': '2026-08-31T10:00:00-07:00', 'turns': 2},
            {'label': 'a different, older theme', 'ts': '2026-08-31T09:00:00-07:00', 'turns': 1},
        ],
    })
    st.write_back(sid, '2026-08-31T10:00:00-07:00', 'a real semantic summary')
    state = H.read_json(state_path)
    check('write_back: updates the matching theme by ts',
          state['themes'][0]['label'], 'a real semantic summary')
    check('write_back: leaves the other theme untouched',
          state['themes'][1]['label'], 'a different, older theme')

    st.write_back(sid, '1999-01-01T00:00:00-07:00', 'should not appear anywhere')
    state = H.read_json(state_path)
    check('write_back: a rotated-out theme_ts is silently skipped',
          any(t.get('label') == 'should not appear anywhere' for t in state['themes']), False)

    H.HOME = real_home

print('%d passed, %d failed' % (PASS, FAIL))
for failure in FAILURES:
    print('FAIL | %s' % failure)
sys.exit(1 if FAIL else 0)
