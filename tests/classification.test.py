#!/usr/bin/env python3
"""classification.test.py — unit tests for telemetry/lib/classification.py.

A one-for-one port of classification.tests.ps1 (Pester 5), which cannot run here:
there is no PowerShell on macOS. Same cases, same expectations, plus a few the
Pester suite did not cover (timestamp shapes, and the permission event name that
the PowerShell writer got wrong).

  ./tests/classification.test.py     exit 0 = all pass, 1 = a failure
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'telemetry', 'lib'))

from classification import (   # noqa: E402
    classify, is_addition, is_denial_context, is_override,
)

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


def event(name, ts, **extra):
    out = {'event': name, 'ts': ts}
    out.update(extra)
    return out


# ── is_denial_context ────────────────────────────────────────────────────────

check('denial: null events', is_denial_context(None), False)
check('denial: empty events', is_denial_context([]), False)

check('denial: perm_req with no matching tool_done -> denied', is_denial_context([
    event('prompt', '2026-01-01T10:00:00Z', classification='first_prompt'),
    event('permission_req', '2026-01-01T10:00:05Z', tool='Bash'),
]), True)

check('denial: perm_req_repeat with no tool_done -> denied', is_denial_context([
    event('prompt', '2026-01-01T10:00:00Z', classification='first_prompt'),
    event('perm_req_repeat', '2026-01-01T10:00:05Z', tool='Bash'),
]), True)

check('denial: perm_req followed by same-tool tool_done -> approved', is_denial_context([
    event('prompt', '2026-01-01T10:00:00Z', classification='first_prompt'),
    event('permission_req', '2026-01-01T10:00:05Z', tool='Bash'),
    event('tool_done', '2026-01-01T10:00:10Z', tool='Bash'),
]), False)

check('denial: tool_done for a different tool does not satisfy it', is_denial_context([
    event('prompt', '2026-01-01T10:00:00Z', classification='first_prompt'),
    event('permission_req', '2026-01-01T10:00:05Z', tool='Bash'),
    event('tool_done', '2026-01-01T10:00:10Z', tool='Read'),
]), True)

check('denial: ignores an unmatched perm_req from a previous turn', is_denial_context([
    event('prompt', '2026-01-01T09:00:00Z', classification='first_prompt'),
    event('permission_req', '2026-01-01T09:00:05Z', tool='Bash'),
    event('stop', '2026-01-01T09:01:00Z'),
    event('prompt', '2026-01-01T09:02:00Z', classification='followup'),
]), False)

# ── is_override ──────────────────────────────────────────────────────────────

for text in [
    "Actually, let's try a different approach",
    'No, I meant the first implementation',
    "No! That's wrong, redo it",
    "Wait, that's not what I wanted",
    "Stop, let's reconsider",
    'Undo the last change',
    "ACTUALLY let's do this differently",
]:
    check('override start-anchored: %r' % text[:28], is_override(text), True)

for text in [
    "Forget that, let's start fresh",
    'Forget this approach entirely',
    "Let's do it a different way instead",
    'Scratch that, use a simpler approach',
    'Start over with a cleaner design',
    'Never mind, keep the original',
    'Cancel that last change please',
    'Ignore that, I found the issue',
    'Disregard the previous instruction',
]:
    check('override anywhere: %r' % text[:28], is_override(text), True)

for text in [
    "Let's implement the goals screen next",
    'Also add error handling to the function',
    'Can you actually also fix the linting errors?',
    "There's no issue with that approach",
    'What does this function return?',
    ('Now that we have the API working, let\'s move on to the UI layer and '
     'implement the goals screen with the same pattern we used for budgets.'),
    '',
    '   ',
]:
    check('not override: %r' % text[:28], is_override(text), False)
check('not override: None', is_override(None), False)

# ── is_addition ──────────────────────────────────────────────────────────────

for text in [
    'Also add error handling',
    'Additionally, we need null checks throughout',
    "Note that we're running on Windows not Linux",
    "Don't forget to add the import statement at the top",
    'By the way, the API key is already in .env',
    "Oh and make it async too while you're at it",
    'One more thing - it also needs to handle the empty array case',
    'I forgot to mention it needs to validate the input first',
    'Furthermore, it should validate on the server side too',
    'Separately, we also need to update the types',
    "While you're at it, fix the formatting too",
    'ALSO make sure to run the tests',
]:
    check('addition: %r' % text[:28], is_addition(text), True)

for text in [
    "Let's implement the goals screen next",
    'What does this function return?',
    "Actually, let's do this differently",
    ("Now let's move on to the settings screen and implement the connected "
     'accounts feature using the same hook pattern.'),
    '',
]:
    check('not addition: %r' % text[:28], is_addition(text), False)
check('not addition: None', is_addition(None), False)

# ── classify ─────────────────────────────────────────────────────────────────

check('classify: empty history -> first_prompt',
      classify("Let's start building", []), 'first_prompt')
check('classify: None history -> first_prompt',
      classify('Hello', None), 'first_prompt')
check('classify: override language with no history is still first_prompt',
      classify('Actually forget that', []), 'first_prompt')

MID_RUN = [
    event('stop', '2026-01-01T09:00:00Z'),
    event('prompt', '2026-01-01T10:00:00Z'),
    event('tool_done', '2026-01-01T10:00:05Z'),
]
check('classify: mid-run neutral -> addition',
      classify('Keep going on the same task', MID_RUN), 'addition')
check('classify: mid-run override language -> addition',
      classify('Actually stop and do X instead', MID_RUN), 'addition')
check('classify: mid-run additive language -> addition',
      classify('Also make sure to handle the error case', MID_RUN), 'addition')

STOPPED = [
    event('prompt', '2026-01-01T10:00:00Z'),
    event('stop', '2026-01-01T10:01:00Z'),
]
check('classify: post-stop override language -> override',
      classify("Actually, let's scrap this and do it differently", STOPPED), 'override')
check("classify: post-stop 'instead' -> override",
      classify("Let's use a different pattern instead", STOPPED), 'override')
check('classify: post-stop additive language -> followup',
      classify('Also add error handling to that function', STOPPED), 'followup')
check("classify: post-stop 'note that' -> followup",
      classify("Note that we're on Windows so use backslashes", STOPPED), 'followup')
check('classify: post-stop neutral -> followup',
      classify("Let's implement the settings screen next", STOPPED), 'followup')
check('classify: post-stop question -> followup',
      classify("What's the best way to handle authentication here?", STOPPED), 'followup')

DENIED = [
    event('stop', '2026-01-01T09:00:00Z'),
    event('prompt', '2026-01-01T10:00:00Z', classification='first_prompt'),
    event('permission_req', '2026-01-01T10:00:05Z', tool='Bash'),
]
check('classify: unmatched perm_req -> denial_context',
      classify("Don't run that, it would delete the wrong dir", DENIED), 'denial_context')
check('classify: denial_context wins over neutral text',
      classify('Actually that command is wrong', DENIED), 'denial_context')
check('classify: denial_context wins over additive text',
      classify('Also you should avoid touching node_modules', DENIED), 'denial_context')

APPROVED = DENIED + [event('tool_done', '2026-01-01T10:00:10Z', tool='Bash')]
check('classify: approved perm_req -> addition, not denial_context',
      classify('Also update the types', APPROVED), 'addition')

check('classify: uses the most recent stop vs the most recent prompt', classify(
    "Let's continue with the next feature", [
        event('prompt', '2026-01-01T09:00:00Z'),
        event('stop', '2026-01-01T09:01:00Z'),
        event('prompt', '2026-01-01T10:00:00Z'),
        event('stop', '2026-01-01T10:01:00Z'),
    ]), 'followup')

check('classify: last prompt after last stop -> mid-run', classify(
    'Add logging too', [
        event('prompt', '2026-01-01T09:00:00Z'),
        event('stop', '2026-01-01T09:01:00Z'),
        event('prompt', '2026-01-01T10:00:00Z'),
    ]), 'addition')

# ── Timestamp shapes (not covered by the Pester suite) ───────────────────────
# The real logs are written by Python's isoformat (offset, 6-digit fraction), the
# Pester fixtures use a bare 'Z', and PowerShell's 'o' format writes 7 digits.
# All three have to compare correctly or every classification silently degrades.

check('ts: 7-digit fraction + offset (PowerShell "o") compares correctly', classify(
    'next thing', [
        event('prompt', '2026-01-01T10:00:00.1234567-08:00'),
        event('stop', '2026-01-01T10:01:00.7654321-08:00'),
    ]), 'followup')

check('ts: mixed Z and offset across the same session', classify(
    'next thing', [
        event('prompt', '2026-01-01T18:00:00Z'),
        event('stop', '2026-01-01T10:01:00.000000-08:00'),
    ]), 'followup')

check('ts: unparseable timestamps degrade to mid-run, never crash', classify(
    'keep going', [
        event('prompt', 'not-a-timestamp'),
        event('stop', 'also-not-a-timestamp'),
    ]), 'addition')

# ── Permission event naming (the upstream bug this port fixes) ───────────────
# log-permission.ps1 wrote the first-time event as 'perm_req', but every reader
# looks for 'permission_req'. A log full of 'perm_req' therefore scored as zero
# friction. The port writes 'permission_req'; assert the reader agrees.

check("denial: legacy 'perm_req' name is NOT recognised (documents the bug)",
      is_denial_context([
          event('prompt', '2026-01-01T10:00:00Z'),
          event('perm_req', '2026-01-01T10:00:05Z', tool='Bash'),
      ]), False)

print('%d passed, %d failed' % (PASS, FAIL))
for failure in FAILURES:
    print('FAIL | %s' % failure)
sys.exit(1 if FAIL else 0)
