#!/usr/bin/env python3
"""frustration-streaks.test.py — unit tests for analyze-session.py's frustration_streaks().

  ./tests/frustration-streaks.test.py     exit 0 = all pass, 1 = a failure
"""

import importlib.util
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'telemetry', 'lib'))

_spec = importlib.util.spec_from_file_location(
    'analyze_session', os.path.join(REPO, 'telemetry', 'analyze-session.py'))
analyze_session = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(analyze_session)
frustration_streaks = analyze_session.frustration_streaks

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


def prompt(text, classification, ts):
    return {'event': 'prompt', 'prompt_text': text, 'classification': classification, 'ts': ts}


check('no friction -> no streaks', frustration_streaks([
    prompt('a', 'followup', '1'), prompt('b', 'first_prompt', '2'),
]), [])

check('single override -> no streak (below the minimum)', frustration_streaks([
    prompt('a', 'followup', '1'), prompt('b', 'override', '2'), prompt('c', 'followup', '3'),
]), [])

result = frustration_streaks([
    prompt('followup one', 'followup', '1'),
    prompt('also do X', 'addition', '2'),
    prompt('also do Y', 'addition', '3'),
    prompt('followup two', 'followup', '4'),
])
check('two consecutive additions -> one streak', len(result), 1)
check('streak length is 2', result[0]['length'] if result else None, 2)
check('streak kinds recorded', result[0]['kinds'] if result else None, ['addition', 'addition'])

result = frustration_streaks([
    prompt('a', 'override', '1'), prompt('b', 'addition', '2'), prompt('c', 'denial_context', '3'),
])
check('mixed friction kinds still form one streak', len(result), 1)
check('mixed streak length is 3', result[0]['length'] if result else None, 3)

result = frustration_streaks([
    prompt('a', 'override', '1'),
    prompt('<task-notification>done</task-notification>', 'system_notification', '2'),
    prompt('b', 'addition', '3'),
])
check('a system_notification in between breaks the streak', result, [])

# A redelivered identical prompt (Claude Code re-fires a queued message on each Stop
# until it's actually consumed) collapses to one occurrence — 4 identical bodies in a
# row must read as nothing, not a length-4 streak of repeated user frustration.
result = frustration_streaks([
    prompt('Can we consolidate the docs', 'followup', '1'),
    prompt('Can we consolidate the docs', 'addition', '2'),
    prompt('Can we consolidate the docs', 'addition', '3'),
    prompt('Can we consolidate the docs', 'addition', '4'),
])
check('identical redelivered text collapses to one, no streak', result, [])

result = frustration_streaks([
    prompt('I still see the baseline risk language', 'addition', '1'),
    prompt('you are really telling me only 1-2 diagrams', 'addition', '2'),
])
check('two distinct consecutive corrections -> a real streak', len(result), 1)
check('distinct-correction streak length is 2', result[0]['length'] if result else None, 2)

print('%d passed, %d failed' % (PASS, FAIL))
for failure in FAILURES:
    print('FAIL | %s' % failure)
sys.exit(1 if FAIL else 0)
