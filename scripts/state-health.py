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
  --drift    has the project moved on without the doc? The behaviour-2 check.
  --ids      does every identifier a doc cites actually have a register?
  --docs     is every document linked, and every artifact source resolvable?

  ./state-health.py                 all four, for the repo containing cwd
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
STATE_DIRS = ('docs', 'research', '.')
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
    """Has the project moved on without the state doc?

    Anchored on the commit that last touched the state doc, not on its
    `last-verified` date. Two reasons, both learned by running the date version
    against a docs-only project and watching it pass vacuously:

      A date is too coarse. `last-verified: today` versus `commit_date > today`
      is never true, so every commit made on the day of verification is
      invisible — precisely the day it matters.

      "Non-code commits don't count" assumes the deliverable is code. For a
      research or specification project every commit is markdown, so the filter
      excluded everything and printed "matches the code", which reads as
      verified when it means unmeasurable. Worse than no check.

    So: anchor = the state doc's own last commit. Drift = commits after it that
    touch anything except the churn files, which move constantly by design and
    do not invalidate a summary — the state doc itself, TODO and JOURNAL. Code,
    specs, research notes and schemas all count, whatever the project is made of.
    """
    for root in roots:
        label = os.path.basename(root)
        state = find(root, STATE_NAMES)
        if not state:
            continue

        anchor = git(root, 'log', '-1', '--format=%H', '--', state).strip()
        if not anchor:
            warn('%s: %s is not committed' % (label, state), 'drift cannot be anchored')
            continue

        churn = {state}
        for names in (TODO_NAMES, ('JOURNAL.md', 'journal.md')):
            rel = find(root, names)
            if rel:
                churn.add(rel)

        moved = []
        for sha in git(root, 'log', '%s..HEAD' % anchor, '--format=%H').split():
            files = git(root, 'show', '--name-only', '--format=', sha).split()
            if any(f not in churn for f in files):
                subject = git(root, 'log', '-1', '--format=%s', sha).strip()
                moved.append(subject)

        anchored = git(root, 'log', '-1', '--format=%ad', '--date=short', anchor).strip()
        if not moved:
            ok('%s: %s is current' % (label, state), 'last updated ' + anchored)
        elif len(moved) <= DRIFT_COMMITS:
            ok('%s: %s lags by %d commit(s)' % (label, state, len(moved)),
               'newest: ' + moved[0][:60])
        else:
            warn('%s: %s is DRIFTING' % (label, state),
                 '%d substantive commits since it was last updated (%s) — newest: %s'
                 % (len(moved), anchored, moved[0][:60]))

        # `last-verified` is the human assertion, so it is cross-checked rather
        # than trusted: older than the doc's own last commit means someone edited
        # the page without re-asserting that they had checked it.
        fm = front_matter(read(os.path.join(root, state)))
        lv = fm.get('last-verified', '')
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', lv):
            warn('%s: no usable last-verified' % label, repr(lv))
            continue
        if anchored and lv < anchored:
            warn('%s: %s edited without re-verifying' % (label, state),
                 'last-verified %s but last edited %s' % (lv, anchored))
        try:
            age = (date.today() - datetime.strptime(lv, '%Y-%m-%d').date()).days
            if age > 90:
                warn('%s: %s unverified for %d days' % (label, state, age))
        except Exception:
            pass


def identifiers(roots):
    """Every identifier family cited must have a register that defines it.

    The failure this exists for: `ariadne` cited `OQ-1` in STATE.md and in the
    `## Now` block injected into every session, while its question register used
    A-/B-/C- tiers and no `OQ-` scheme existed anywhere. A dangling id is the
    docs-only equivalent of a dangling file link, and it is invisible to a link
    checker because there is no link.

    An id counts as DEFINED where it opens a table cell or titles a heading —
    that is what a register row looks like. Real registers in the wild wrap the
    id in emphasis or a link, so all of these count and the pattern must allow
    the leading markup:

        | **A-1** | ...        | [DL-013](#dl-013) | ...
        | PB-1 | ...           ### DL-013

    Anywhere else it is a citation. A family with citations and no definition
    anywhere is dangling. Distinguishing definition from citation is what makes
    this usable: counting members instead flagged `PB-1`, a legitimately
    single-member family with a proper register row, and a stricter pattern
    flagged six families that were correctly registered in bold.
    """
    defined_pat = re.compile(r'^(?:\|\s*|#{1,6}\s+)[*_`\[]*([A-Z]{1,3})-([0-9]{1,3})\b',
                             re.MULTILINE)
    cited_pat = re.compile(r'\b([A-Z]{1,3})-([0-9]{1,3})\b')

    for root in roots:
        label = os.path.basename(root)
        state_rel0 = find(root, STATE_NAMES)
        docs_dir = os.path.join(root, os.path.dirname(state_rel0)) if state_rel0 else os.path.join(root, 'docs')
        if not os.path.isdir(docs_dir):
            continue

        defined, cited = set(), {}
        for name in sorted(os.listdir(docs_dir)):
            if not name.endswith('.md'):
                continue
            text = read(os.path.join(docs_dir, name))
            for pre, _num in defined_pat.findall(text):
                defined.add(pre)
            for pre, _num in cited_pat.findall(text):
                cited.setdefault(pre, set()).add(name)

        dangling = sorted(p for p in cited if p not in defined)
        for pre in dangling:
            warn('%s: identifier family %s- is cited but defined nowhere here' % (label, pre),
                 'in %s — a reader cannot resolve it' % ', '.join(sorted(cited[pre])))
        if cited and not dangling:
            ok('%s: %d identifier families all have registers' % (label, len(defined & set(cited))),
               ' '.join(sorted(defined & set(cited))[:8]))


def docs(roots):
    """Is every document owned, and every artifact accounted for?

    Two failures this exists for, both observed rather than imagined. A doc sat
    committed and linked from nowhere for a day — nobody reads what nobody links,
    so it silently stopped being maintained. And two artifacts spent an afternoon
    both claiming the same concern, because they differed in format and format
    reads like a distinction until you write both titles down.

    Neither was caught by reading. Both are caught by counting.
    """
    for root in roots:
        label = os.path.basename(root)
        state_rel = find(root, STATE_NAMES)
        docs_dir = os.path.join(root, os.path.dirname(state_rel)) if state_rel else os.path.join(root, 'docs')
        if not os.path.isdir(docs_dir) or not state_rel:
            continue
        state_text = read(os.path.join(root, state_rel))
        state_base = os.path.basename(state_rel)

        # 1 · every doc must be linked from the state page — the index of record
        linked = set(re.findall(r'\]\(([A-Za-z0-9._-]+\.md)\)', state_text))
        orphans = []
        for name in sorted(os.listdir(docs_dir)):
            if not name.endswith('.md') or name in (state_base, 'ARTIFACTS.md'):
                continue
            if name not in linked:
                orphans.append(name)
        if orphans:
            bad('%s: docs linked from nowhere' % label,
                '%s — a document nobody links is a document nobody maintains'
                % ', '.join(orphans[:6]))
        else:
            ok('%s: every doc is linked from %s' % (label, state_rel))

        # 2 · the artifact index must resolve: sources exist, supersessions名 a successor
        idx = os.path.join(docs_dir, 'ARTIFACTS.md')
        if not os.path.isfile(idx):
            continue
        rows = [ln for ln in read(idx).split('\n')
                if ln.startswith('| ') and ln.count('|') >= 5 and '---' not in ln]
        missing_src, unmarked = [], []
        for ln in rows:
            cells = [c.strip() for c in ln.strip('|').split('|')]
            if len(cells) < 5 or cells[0].lower().startswith('artifact'):
                continue
            name, published = cells[0][:40], cells[4].lower()
            for m in re.findall(r'\]\((\.\./[^)]+)\)', cells[3]):
                if not os.path.exists(os.path.normpath(os.path.join(docs_dir, m))):
                    missing_src.append('%s -> %s' % (name, m))
            if 'supersed' in cells[1].lower() and 'by' not in published:
                unmarked.append(name)
        if missing_src:
            bad('%s: artifact source missing' % label, '; '.join(missing_src[:3]))
        else:
            ok('%s: every artifact source path exists' % label)
        if unmarked:
            bad('%s: superseded without a successor' % label, '; '.join(unmarked[:3]))
        elif rows:
            ok('%s: supersessions all name a successor' % label)


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

    run_all = not (args & {'--sanity', '--smoke', '--drift', '--ids', '--docs'})
    if run_all or '--sanity' in args:
        sanity(roots)
    if run_all or '--smoke' in args:
        smoke()
    if run_all or '--drift' in args:
        drift(roots)
    if run_all or '--ids' in args:
        identifiers(roots)
    if run_all or '--docs' in args:
        docs(roots)

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
