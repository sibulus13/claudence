#!/usr/bin/env python3
"""state-health.py — is the workspace state contract actually working?

Two user behaviours depend on it, and both fail silently:

  1. Open a workspace -> the state visualisation and the catch-up context appear.
     Fails silently when a project's state doc is missing or under a filename the
     readers do not recognise. That is not hypothetical: this repo's own status
     page went 4.5 months stale that way, unseen by the reader shipped beside it.

  2. Functionality or a decision changes -> the state doc is updated to match.
     Fails silently by definition. Nothing errors when a doc drifts from the code;
     the doc just quietly becomes fiction, and it is trusted because it is written
     down.

Three modes, cheapest first, mirroring telemetry/loop-health.py:

  --sanity   is it wired up? File-level checks, no side effects, <1s.
  --smoke    does it work end to end? Drives the real hook + launcher in a
             throwaway repo and asserts a fresh session could catch up.
  --drift    has the code moved without the doc? The behaviour-2 check.

  ./state-health.py                 all three, for the repo containing cwd
  ./state-health.py --all           every git repo two levels under ~/repo
  ./state-health.py --sanity        exit 0 = healthy, 1 = a check failed

Exit code is the contract: non-zero means something needs a human. Drift is a
warning, not a failure — a doc can legitimately lag by a commit or two, and a
check that cries wolf gets ignored, which is worse than not having it.

Standard library only, so it runs identically under the Homebrew and Xcode
python3 builds.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import date, datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable or '/usr/bin/python3'
HOOK = os.path.join(REPO, 'scripts', 'workspace-state.py')
LAUNCHER = os.path.join(REPO, 'scripts', 'open-workspace.sh')

# The contract, and the same alias order the three readers use.
STATE_DIRS = ('docs', '.')
STATE_NAMES = ('STATE.md', 'context.md', 'workflow_state.md', 'KNOWLEDGE.md')
TODO_NAMES = ('TODO.md', 'todo.md', 'ROADMAP.md', 'BACKLOG.md')
FRONT_FIELDS = ('purpose', 'update-trigger', 'last-verified', 'status')
TODO_SECTIONS = ('## Now', '## Next', '## Backlog')

# A state doc lagging the code by more than this many non-doc commits is drifting
# rather than merely lagging. Two is one session's worth of work.
DRIFT_COMMITS = 2
SCAN_ROOT = os.path.expanduser('~/repo')

PASS, FAIL, WARN = [], [], []


def ok(name, detail=''):
    PASS.append(name + (' — ' + detail if detail else ''))


def bad(name, detail=''):
    FAIL.append(name + (' — ' + detail if detail else ''))


def warn(name, detail=''):
    WARN.append(name + (' — ' + detail if detail else ''))


def read(path):
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            return fh.read()
    except Exception:
        return ''


def git(root, *args):
    """Returns stdout, or '' on any failure. Never raises — a repo may be bare."""
    try:
        done = subprocess.run(['git', '-C', root] + list(args),
                              capture_output=True, text=True, timeout=15)
    except Exception:
        return ''
    return done.stdout if done.returncode == 0 else ''


def repo_root(start):
    cur = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(cur, '.git')):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def find(root, names):
    for d in STATE_DIRS:
        for name in names:
            p = os.path.join(root, d, name)
            if os.path.isfile(p):
                return os.path.relpath(p, root)
    return None


def front_matter(text):
    """The leading `---` block as a dict. {} when absent."""
    if not text.startswith('---'):
        return {}
    end = text.find('\n---', 3)
    if end < 0:
        return {}
    out = {}
    for line in text[3:end].splitlines():
        if ':' in line:
            k, v = line.split(':', 1)
            out[k.strip()] = v.strip()
    return out


def discover_repos():
    """Git repos two levels under ~/repo — the layout the repo convention enforces."""
    found = []
    if not os.path.isdir(SCAN_ROOT):
        return found
    for cat in sorted(os.listdir(SCAN_ROOT)):
        catdir = os.path.join(SCAN_ROOT, cat)
        if not os.path.isdir(catdir) or cat.startswith('.'):
            continue
        if os.path.exists(os.path.join(catdir, '.git')):
            found.append(catdir)
            continue
        for proj in sorted(os.listdir(catdir)):
            p = os.path.join(catdir, proj)
            if os.path.exists(os.path.join(p, '.git')):
                found.append(p)
    return found


# ── sanity ───────────────────────────────────────────────────────────────────

def sanity(roots):
    """Is the contract wired up, per repo? No side effects.

    A repo with no state doc is reported, not failed: adopting the contract is a
    choice. What fails is a repo that has one and got it wrong, because that is
    the case where the readers appear to work and quietly serve a broken page.
    """
    # The alias list is written in python, bash and lua — three runtimes with no
    # way to share a constant. Drift between them is silent, so assert it once.
    sources = {
        'scripts/workspace-state.py': r"'(STATE\.md|context\.md|workflow_state\.md|KNOWLEDGE\.md)'",
        'scripts/open-workspace.sh': r"\b(STATE\.md|context\.md|workflow_state\.md|KNOWLEDGE\.md)\b",
        'terminal.lua': r"'(STATE\.md|context\.md|workflow_state\.md|KNOWLEDGE\.md)'",
    }
    for rel, pattern in sources.items():
        found = set(re.findall(pattern, read(os.path.join(REPO, rel))))
        missing = set(STATE_NAMES) - found
        if missing:
            bad('aliases agree: %s' % rel, 'missing %s' % sorted(missing))
        else:
            ok('aliases agree: %s' % rel)

    if not os.access(LAUNCHER, os.X_OK) and not os.path.isfile(LAUNCHER):
        bad('launcher present', LAUNCHER)
    else:
        ok('launcher present')

    for root in roots:
        label = os.path.basename(root)
        state = find(root, STATE_NAMES)
        if not state:
            warn('%s: no state doc' % label, 'copy templates/STATE.md to docs/STATE.md')
            continue

        text = read(os.path.join(root, state))
        fm = front_matter(text)
        missing = [f for f in FRONT_FIELDS if f not in fm]
        if missing:
            bad('%s: %s front matter' % (label, state), 'missing %s' % missing)
        else:
            ok('%s: %s front matter' % (label, state), fm.get('last-verified', ''))

        # Behaviour 1 says "state visualisation". A state page with no diagram
        # is a status report, and the request was explicitly visual.
        if '```mermaid' in text:
            ok('%s: %s has a diagram' % (label, state),
               '%d block(s)' % text.count('```mermaid'))
        else:
            bad('%s: %s has no mermaid diagram' % (label, state))

        todo = find(root, TODO_NAMES)
        if not todo:
            bad('%s: no TODO.md' % label, 'the hook injects ## Now from it')
        else:
            ttext = read(os.path.join(root, todo))
            absent = [s for s in TODO_SECTIONS if s not in ttext]
            if absent:
                bad('%s: %s sections' % (label, todo), 'missing %s' % absent)
            else:
                ok('%s: %s sections' % (label, todo))

        # A backlink to a file that no longer exists is drift you can prove.
        broken = []
        for target in re.findall(r'\]\(([^)#:]+\.md)\)', text):
            resolved = os.path.normpath(os.path.join(os.path.dirname(os.path.join(root, state)), target))
            if not os.path.exists(resolved):
                broken.append(target)
        if broken:
            bad('%s: %s backlinks' % (label, state), 'dangling %s' % sorted(set(broken))[:5])
        else:
            ok('%s: %s backlinks resolve' % (label, state))


# ── smoke ────────────────────────────────────────────────────────────────────

def smoke():
    """End to end: could a fresh session actually catch up?

    Builds a throwaway repo, drives the REAL SessionStart hook and the REAL
    launcher discovery, and asserts every catch-up element a user asked for comes
    back. File-level checks cannot prove this — the hook could find the files and
    still inject nothing, which is exactly how it behaved before `## Next`, the
    journal head and the commit log were added.
    """
    box = tempfile.mkdtemp(prefix='state-health-')
    docs = os.path.join(box, 'docs')
    try:
        os.makedirs(docs, exist_ok=True)
        with open(os.path.join(docs, 'STATE.md'), 'w', encoding='utf-8') as fh:
            fh.write('---\npurpose: p\nupdate-trigger: t\nlast-verified: 2026-01-01\n'
                     'status: current\n---\n\n# S\n\n```mermaid\nflowchart TD\n  A --> B\n```\n')
        with open(os.path.join(docs, 'TODO.md'), 'w', encoding='utf-8') as fh:
            fh.write('# TODO\n\n## Now\n\n- SENTINEL_NOW\n\n## Next\n\n- SENTINEL_NEXT\n\n'
                     '## Backlog\n\n- SENTINEL_BACKLOG\n')
        with open(os.path.join(docs, 'JOURNAL.md'), 'w', encoding='utf-8') as fh:
            fh.write('# Journal\n\n## 2026-08-10\n\n### 12:00 · `PIVOT` · SENTINEL_JOURNAL\n\n'
                     '## 2026-08-09\n\n### 09:00 · `OLD` · SENTINEL_OLDER\n')

        for cmd in (['init', '-q', '.'], ['add', '.'],
                    ['-c', 'user.email=t@t', '-c', 'user.name=t',
                     'commit', '-qm', 'feat: SENTINEL_COMMIT']):
            if subprocess.run(['git', '-C', box] + cmd,
                              capture_output=True, timeout=30).returncode != 0:
                bad('smoke: git fixture', ' '.join(cmd))
                return

        # Behaviour 1, first half: the hook injects the catch-up context.
        proc = subprocess.run([PY, HOOK], input=json.dumps({'cwd': box}),
                              capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            bad('smoke: hook exited %d' % proc.returncode, proc.stderr.strip()[:200])
            return
        try:
            ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        except Exception as exc:
            bad('smoke: hook payload', '%s: %s' % (type(exc).__name__, exc))
            return

        # Input vs expected output — the whole point of a smoke test.
        for label, needle in (('in-flight work', 'SENTINEL_NOW'),
                              ('next steps', 'SENTINEL_NEXT'),
                              ('latest decision', 'SENTINEL_JOURNAL'),
                              ('latest implementation', 'SENTINEL_COMMIT'),
                              ('the state doc path', 'docs/STATE.md')):
            (ok if needle in ctx else bad)('smoke: injects %s' % label, needle)

        for label, needle in (('deferred backlog', 'SENTINEL_BACKLOG'),
                              ('superseded journal entry', 'SENTINEL_OLDER')):
            (ok if needle not in ctx else bad)('smoke: omits %s' % label, needle)

        # Behaviour 1, second half: the launcher opens the same file the hook named.
        proc = subprocess.run(['bash', LAUNCHER, '--state-doc', box],
                              capture_output=True, text=True, timeout=30)
        resolved = proc.stdout.strip()
        if resolved == 'docs/STATE.md':
            ok('smoke: launcher resolves the state doc', resolved)
        else:
            bad('smoke: launcher resolves the state doc', 'got %r' % resolved)

        # A repo with nothing must stay silent, or the harness nags everywhere.
        empty = tempfile.mkdtemp(prefix='state-health-empty-')
        try:
            proc = subprocess.run([PY, HOOK], input=json.dumps({'cwd': empty}),
                                  capture_output=True, text=True, timeout=30)
            if proc.stdout.strip() == '' and proc.returncode == 0:
                ok('smoke: silent without a contract')
            else:
                bad('smoke: silent without a contract', proc.stdout.strip()[:120])
        finally:
            subprocess.call(['rm', '-rf', empty])
    except Exception as exc:  # a smoke test that crashes is a failed smoke test
        bad('smoke: crashed', '%s: %s' % (type(exc).__name__, exc))
    finally:
        subprocess.call(['rm', '-rf', box])


# ── drift ────────────────────────────────────────────────────────────────────

def drift(roots):
    """Has the code moved without the doc?

    The mechanical signal is commits landing after `last-verified` that touch
    something other than the docs themselves. Calendar staleness ("90 days old")
    answers a different and weaker question: a doc verified yesterday can already
    be fiction if eight commits landed this morning, and a doc untouched for a
    year is fine if the code was too.

    Doc-only commits are excluded deliberately — editing STATE.md is not evidence
    that STATE.md is wrong.
    """
    for root in roots:
        label = os.path.basename(root)
        state = find(root, STATE_NAMES)
        if not state:
            continue
        fm = front_matter(read(os.path.join(root, state)))
        lv = fm.get('last-verified', '')
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', lv):
            warn('%s: no usable last-verified' % label, repr(lv) + ' — drift cannot be measured')
            continue

        # Commits strictly after the verification date, excluding doc-only ones.
        raw = git(root, 'log', '--since=%s' % lv, '--format=%H %ad %s', '--date=short')
        moved = []
        for line in raw.splitlines():
            parts = line.split(' ', 2)
            if len(parts) < 3 or parts[1] <= lv:
                continue
            files = git(root, 'show', '--name-only', '--format=', parts[0]).split()
            if any(not f.startswith('docs/') and not f.endswith('.md') for f in files):
                moved.append((parts[1], parts[2]))

        if not moved:
            ok('%s: %s matches the code' % (label, state), 'verified ' + lv)
        elif len(moved) <= DRIFT_COMMITS:
            ok('%s: %s lags by %d commit(s)' % (label, state, len(moved)),
               'newest: ' + moved[0][1][:60])
        else:
            warn('%s: %s is DRIFTING' % (label, state),
                 '%d non-doc commits since %s — newest: %s'
                 % (len(moved), lv, moved[0][1][:60]))

        # An overdue re-verification is a weaker signal, but free to compute.
        try:
            age = (date.today() - datetime.strptime(lv, '%Y-%m-%d').date()).days
            if age > 90:
                warn('%s: %s unverified for %d days' % (label, state, age))
        except Exception:
            pass


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    args = set(sys.argv[1:])
    if args & {'-h', '--help'}:
        sys.stdout.write(__doc__)
        return 0

    if '--all' in args:
        roots = discover_repos()
        if not roots:
            sys.stdout.write('no git repos found under %s\n' % SCAN_ROOT)
            return 1
    else:
        root = repo_root(os.getcwd())
        if not root:
            sys.stdout.write('not inside a git repo — use --all\n')
            return 1
        roots = [root]

    run_all = not (args & {'--sanity', '--smoke', '--drift'})
    if run_all or '--sanity' in args:
        sanity(roots)
    if run_all or '--smoke' in args:
        smoke()
    if run_all or '--drift' in args:
        drift(roots)

    for line in PASS:
        sys.stdout.write('  ok   %s\n' % line)
    for line in WARN:
        sys.stdout.write('  WARN %s\n' % line)
    for line in FAIL:
        sys.stdout.write('  FAIL %s\n' % line)
    sys.stdout.write('\n%d ok, %d warn, %d fail — %d repo(s)\n'
                     % (len(PASS), len(WARN), len(FAIL), len(roots)))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
