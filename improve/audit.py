#!/usr/bin/env python3
"""audit.py — the deterministic half of the self-improvement loop.

Runs from the Stop hook on every session, with no agent involved. It measures
what can be measured and writes the findings down; it never edits a governance
file, because deciding *how* to split or merge a rule needs judgement.

  measure  ->  improve/state.json   (machine-readable, read by the SessionStart hook)
           ->  improve/LEDGER.md    (human-readable, appended only when something changed)

What it measures, and why each one is a real signal rather than a vanity metric:

  density     A governance file past ~500 lines, or a section past ~60, stopped being
              read in full. Splitting it is the fix; knowing it happened is the trigger.
  duplication Two rules saying the same thing in different files means one of them
              will be edited and the other will silently contradict it.
  staleness   A doc whose `last-verified` is older than its own re-verification window
              is asserting things nobody has checked.
  due         Days since the last recorded run, against config's frequencyDays.

Exit is always 0 and output is always silent: a Stop hook that prints noise trains
people to ignore hooks. Standard library only, so it runs under both python3 builds.
"""

import difflib
import json
import os
import re
import sys
from datetime import datetime, timezone

HOME = os.path.expanduser('~')
IMPROVE = os.path.join(HOME, '.claude', 'improve')
STATE = os.path.join(IMPROVE, 'state.json')
LEDGER = os.path.join(IMPROVE, 'LEDGER.md')
CONFIG = os.path.join(IMPROVE, 'config.json')

DEFAULTS = {
    'frequencyDays': 7,
    'thresholdOccurrences': 2,
    'maxSessionsToAnalyze': 10,
    'autoApply': False,
    # refactor thresholds — the point at which a file stopped being read in full
    'fileLineLimit': 500,
    'sectionLineLimit': 60,
    'memoryFileLimit': 80,
    'memoryCountLimit': 25,
    'similarityThreshold': 0.78,
    'staleDays': 90,
}

# governance surfaces worth watching, as (label, path) — missing paths are skipped
def targets():
    t = [
        ('global CLAUDE.md', os.path.join(HOME, '.claude', 'CLAUDE.md')),
        ('local CLAUDE.md', os.path.join(HOME, '.claude', 'CLAUDE.local.md')),
    ]
    mem = os.path.join(HOME, '.claude', 'projects')
    if os.path.isdir(mem):
        for proj in sorted(os.listdir(mem)):
            d = os.path.join(mem, proj, 'memory')
            if os.path.isdir(d):
                for f in sorted(os.listdir(d)):
                    if f.endswith('.md'):
                        t.append(('memory/%s' % f, os.path.join(d, f)))
    skills = os.path.join(HOME, 'repo', 'claudence', 'skills')
    if os.path.isdir(skills):
        for s in sorted(os.listdir(skills)):
            p = os.path.join(skills, s, 'SKILL.md')
            if os.path.isfile(p):
                t.append(('skill/%s' % s, p))
    return t


def read(path):
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            return fh.read()
    except Exception:
        return None


def load_config():
    cfg = dict(DEFAULTS)
    raw = read(CONFIG)
    if raw:
        try:
            cfg.update(json.loads(raw) or {})
        except Exception:
            pass
    return cfg


def sections(text):
    """[(heading, line_count)] for ## and ### headings."""
    out, cur, n = [], None, 0
    for ln in text.splitlines():
        if re.match(r'^#{2,3} ', ln):
            if cur is not None:
                out.append((cur, n))
            cur, n = ln.lstrip('# ').strip(), 0
        elif cur is not None:
            n += 1
    if cur is not None:
        out.append((cur, n))
    return out


def rules(text):
    """Normalised claim-bearing lines — bullets and table rows — for dedupe."""
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if not (s.startswith('- ') or s.startswith('* ') or s.startswith('| ')):
            continue
        s = re.sub(r'[*`_\[\]|]', ' ', s)
        s = re.sub(r'\s+', ' ', s).strip().lower()
        if len(s) >= 60:
            out.append(s)
    return out


def measure(cfg):
    refactor, dup, stale = [], [], []
    corpus = []

    for label, path in targets():
        text = read(path)
        if text is None:
            continue
        lines = text.count('\n') + 1

        if label.startswith('memory/'):
            if lines > cfg['memoryFileLimit']:
                refactor.append({'target': label, 'kind': 'memory-file-too-long',
                                 'measured': lines, 'limit': cfg['memoryFileLimit'],
                                 'action': 'split into one fact per file, or trim to the fact plus why'})
        elif lines > cfg['fileLineLimit']:
            refactor.append({'target': label, 'kind': 'file-too-long',
                             'measured': lines, 'limit': cfg['fileLineLimit'],
                             'action': 'extract the largest sections into references/ and leave a pointer'})

        for head, n in sections(text):
            if n > cfg['sectionLineLimit']:
                refactor.append({'target': '%s § %s' % (label, head), 'kind': 'section-too-long',
                                 'measured': n, 'limit': cfg['sectionLineLimit'],
                                 'action': 'move to its own reference file; keep a two-line summary'})

        m = re.search(r'^last-verified:\s*(\d{4}-\d{2}-\d{2})', text, re.MULTILINE)
        if m:
            try:
                age = (datetime.now(timezone.utc).date() - datetime.strptime(m.group(1), '%Y-%m-%d').date()).days
                if age > cfg['staleDays']:
                    stale.append({'target': label, 'last_verified': m.group(1), 'age_days': age})
            except Exception:
                pass

        for r in rules(text):
            corpus.append((label, r))

    n = len(corpus)
    seen = set()
    for i in range(n):
        for j in range(i + 1, n):
            a_lbl, a = corpus[i]
            b_lbl, b = corpus[j]
            if a_lbl == b_lbl:
                continue
            if abs(len(a) - len(b)) > max(len(a), len(b)) * 0.5:
                continue
            ratio = difflib.SequenceMatcher(None, a, b).ratio()
            if ratio >= cfg['similarityThreshold']:
                key = tuple(sorted([a[:70], b[:70]]))
                if key in seen:
                    continue
                seen.add(key)
                dup.append({'similarity': round(ratio, 3), 'a': a_lbl, 'b': b_lbl,
                            'text': a[:150],
                            'action': 'designate one canonical home and make the other a pointer'})

    memdirs = 0
    mem = os.path.join(HOME, '.claude', 'projects')
    if os.path.isdir(mem):
        for proj in os.listdir(mem):
            d = os.path.join(mem, proj, 'memory')
            if os.path.isdir(d):
                cnt = len([f for f in os.listdir(d) if f.endswith('.md') and f != 'MEMORY.md'])
                memdirs = max(memdirs, cnt)
                if cnt > cfg['memoryCountLimit']:
                    refactor.append({'target': 'memory/%s' % proj, 'kind': 'too-many-memories',
                                     'measured': cnt, 'limit': cfg['memoryCountLimit'],
                                     'action': 'merge overlapping facts; delete any that the repo now records'})

    return refactor, dup, stale, memdirs


def last_run():
    hist = os.path.join(IMPROVE, 'history.jsonl')
    raw = read(hist)
    if not raw:
        return None
    for ln in reversed(raw.strip().splitlines()):
        try:
            return json.loads(ln).get('timestamp')
        except Exception:
            continue
    return None


def main():
    if not os.path.isdir(IMPROVE):
        return
    cfg = load_config()
    refactor, dup, stale, memcount = measure(cfg)

    lr = last_run()
    days = None
    if lr:
        try:
            days = (datetime.now(timezone.utc) - datetime.fromisoformat(lr.replace('Z', '+00:00'))).days
        except Exception:
            days = None
    due = (days is None) or (days >= cfg['frequencyDays'])

    state = {
        'generated': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'last_run': lr,
        'days_since_run': days,
        'due': due,
        'frequency_days': cfg['frequencyDays'],
        'counts': {'refactor': len(refactor), 'duplication': len(dup),
                   'stale': len(stale), 'memories': memcount},
        'refactor': refactor[:25],
        'duplication': dup[:25],
        'stale': stale[:25],
    }

    prev = read(STATE)
    prev_counts = None
    if prev:
        try:
            prev_counts = json.loads(prev).get('counts')
        except Exception:
            pass

    try:
        with open(STATE, 'w', encoding='utf-8') as fh:
            json.dump(state, fh, indent=2)
            fh.write('\n')
    except Exception:
        return

    # Append to the ledger only when the picture changed — a ledger that grows on
    # every session is a log, and nobody reads a log.
    if prev_counts != state['counts']:
        stamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        line = ('- **%s** — refactor %d · duplication %d · stale %d · memories %d%s\n'
                % (stamp, len(refactor), len(dup), len(stale), memcount,
                   '  ⟵ loop is due' if due else ''))
        try:
            if not os.path.exists(LEDGER):
                with open(LEDGER, 'w', encoding='utf-8') as fh:
                    fh.write('# Self-improvement ledger\n\n'
                             'Appended by `improve/audit.py` when the measured picture changes, and by '
                             '`/self-improve` when it applies something. **Newest first within each '
                             'section.** This is the record of what the loop has done to your '
                             'governance files without you watching.\n\n## Measurements\n\n')
            with open(LEDGER, 'a', encoding='utf-8') as fh:
                fh.write(line)
        except Exception:
            pass


if __name__ == '__main__':
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
