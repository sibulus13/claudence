#!/usr/bin/env python3
"""workspace-state.py — SessionStart hook.

Points a fresh agent at the workspace's state contract, so it does not have to
guess which of several overlapping records to read first.

The contract is five files, by convention, looked for in `docs/` then the repo
root. Legacy names are accepted so this works in repos that predate it:

  OVERVIEW.md  what it is, who it serves, the baseline  (README.md)
  STATE.md     where the project is, one page          (context.md, workflow_state.md)
  TODO.md      Now / Next / Backlog                    (todo.md, ROADMAP.md, BACKLOG.md)
  JOURNAL.md   dated why-the-direction-changed         (CHANGELOG.md is NOT this)
  DECISIONS.md ADR-lite journal                        (ADR.md)

Beyond listing them, it inlines the parts a fresh session would otherwise have
to reconstruct by hand:

  TODO.md `## Now`     what is in flight or blocked on a person
  TODO.md `## Next`    the immediate next steps, agreed and unblocked
  JOURNAL.md head      the newest dated entry's headings — latest decisions
  git log              the last commits — latest implementations

The last two exist because neither file answers "what happened last session" on
its own: the journal records *why the direction changed*, git records *what
changed*, and joining them is exactly the derivation this contract exists to
spare a fresh session. The commit log is also the only record that is a
byproduct of the work rather than a chore alongside it, so it cannot go stale.

Silent when a workspace has none of these: no nagging, and no noise in repos
this convention does not apply to. Standard library only, so it runs identically
under the Homebrew and Xcode python3 builds.
"""

import json
import os
import re
import subprocess
import sys

# canonical name -> (what it is, accepted aliases)
CONTRACT = (
    ('OVERVIEW.md', 'what it is, and the baseline it must beat', ('README.md',)),
    ('STATE.md', 'where the project is', ('context.md', 'workflow_state.md', 'KNOWLEDGE.md')),
    ('TODO.md', 'Now / Next / Backlog', ('todo.md', 'ROADMAP.md', 'BACKLOG.md')),
    ('JOURNAL.md', 'why the direction changed', ('journal.md',)),
    ('DECISIONS.md', 'decisions and assumptions', ('ADR.md', 'decisions.md')),
)
SEARCH_DIRS = ('docs', 'research', '.')
NOW_HEADINGS = ('## now', '## 1 · now', '## in flight')
MAX_NOW_LINES = 14
NEXT_HEADINGS = ('## next', '## next up', '## 2 · next')
MAX_NEXT_LINES = 8
MAX_COMMITS = 6
MAX_JOURNAL_LINES = 6
# Non-doc commits a state doc may lag by before it is called stale. Two is about
# one session's work; warning on one would cry wolf and get tuned out.
DRIFT_COMMITS = 2


def repo_root(start):
    """Nearest ancestor containing .git, else the starting directory."""
    cur = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(cur, '.git')):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start)
        cur = parent


def find(root, canonical, aliases):
    for d in SEARCH_DIRS:
        for name in (canonical,) + tuple(aliases):
            p = os.path.join(root, d, name)
            if os.path.isfile(p):
                return os.path.relpath(p, root)
    return None


def read_text(path):
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            return fh.read()
    except Exception:
        return None


def section(path, headings, limit):
    """One `## `-delimited section of a markdown file, trimmed.

    Returns [] when the file or the heading is absent, so a caller can treat
    "no such section" and "section is empty" the same way — both mean there is
    nothing worth injecting.
    """
    raw = read_text(path)
    if not raw:
        return []
    lines = raw.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.strip().lower() in headings:
            start = i + 1
            break
    if start is None:
        return []
    out = []
    for ln in lines[start:]:
        if ln.startswith('## '):
            break
        if ln.strip():
            out.append(ln.rstrip())
        if len(out) >= limit:
            out.append('    … truncated, read the file for the rest')
            break
    return out


def journal_head(path):
    """The newest dated entry's date plus its `### ` subheadings.

    The journal is newest-first by convention, so the first `## ` heading past
    the front matter is the latest day. Only the subheadings are taken: they are
    written as `### HH:MM · TYPE · summary`, which is already the one-line form
    of what changed and why.
    """
    raw = read_text(path)
    if not raw:
        return []
    out = []
    for ln in raw.splitlines():
        if ln.startswith('## ') and not out:
            out.append(ln[3:].strip())
        elif ln.startswith('## ') and out:
            break
        elif ln.startswith('### ') and out:
            out.append('  ' + ln[4:].strip())
            if len(out) > MAX_JOURNAL_LINES:
                break
    return out if len(out) > 1 else []


def recent_commits(root, limit):
    """The last commits, one line each. [] outside a repo or on any git failure."""
    try:
        done = subprocess.run(
            ['git', '-C', root, 'log', '--format=%h %ad %s', '--date=short', '-n', str(limit)],
            capture_output=True, text=True, timeout=5)
    except Exception:
        return []
    if done.returncode != 0:
        return []
    return ['  ' + ln for ln in done.stdout.splitlines() if ln.strip()]


def drift_note(root, state_rel):
    """Has the code moved since the state doc was last verified?

    Surfaced here rather than left to a driver nobody runs, for the same reason
    the improve auditor is: the moment a session opens is the moment a stale doc
    does its damage, because everything after that is reasoned from it.

    Counts commits after `last-verified` that touch something other than markdown.
    A doc-only commit is not evidence the doc is right, so it does not count — and
    the only way to clear this is to re-verify and bump the date. Cheap by design:
    two git calls plus one per candidate commit, all with timeouts, silent on any
    failure. Full detail: scripts/state-health.py --drift.
    """
    raw = read_text(os.path.join(root, state_rel)) or ''
    m = re.search(r'^last-verified:\s*(\d{4}-\d{2}-\d{2})\s*$', raw, re.MULTILINE)
    if not m:
        return []
    since = m.group(1)

    def git(*args):
        try:
            done = subprocess.run(['git', '-C', root] + list(args),
                                  capture_output=True, text=True, timeout=5)
        except Exception:
            return ''
        return done.stdout if done.returncode == 0 else ''

    moved = []
    for line in git('log', '--since=%s' % since, '--format=%H %ad %s',
                    '--date=short').splitlines():
        parts = line.split(' ', 2)
        if len(parts) < 3 or parts[1] <= since:
            continue
        files = git('show', '--name-only', '--format=', parts[0]).split()
        if any(not f.endswith('.md') for f in files):
            moved.append(parts[2])
        if len(moved) > DRIFT_COMMITS:
            break

    if len(moved) <= DRIFT_COMMITS:
        return []
    return ['%s may be STALE — %d+ non-doc commits since it was verified (%s).'
            % (state_rel, len(moved), since),
            '  newest: %s' % moved[0][:70],
            '  Reconcile it against what actually shipped, then bump last-verified.',
            '  Detail: scripts/state-health.py --drift']


def improve_state():
    """What the Stop-hook auditor last measured about the governance files.

    Surfaced here because the auditor runs unattended and its findings are
    otherwise invisible until someone opens a JSON file, which nobody does.
    Only the actionable parts: whether the loop is due, and what crossed a
    refactor or duplication threshold.
    """
    raw = read_text(os.path.join(os.path.expanduser('~'), '.claude', 'improve', 'state.json'))
    if not raw:
        return []
    try:
        st = json.loads(raw)
    except Exception:
        return []
    c = st.get('counts') or {}
    flagged = sum(c.get(k, 0) for k in ('refactor', 'duplication', 'stale'))
    if not st.get('due') and not flagged:
        return []

    out = ['Self-improvement loop:']
    if st.get('due'):
        d = st.get('days_since_run')
        out.append('  DUE — %s (every %s days). Run /self-improve.'
                   % ('never run' if d is None else '%s days since the last run' % d,
                      st.get('frequency_days')))
    if flagged:
        out.append('  Context density: %d refactor · %d duplication · %d stale.'
                   % (c.get('refactor', 0), c.get('duplication', 0), c.get('stale', 0)))
        for r in (st.get('refactor') or [])[:3]:
            out.append('    refactor  %s (%s %s > %s)'
                       % (r.get('target'), r.get('kind'), r.get('measured'), r.get('limit')))
        for r in (st.get('duplication') or [])[:3]:
            out.append('    duplicate %s <-> %s (%.2f)'
                       % (r.get('a'), r.get('b'), r.get('similarity', 0)))
        out.append('  Full detail: ~/.claude/improve/state.json · history: improve/LEDGER.md')
    return out


def main():
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ''
    cwd = None
    if raw and raw.strip():
        try:
            cwd = (json.loads(raw) or {}).get('cwd')
        except Exception:
            cwd = None
    root = repo_root(str(cwd) if cwd else os.getcwd())

    found = []
    for canonical, what, aliases in CONTRACT:
        rel = find(root, canonical, aliases)
        if rel:
            found.append((rel, what))
    if not found:
        return

    name = os.path.basename(root.rstrip('/')) or root
    parts = ["Workspace state contract for '%s' — read these before acting, in this order:" % name]
    for rel, what in found:
        parts.append('  %-22s %s' % (rel, what))

    todo = next((rel for rel, _ in found if os.path.basename(rel).lower() in ('todo.md', 'roadmap.md', 'backlog.md')), None)
    if todo:
        p = os.path.join(root, todo)
        block = section(p, NOW_HEADINGS, MAX_NOW_LINES)
        if block:
            parts.append('')
            parts.append('Open now, from %s:' % todo)
            parts.extend(block)
        else:
            parts.append('')
            parts.append('%s has no populated "## Now" section — nothing is flagged as in flight.' % todo)
        nxt = section(p, NEXT_HEADINGS, MAX_NEXT_LINES)
        if nxt:
            parts.append('')
            parts.append('Next, agreed and unblocked, from %s:' % todo)
            parts.extend(nxt)

    journal = next((rel for rel, _ in found if os.path.basename(rel).lower() == 'journal.md'), None)
    if journal:
        head = journal_head(os.path.join(root, journal))
        if head:
            parts.append('')
            parts.append('Latest decisions and changes of direction, from %s — %s:' % (journal, head[0]))
            parts.extend(head[1:])

    commits = recent_commits(root, MAX_COMMITS)
    if commits:
        parts.append('')
        parts.append('Latest implementations, from git log:')
        parts.extend(commits)

    # Whether what you just read is still true. Deliberately last: it qualifies
    # everything above it, and a caveat printed first is a caveat skipped.
    state = next((rel for rel, _ in found
                  if os.path.basename(rel).lower() in ('state.md', 'context.md',
                                                       'workflow_state.md', 'knowledge.md')), None)
    if state:
        note = drift_note(root, state)
        if note:
            parts.append('')
            parts.append('⚠ DRIFT — reconcile before trusting the above:')
            parts.extend('  ' + ln for ln in note)

    parts.append('')
    parts.append('State these to the user in your first reply, then work from them rather than '
                 're-deriving context. When the session ends or direction changes, update TODO.md '
                 'and add a JOURNAL.md entry — that is what makes the next session cheap.')

    imp = improve_state()
    if imp:
        parts.append('')
        parts.extend(imp)

    sys.stdout.write(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'SessionStart',
            'additionalContext': '\n'.join(parts),
        }
    }, separators=(',', ':')))


if __name__ == '__main__':
    main()
