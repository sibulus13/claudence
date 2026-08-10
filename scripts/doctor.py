#!/usr/bin/env python3
"""doctor.py — is this claudence install actually working, on THIS machine?

Claudence was built on one Windows desktop and ported to one Mac. Everything in
it therefore assumes a single tenant: absolute paths, one keychain identity, one
set of symlinks, one PATH. None of that is checked anywhere, so a fresh or
drifted install fails quietly and the first symptom is a hook that never fires.

This is the preflight. It answers one question per check — "is this aspect
unblocked?" — and every failure carries the command that fixes it.

  ./scripts/doctor.py            everything
  ./scripts/doctor.py --quick    skip the checks that spawn processes
  ./scripts/doctor.py --fix      apply the safe, idempotent repairs (symlinks)

Exit 0 = ready. Exit 1 = something needs attention. Exit 2 = broken install.

Deliberately stdlib-only and side-effect-free unless --fix is passed, so it is
safe to run on a machine you have not set up yet.
"""

import json
import os
import subprocess
import sys

HOME = os.path.expanduser('~')
CLAUDE = os.path.join(HOME, '.claude')
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable or '/usr/bin/python3'

OK, WARN, FAIL = 'ok', 'WARN', 'FAIL'
RESULTS = []

# Everything under ~/.claude that must resolve back into the repo checkout.
# This is the single-tenant assumption made explicit: the repo is the source of
# truth and ~/.claude is a view onto it.
# settings.json is deliberately NOT here: Claude Code rewrites it when settings
# change, so a symlink would have the app editing the checkout. setup.sh copies
# settings.macos.json into place instead, which means it can drift both ways —
# see check_settings_drift, which is the more useful check.
LINKS = ['CLAUDE.md', 'attention.lua', 'docs', 'hooks', 'improve', 'keymap.txt',
         'scripts', 'skills', 'statusline.py', 'telemetry']


def record(section, name, status, detail='', remedy=''):
    RESULTS.append((section, name, status, detail, remedy))


def _run(args, stdin='', timeout=30):
    try:
        p = subprocess.run(args, input=stdin, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except Exception as exc:
        return 127, '', '%s: %s' % (type(exc).__name__, exc)


# ── 1 · environment ──────────────────────────────────────────────────────────

def check_environment():
    s = 'environment'
    for name, path in (('python3', '/opt/homebrew/bin/python3'),
                       ('system python3', '/usr/bin/python3')):
        if os.path.exists(path):
            record(s, name, OK, path)
        else:
            record(s, name, WARN if 'system' not in name else FAIL, path + ' missing')

    # Hooks do NOT source a profile. They see only settings.json env.PATH, which
    # is why a hook that shells out to node breaks even though your shell has it.
    settings = _settings()
    pinned = ((settings.get('env') or {}).get('PATH') or '')
    if not pinned:
        record(s, 'settings PATH pinned', FAIL, 'hooks will inherit a bare PATH',
               'add env.PATH to settings.json — Homebrew first')
    else:
        missing = [d for d in pinned.split(':') if d and not os.path.isdir(d)]
        if missing:
            record(s, 'settings PATH pinned', WARN, 'entries do not exist: ' + ', '.join(missing[:3]))
        else:
            record(s, 'settings PATH pinned', OK, '%d entries, all present' % len(pinned.split(':')))


def _settings():
    p = os.path.join(CLAUDE, 'settings.json')
    try:
        return json.load(open(p))
    except Exception:
        return {}


# ── 2 · symlinks — the single-tenant assumption ──────────────────────────────

def check_links(fix=False):
    s = 'links'
    for name in LINKS:
        live = os.path.join(CLAUDE, name)
        target = os.path.join(REPO, name)
        if not os.path.exists(target):
            record(s, name, WARN, 'not in the checkout — skipped')
            continue
        if os.path.islink(live) and os.path.realpath(live) == os.path.realpath(target):
            record(s, name, OK)
        elif os.path.exists(live) and not os.path.islink(live):
            # A real file shadowing the repo copy is the worst case: edits to the
            # repo silently do nothing, which is exactly the "is my context the
            # latest version?" failure this script exists to catch.
            record(s, name, FAIL, 'is a real file, NOT a link — repo edits do nothing',
                   'mv %s %s.bak && ln -s %s %s' % (live, live, target, live))
        else:
            if fix:
                try:
                    if os.path.lexists(live):
                        os.remove(live)
                    os.symlink(target, live)
                    record(s, name, OK, 'linked by --fix')
                    continue
                except OSError as exc:
                    record(s, name, FAIL, str(exc))
                    continue
            record(s, name, FAIL, 'missing', 'ln -s %s %s' % (target, live))


# ── 3 · hooks ────────────────────────────────────────────────────────────────

def check_hooks():
    s = 'hooks'
    settings = _settings()
    hooks = settings.get('hooks') or {}
    if not hooks:
        record(s, 'configured', FAIL, 'no hooks in settings.json')
        return
    seen = 0
    for event, groups in hooks.items():
        for g in groups:
            for h in g.get('hooks', []):
                cmd = h.get('command', '')
                seen += 1
                # Extract the script path from: python3 "$HOME/.claude/x/y.py" --flag
                script = None
                for tok in cmd.replace('"', ' ').split():
                    if tok.endswith('.py') or tok.endswith('.sh'):
                        script = tok.replace('$HOME', HOME)
                        break
                if not script:
                    record(s, '%s' % event, WARN, 'no script path found in: %s' % cmd[:50])
                elif not os.path.exists(script):
                    record(s, '%s → %s' % (event, os.path.basename(script)), FAIL,
                           'script does not exist', 'check the symlinks section')
                else:
                    record(s, '%s → %s' % (event, os.path.basename(script)), OK)
    record(s, 'total wired', OK, '%d hook commands' % seen)

    for key, label in (('statusLine', 'status line'),):
        cmd = (settings.get(key) or {}).get('command', '')
        path = None
        for tok in cmd.replace('"', ' ').split():
            if tok.endswith('.py'):
                path = tok.replace('$HOME', HOME)
        if path and os.path.exists(path):
            record(s, label, OK)
        else:
            record(s, label, FAIL, 'not configured or missing')


# ── 4 · runtime — do they actually execute? ──────────────────────────────────

def check_runtime():
    """A wired hook that crashes is worse than an absent one: it fails silently."""
    s = 'runtime'
    sid = 'doctor00-0000-0000-0000-000000000000'
    code, out, err = _run([PY, os.path.join(REPO, 'statusline.py')],
                          stdin=json.dumps({'session_id': sid,
                                            'cost': {'total_cost_usd': 1.0},
                                            'context_window': {'used_percentage': 10}}))
    if code != 0:
        record(s, 'statusline executes', FAIL, err.strip()[:90])
    elif not out.strip():
        record(s, 'statusline executes', WARN, 'ran but produced no output')
    else:
        record(s, 'statusline executes', OK, '%d chars' % len(out))

    health = os.path.join(REPO, 'telemetry', 'loop-health.py')
    if not os.path.exists(health):
        record(s, 'loop health', WARN, 'loop-health.py not present')
    else:
        code, out, _ = _run([PY, health, '--sanity'])
        line = [l for l in out.splitlines() if 'ok,' in l]
        record(s, 'loop health --sanity', OK if code == 0 else FAIL,
               line[-1].strip() if line else 'exit %d' % code,
               '' if code == 0 else 'run telemetry/loop-health.py for detail')


# ── 5 · scheduled work ───────────────────────────────────────────────────────

def check_schedule():
    s = 'schedule'
    code, out, _ = _run(['launchctl', 'list'])
    if code != 0:
        record(s, 'launchctl', WARN, 'not available')
        return
    if 'com.claudence.loop-health' in out:
        record(s, 'loop-health job', OK, 'loaded')
    else:
        record(s, 'loop-health job', WARN, 'not loaded',
               'sed "s|__HOME__|$HOME|g" scripts/com.claudence.loop-health.plist.template '
               '> ~/Library/LaunchAgents/com.claudence.loop-health.plist && launchctl load '
               '~/Library/LaunchAgents/com.claudence.loop-health.plist')


# ── 6 · context freshness — "is what I am reading current?" ──────────────────

def check_settings_drift():
    """settings.json is a COPY, so it drifts in both directions — and each
    direction is a different problem.

    Repo ahead of live  → this machine never got a change; re-run setup.sh.
    Live ahead of repo  → this machine is the only place the change exists, so a
                          second machine would not reproduce it. That is the
                          single-tenant assumption biting, and it is the one
                          nobody notices until they set up a second machine.
    """
    s = 'settings'
    live = _settings()
    canon_path = os.path.join(REPO, 'settings.macos.json')
    if not live:
        record(s, 'settings.json', FAIL, 'missing or unparseable')
        return
    if not os.path.exists(canon_path):
        record(s, 'settings.macos.json', WARN, 'no canonical copy in the repo')
        return
    try:
        canon = json.load(open(canon_path))
    except Exception as exc:
        record(s, 'settings.macos.json', FAIL, 'unparseable: %s' % exc)
        return

    def hook_cmds(d):
        out = set()
        for _ev, groups in (d.get('hooks') or {}).items():
            for g in groups:
                for h in g.get('hooks', []):
                    out.add(h.get('command', ''))
        return out

    missing_live = hook_cmds(canon) - hook_cmds(live)
    record(s, 'hooks: repo → live', OK if not missing_live else FAIL,
           'in sync' if not missing_live else '%d repo hook(s) not installed' % len(missing_live),
           '' if not missing_live else './setup.sh  (this machine is running stale hooks)')

    live_plugins = set((live.get('enabledPlugins') or {}).keys())
    canon_plugins = set((canon.get('enabledPlugins') or {}).keys())
    only_live = live_plugins - canon_plugins
    record(s, 'plugins: live → repo', OK if not only_live else WARN,
           'in sync' if not only_live else 'only on this machine: ' + ', '.join(sorted(only_live)),
           '' if not only_live else 'fold them into settings.macos.json so a second machine gets them')

    live_env = set((live.get('env') or {}).keys())
    only_env = live_env - set((canon.get('env') or {}).keys())
    if only_env:
        record(s, 'env: live → repo', WARN, 'only on this machine: ' + ', '.join(sorted(only_env)),
               'PATH is machine-specific by nature; confirm setup.sh generates it')
    else:
        record(s, 'env: live → repo', OK, 'in sync')


def check_context():
    """The question that prompted this script: can I trust the loaded context?"""
    s = 'context'
    for name in ('CLAUDE.md', 'CLAUDE.local.md'):
        p = os.path.join(CLAUDE, name)
        if os.path.exists(p):
            record(s, name, OK, '%d KB' % (os.path.getsize(p) // 1024))
        else:
            record(s, name, WARN if 'local' in name else FAIL, 'missing')

    skills = os.path.join(CLAUDE, 'skills')
    if os.path.isdir(skills):
        bad = []
        for d in sorted(os.listdir(skills)):
            sk = os.path.join(skills, d, 'SKILL.md')
            if not os.path.isdir(os.path.join(skills, d)):
                continue
            if not os.path.exists(sk):
                bad.append(d + ' (no SKILL.md)')
                continue
            head = open(sk, encoding='utf-8').read(400)
            if 'name:' not in head or 'description:' not in head:
                bad.append(d + ' (frontmatter)')
        n = len([d for d in os.listdir(skills) if os.path.isdir(os.path.join(skills, d))])
        if bad:
            record(s, 'skills', FAIL, '%d of %d malformed: %s' % (len(bad), n, ', '.join(bad[:3])))
        else:
            record(s, 'skills', OK, '%d, all with frontmatter' % n)

    # Uncommitted or unpushed work means the checkout is NOT the shared truth.
    code, out, _ = _run(['git', '-C', REPO, 'status', '--porcelain'])
    dirty = len([l for l in out.splitlines() if l.strip()])
    record(s, 'working tree', OK if not dirty else WARN,
           'clean' if not dirty else '%d uncommitted path(s)' % dirty)

    code, out, _ = _run(['git', '-C', REPO, 'rev-parse', '--abbrev-ref', 'HEAD'])
    branch = out.strip() or '?'
    code, out, _ = _run(['git', '-C', REPO, 'log', '--oneline', 'origin/%s..%s' % (branch, branch)])
    if code != 0:
        record(s, 'unpushed commits', WARN, 'no upstream for %s' % branch,
               'git push -u origin %s' % branch)
    else:
        n = len([l for l in out.splitlines() if l.strip()])
        record(s, 'unpushed commits', OK if n == 0 else WARN, '%d on %s' % (n, branch),
               '' if n == 0 else 'git push origin %s' % branch)

    # Single-tenant tell: one keychain identity for github.com. If the remote
    # belongs to a different account, every push 403s and the message does not
    # say why.
    code, out, _ = _run(['git', '-C', REPO, 'remote', 'get-url', 'origin'])
    remote = out.strip()
    if remote and 'github.com' in remote:
        owner = remote.split('github.com')[-1].lstrip(':/').split('/')[0]
        code2, out2, _ = _run(['security', 'find-internet-password', '-s', 'github.com'])
        acct = ''
        for line in out2.splitlines():
            if '"acct"' in line and '=' in line:
                acct = line.split('=')[-1].strip().strip('"')
        if acct and owner and acct.lower() != owner.lower():
            record(s, 'git identity', WARN,
                   'keychain=%s but remote owner=%s — pushes will 403' % (acct, owner),
                   'add %s as a collaborator, or prefix the remote host with "%s@" '
                   '(git remote set-url) so a separate keychain entry is used. '
                   'See docs/SETUP.md' % (acct, owner))
        else:
            record(s, 'git identity', OK, acct or 'no keychain entry found')


def main():
    args = set(sys.argv[1:])
    fix = '--fix' in args
    quick = '--quick' in args

    check_environment()
    check_links(fix=fix)
    check_hooks()
    if not quick:
        check_runtime()
    check_schedule()
    check_settings_drift()
    check_context()

    width = max(len(n) for _, n, _, _, _ in RESULTS) + 2
    section = None
    for sec, name, status, detail, remedy in RESULTS:
        if sec != section:
            print('\n%s' % sec.upper())
            section = sec
        mark = {'ok': '  ok  ', 'WARN': '  WARN', 'FAIL': '  FAIL'}[status]
        print('%s %-*s %s' % (mark, width, name, detail))
        if remedy and status != OK:
            print('       %s→ %s' % (' ' * width, remedy))

    fails = [r for r in RESULTS if r[2] == FAIL]
    warns = [r for r in RESULTS if r[2] == WARN]
    print('\n%d ok, %d warn, %d fail' % (len(RESULTS) - len(fails) - len(warns), len(warns), len(fails)))
    if fails:
        print('\nNot ready. Fix the FAIL lines above; --fix repairs symlinks automatically.')
        return 2 if any(r[0] == 'links' for r in fails) else 1
    if warns:
        return 1
    print('Ready.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
