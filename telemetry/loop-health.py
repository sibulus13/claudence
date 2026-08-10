#!/usr/bin/env python3
"""loop-health.py — is the self-improvement loop actually working?

The loop reads telemetry and writes improvements. Both halves fail silently: a
hook stops populating a field and the ledger fills with nulls, or the loop never
runs and nothing says so. Both happened — cost_usd and ctx_pct were null on all
125 ledger rows for six days, and improve/history.jsonl has never been written.

Three modes, cheapest first:

  --sanity   is it wired up? File-level checks, no side effects, <1s.
  --smoke    does it work end to end? Drives the real hooks in a throwaway HOME.
  --health   what has it done, and what changed since the last check?

  ./loop-health.py            all three
  ./loop-health.py --sanity   exit 0 = healthy, 1 = a check failed

Exit code is the contract: non-zero means something needs a human. Cron mails
the output on failure and stays quiet otherwise.
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib'))
import hooklib as H  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable or '/usr/bin/python3'

IMPROVE_DIR = os.path.join(H.CLAUDE_DIR, 'improve')
HISTORY = os.path.join(IMPROVE_DIR, 'history.jsonl')
LEDGER = os.path.join(H.TELEMETRY_DIR, 'cost-ledger.jsonl')
WATERMARK = os.path.join(IMPROVE_DIR, 'last-health-check.json')
# When the ledger became trustworthy. Rows before it predate the status-line
# fallback and are legitimately null; see the canary in sanity().
BASELINE = os.path.join(IMPROVE_DIR, 'ledger-baseline.json')

# A ledger row older than this predates the meta-file fallback and is expected
# to carry nulls; only recent rows are evidence of a live regression.
RECENT_ROWS = 20
# Populated-field floor across recent rows. Not 100%: a session that stops before
# the status line ever renders legitimately has no cost reading.
POPULATED_FLOOR = 0.6
STALE_DAYS = 14

PASS, FAIL, WARN = [], [], []


def ok(name, detail=''):
    PASS.append(name + (' — ' + detail if detail else ''))


def bad(name, detail=''):
    FAIL.append(name + (' — ' + detail if detail else ''))


def warn(name, detail=''):
    WARN.append(name + (' — ' + detail if detail else ''))


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, 'r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


# ── sanity ───────────────────────────────────────────────────────────────────

def sanity():
    """File-level: are the loop's inputs present and populated?"""
    if not os.path.isdir(H.TELEMETRY_DIR):
        bad('telemetry dir', H.TELEMETRY_DIR + ' missing')
        return
    ok('telemetry dir')

    ledger = read_jsonl(LEDGER)
    if not ledger:
        bad('cost ledger', 'no rows — the Stop hook is not writing')
        return
    ok('cost ledger', '%d rows' % len(ledger))

    # THE canary. This is the exact regression that made the loop unfalsifiable:
    # the Stop payload carries neither field, so without the status-line fallback
    # every row records null and no amount of accumulated data is usable.
    #
    # Rows written before the fix landed are legitimately null, so scoring them
    # would fail this check for weeks and train everyone to ignore it. The
    # baseline records when the ledger became trustworthy; earlier rows are
    # exempt, later ones are not, and a future regression still trips it.
    baseline = H.parse_ts((H.read_json(BASELINE, {}) or {}).get('ts'))
    recent = [r for r in ledger[-RECENT_ROWS * 3:]
              if not baseline or (H.parse_ts(r.get('ts')) or baseline) >= baseline][-RECENT_ROWS:]
    if len(recent) < 5:
        warn('ledger population', '%d row(s) since baseline — too few to judge yet' % len(recent))
        return
    for field in ('cost_usd', 'ctx_pct'):
        filled = sum(1 for r in recent if r.get(field) is not None)
        rate = filled / float(len(recent))
        detail = '%d/%d rows since baseline populated' % (filled, len(recent))
        if rate < POPULATED_FLOOR:
            bad('ledger.%s' % field, detail + ' — check statusline.py writes meta-<id>.json')
        else:
            ok('ledger.%s' % field, detail)

    # Inputs the loop reads beyond the ledger.
    cfg = os.path.join(IMPROVE_DIR, 'config.json')
    if not os.path.exists(cfg):
        warn('improve/config.json', 'missing — loop will use defaults')
    else:
        try:
            json.load(open(cfg))
            ok('improve/config.json')
        except ValueError as exc:
            bad('improve/config.json', 'unparseable: %s' % exc)

    reports = os.path.join(H.TELEMETRY_DIR, 'reports')
    n = len([f for f in os.listdir(reports) if f.endswith('.json')]) if os.path.isdir(reports) else 0
    (ok if n else bad)('friction reports', '%d present' % n)

    # Error state: a running flag left behind means a session died mid-run, or
    # the Stop hook never fired. One is noise; several is a broken hook.
    stale = [f for f in os.listdir(H.TELEMETRY_DIR) if f.startswith('running-')]
    if len(stale) > 2:
        warn('stale running flags', '%d — Stop hook may not be firing' % len(stale))
    else:
        ok('running flags', '%d' % len(stale))


# ── smoke ────────────────────────────────────────────────────────────────────

def smoke():
    """End to end: drive the real hooks in a throwaway HOME and assert the output.

    Deliberately exercises the status-line -> Stop handoff, because that is the
    seam that broke and the seam no file-level check can prove.
    """
    sid = 'smoke0000-1111-2222-3333-444455556666'
    box = tempfile.mkdtemp(prefix='loop-health-')
    env = dict(os.environ, HOME=box)
    os.makedirs(os.path.join(box, '.claude', 'telemetry'), exist_ok=True)

    def run(script, payload):
        proc = subprocess.Popen([PY, os.path.join(REPO, script)],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=env)
        out, err = proc.communicate(json.dumps(payload).encode('utf-8'), timeout=30)
        return proc.returncode, out.decode('utf-8', 'replace'), err.decode('utf-8', 'replace')

    try:
        code, _, err = run('telemetry/log-prompt.py',
                           {'session_id': sid, 'prompt': 'smoke', 'cwd': '/tmp/x'})
        if code != 0:
            bad('smoke: log-prompt', err.strip()[:120])
            return

        # The status line is the ONLY process that receives cost and context.
        code, _, err = run('statusline.py',
                           {'session_id': sid, 'cost': {'total_cost_usd': 4.25},
                            'context_window': {'used_percentage': 63}})
        if code != 0:
            bad('smoke: statusline', err.strip()[:120])
            return

        code, _, err = run('telemetry/analyze-session.py', {'session_id': sid})
        if code != 0:
            bad('smoke: analyze-session', err.strip()[:120])
            return

        report_path = os.path.join(box, '.claude', 'telemetry', 'reports', '%s.json' % sid[:8])
        if not os.path.exists(report_path):
            bad('smoke: report written', 'no report at ' + report_path)
            return
        report = json.load(open(report_path))

        # Input vs expected output — the whole point of a smoke test.
        for field, expected in (('cost_usd', 4.25), ('ctx_pct', 63)):
            actual = report.get(field)
            if actual != expected:
                bad('smoke: %s round-trip' % field, 'expected %r, got %r' % (expected, actual))
            else:
                ok('smoke: %s round-trip' % field, repr(actual))

        rows = read_jsonl(os.path.join(box, '.claude', 'telemetry', 'cost-ledger.jsonl'))
        (ok if rows else bad)('smoke: ledger appended', '%d row(s)' % len(rows))
    except Exception as exc:  # a smoke test that crashes is a failed smoke test
        bad('smoke: crashed', '%s: %s' % (type(exc).__name__, exc))
    finally:
        subprocess.call(['rm', '-rf', box])


# ── health ───────────────────────────────────────────────────────────────────

def _since(rows, cutoff):
    out = []
    for r in rows:
        ts = H.parse_ts(r.get('ts') or r.get('timestamp'))
        if ts and cutoff and ts > cutoff:
            out.append(r)
    return out


def health():
    """What has the loop done, and what changed since the last check?"""
    mark = H.read_json(WATERMARK, {}) or {}
    last = H.parse_ts(mark.get('ts')) if mark.get('ts') else None
    now = datetime.now(timezone.utc)

    lines = []
    lines.append('Last health check : %s' % (mark.get('ts') or 'never'))

    history = read_jsonl(HISTORY)
    if not history:
        # Not a failure — the loop is specified but has never run. Saying so is
        # the whole value here, because nothing else reports it.
        warn('improve/history.jsonl', 'no runs recorded — the loop has never executed')
        lines.append('Loop runs         : 0 (never run)')
    else:
        newest = H.parse_ts(history[-1].get('timestamp') or history[-1].get('ts'))
        age = (now - newest).days if newest else None
        lines.append('Loop runs         : %d, newest %s' % (len(history), newest))
        if age is not None and age > STALE_DAYS:
            warn('loop freshness', 'last run %d days ago' % age)
        new = _since(history, last)
        lines.append('Applied since last: %d' % len(new))
        for r in new[-10:]:
            for a in (r.get('augmentations') or []):
                lines.append('  + [%s] %s' % (a.get('category', '?'), str(a.get('rule', ''))[:90]))

    ledger = read_jsonl(LEDGER)
    fresh = _since(ledger, last) if last else ledger
    lines.append('Sessions since    : %d' % len(fresh))
    if fresh:
        costed = [r['cost_usd'] for r in fresh if r.get('cost_usd') is not None]
        lines.append('Cost observed     : $%.2f across %d/%d scored sessions'
                     % (sum(costed), len(costed), len(fresh)))
        scores = [r.get('score') or 0 for r in fresh]
        lines.append('Mean friction     : %.2f' % (sum(scores) / float(len(scores))))

    H.write_json(WATERMARK, {'ts': H.now_iso()})
    return lines


def main():
    args = set(sys.argv[1:])
    run_all = not (args & {'--sanity', '--smoke', '--health'})

    if run_all or '--sanity' in args:
        sanity()
    if run_all or '--smoke' in args:
        smoke()

    detail = []
    if run_all or '--health' in args:
        detail = health()

    print('=== loop health @ %s ===' % H.now_iso())
    for line in detail:
        print(line)
    if detail:
        print('')
    for p in PASS:
        print('  ok   %s' % p)
    for w in WARN:
        print('  WARN %s' % w)
    for f in FAIL:
        print('  FAIL %s' % f)
    print('\n%d ok, %d warn, %d fail' % (len(PASS), len(WARN), len(FAIL)))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
