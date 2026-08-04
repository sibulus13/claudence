#!/usr/bin/env python3
"""startup-reminder.py — SessionStart hook (port of startup-reminder.ps1).

Surfaces the current repo's dev/startup command when a session opens, detected
generically so it works across projects. Precedence:
  1. .startup-cmd file (one line) — explicit per-repo override
  2. dev.sh / start.sh / restart.sh          (shell launchers)
  3. package.json scripts.dev | scripts.start (package manager from the lockfile)
  4. docker-compose.yml / compose.yaml
  5. Makefile with a dev | start | run target
Silent when the repo has no recognizable startup command — no nagging.

The PowerShell launchers the Windows original checked (dev.ps1, restart.ps1,
start.ps1, run.ps1) are dropped: they cannot run here.
"""

import json
import os
import re
import sys

SHELL_LAUNCHERS = ('dev.sh', 'start.sh', 'restart.sh')
MAKE_TARGETS = ('dev', 'start', 'run')


def read_text(path):
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            return fh.read()
    except Exception:
        return None


def package_manager(cwd):
    if os.path.exists(os.path.join(cwd, 'pnpm-lock.yaml')):
        return 'pnpm'
    if os.path.exists(os.path.join(cwd, 'yarn.lock')):
        return 'yarn'
    return 'npm run'


def detect(cwd):
    override = read_text(os.path.join(cwd, '.startup-cmd'))
    if override and override.strip():
        return override.strip().splitlines()[0].strip()

    for launcher in SHELL_LAUNCHERS:
        if os.path.exists(os.path.join(cwd, launcher)):
            return './' + launcher

    package_json = os.path.join(cwd, 'package.json')
    if os.path.exists(package_json):
        raw = read_text(package_json)
        try:
            scripts = (json.loads(raw) or {}).get('scripts') or {}
        except Exception:
            scripts = {}
        manager = package_manager(cwd)
        if scripts.get('dev'):
            return '%s dev' % manager
        if scripts.get('start'):
            return '%s start' % manager
        return None

    for compose in ('docker-compose.yml', 'compose.yaml'):
        if os.path.exists(os.path.join(cwd, compose)):
            return 'docker compose up'

    makefile = read_text(os.path.join(cwd, 'Makefile'))
    if makefile:
        for target in MAKE_TARGETS:
            if re.search(r'^%s\s*:' % re.escape(target), makefile, re.MULTILINE):
                return 'make %s' % target
    return None


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
    cwd = str(cwd) if cwd else os.getcwd()

    command = detect(cwd)
    if not command:
        return

    context = ("Startup command for '%s': run  %s  to launch this project's services "
               "(hot reload / dev). Surface this to the user near the start of your "
               "first reply." % (os.path.basename(cwd.rstrip('/')), command))
    sys.stdout.write(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'SessionStart',
            'additionalContext': context,
        }
    }, separators=(',', ':')))


if __name__ == '__main__':
    main()
