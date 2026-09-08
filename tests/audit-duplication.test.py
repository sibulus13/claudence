#!/usr/bin/env python3
"""audit-duplication.test.py — unit tests for improve/audit.py's rules()/check_against_corpus().

  ./tests/audit-duplication.test.py     exit 0 = all pass, 1 = a failure
"""

import importlib.util
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_spec = importlib.util.spec_from_file_location('audit', os.path.join(REPO, 'improve', 'audit.py'))
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)

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


# ── rules(): bullets/table rows always counted, paragraphs only when asked ──

BULLETED = (
    '# Some doc\n\n'
    '- this bullet line is long enough on its own to clear the sixty character floor\n'
    'A plain paragraph of prose that is not a bullet or table row at all, long enough too.\n'
)

check('rules(): bullet counted without include_paragraphs',
      len(audit.rules(BULLETED)), 1)
check('rules(): bare paragraph NOT counted without include_paragraphs',
      len(audit.rules(BULLETED)),
      len([r for r in audit.rules(BULLETED) if r.startswith('-')]))
check('rules(): paragraph IS counted when include_paragraphs=True',
      len(audit.rules(BULLETED, include_paragraphs=True)) > len(audit.rules(BULLETED)), True)

FRONTMATTERED = (
    '---\nname: x\nmetadata:\n  type: feedback\n---\n\n'
    'This is a long enough prose paragraph that should be picked up as one comparable unit.\n'
)
result = audit.rules(FRONTMATTERED, include_paragraphs=True)
check('rules(): frontmatter block itself is excluded from the paragraph scan',
      any('metadata' in r or 'type: feedback' in r for r in result), False)
check('rules(): the real body paragraph after frontmatter IS picked up',
      any('long enough prose paragraph' in r for r in result), True)

# ── check_against_corpus(): finds a near-duplicate paragraph across two real files ──

with tempfile.TemporaryDirectory() as tmp:
    memdir = os.path.join(tmp, 'projects', 'proj', 'memory')
    os.makedirs(memdir)
    existing = os.path.join(memdir, 'existing.md')
    with open(existing, 'w') as fh:
        fh.write('---\nname: existing\nmetadata:\n  type: feedback\n---\n\n'
                 'When presenting a list of things, lead each bullet with the entity itself as '
                 'the bold headline rather than burying it in a table column, and pack the '
                 'detail densely inline after it.\n')
    new_file = os.path.join(memdir, 'new-one.md')
    with open(new_file, 'w') as fh:
        fh.write('---\nname: new-one\nmetadata:\n  type: feedback\n---\n\n'
                 'When presenting a list of things, lead each bullet with the entity itself as '
                 'the bold headline rather than burying it in a table column, and pack the '
                 'detail densely inline after it.\n')
    distinct_file = os.path.join(memdir, 'distinct.md')
    with open(distinct_file, 'w') as fh:
        fh.write('---\nname: distinct\nmetadata:\n  type: feedback\n---\n\n'
                 'A completely unrelated lesson about scheduling meetings around a real '
                 'calendar rather than trusting a note\'s embedded date as fact.\n')

    real_home = audit.HOME
    real_targets = audit.targets
    try:
        audit.HOME = tmp
        audit.targets = lambda: [
            ('memory/existing.md', existing),
            ('memory/new-one.md', new_file),
            ('memory/distinct.md', distinct_file),
        ]
        dups = audit.check_against_corpus(new_file)
        check('check_against_corpus: finds the near-identical paragraph', len(dups) >= 1, True)
        check('check_against_corpus: does not flag the unrelated file',
              all(d['b'] != 'memory/distinct.md' for d in dups), True)

        dups_distinct = audit.check_against_corpus(distinct_file)
        check('check_against_corpus: the genuinely distinct file has no matches',
              dups_distinct, [])
    finally:
        audit.HOME = real_home
        audit.targets = real_targets

print('%d passed, %d failed' % (PASS, FAIL))
for failure in FAILURES:
    print('FAIL | %s' % failure)
sys.exit(1 if FAIL else 0)
