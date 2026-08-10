#!/usr/bin/env python3
"""workspace-state.py — SessionStart hook.

Points a fresh agent at the workspace's state contract, so it does not have to
guess which of several overlapping records to read first.

The contract is four files, by convention, looked for in `docs/` then the repo
root. Legacy names are accepted so this works in repos that predate it:

  STATE.md     where the project is, one page          (context.md, workflow_state.md)
  TODO.md      Now / Next / Backlog                    (todo.md, ROADMAP.md, BACKLOG.md)
  JOURNAL.md   dated why-the-direction-changed         (CHANGELOG.md is NOT this)
  DECISIONS.md ADR-lite journal                        (ADR.md)

Beyond listing them, it inlines the `## Now` section of TODO.md — the immediate
work is the one thing worth injecting rather than pointing at, because an agent
that has to open a file to learn there is nothing urgent has already paid the
cost of opening it.

Silent when a workspace has none of these: no nagging, and no noise in repos
this convention does not apply to. Standard library only, so it runs identically
under the Homebrew and Xcode python3 builds.
"""

import json
import os
import sys

# canonical name -> (what it is, accepted aliases)
CONTRACT = (
    ('STATE.md', 'where the project is', ('context.md', 'workflow_state.md', 'KNOWLEDGE.md')),
    ('TODO.md', 'Now / Next / Backlog', ('todo.md', 'ROADMAP.md', 'BACKLOG.md')),
    ('JOURNAL.md', 'why the direction changed', ('journal.md',)),
    ('DECISIONS.md', 'decisions and assumptions', ('ADR.md', 'decisions.md')),
)
SEARCH_DIRS = ('docs', '.')
NOW_HEADINGS = ('## now', '## 1 · now', '## in flight')
MAX_NOW_LINES = 14


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


def now_block(path):
    """The `## Now` section, trimmed. Returns [] when absent or empty."""
    raw = read_text(path)
    if not raw:
        return []
    lines = raw.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.strip().lower() in NOW_HEADINGS:
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
        if len(out) >= MAX_NOW_LINES:
            out.append('    … truncated, read the file for the rest')
            break
    return out


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
        block = now_block(os.path.join(root, todo))
        if block:
            parts.append('')
            parts.append('Open now, from %s:' % todo)
            parts.extend(block)
        else:
            parts.append('')
            parts.append('%s has no populated "## Now" section — nothing is flagged as in flight.' % todo)

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
