#!/usr/bin/env python3
"""Block a commit that would publish client-identifying content.

This repo is public. The names that must not reach it — clients, tenants,
private products — are themselves the sensitive part, so the denylist does NOT
live here. It lives at ~/.claude/claudence-denylist.txt, which is outside the
repo entirely and therefore cannot be committed by accident.

Usage:
    check-public-safe.py            scan staged changes (pre-commit hook)
    check-public-safe.py --all      scan every tracked file (audit)

Exit 1 blocks the commit. Override a deliberate mention with
`git commit --no-verify`, but prefer moving the content to CLAUDE.local.md.
"""
import os
import re
import subprocess
import sys

DENYLIST = os.path.expanduser('~/.claude/claudence-denylist.txt')

# Usernames that are obviously stand-ins, not a real account. Test fixtures and
# docs are full of these, and flagging them trains you to --no-verify past the
# guard — which is worse than not having one.
PLACEHOLDER_USERS = (r'(?:[a-z]|me|you|user|username|someone|somebody|example|test|dev|foo|bar|name)')

# Always-on patterns — these are unsafe in a public repo regardless of client.
BUILTIN = [
    (r'/Users/(?!%s/)[a-z0-9._-]+/' % PLACEHOLDER_USERS,
     'absolute home path (leaks the account name)'),
    (r'/home/(?!%s/)[a-z0-9._-]+/' % PLACEHOLDER_USERS,
     'absolute home path (leaks the account name)'),
    # Only the Users form leaks anything — a bare drive+folder names no account —
    # and it honours the placeholder list like its POSIX siblings above. Windows
    # paths reach this scanner through Lua/JSON source, so the separator is an
    # escaped pair. Was `[A-Z]:\\(?:repo|Users)`, which flagged D:\repo\Bar and
    # C:\Users\m\ in the test fixtures: false positives, the one failure mode
    # this guard cannot afford.
    (r'[A-Z]:\\\\Users\\\\(?!%s\\\\)[a-z0-9._-]+' % PLACEHOLDER_USERS,
     'absolute Windows path (leaks the account name)'),
    # Same reasoning: example.com and friends are reserved for documentation.
    (r'[\w.+-]+@(?!example\.(?:com|org|net)\b)[\w-]+\.[\w.]+', 'email address'),
    (r'(?i)\b(?:sk|pk|ghp|gho|github_pat)_[A-Za-z0-9_]{16,}', 'API token'),
    (r'(?i)\b(?:BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY)\b', 'private key'),
]

# Files where an example path is the point, not a leak.
ALLOW_PATHS = {'scripts/check-public-safe.py', 'CLAUDE.local.example.md', '.gitignore'}


def load_denylist():
    """One entry per line: a bare name or a /regex/. Blank lines and # are skipped."""
    if not os.path.exists(DENYLIST):
        return []
    out = []
    with open(DENYLIST, encoding='utf-8') as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            if len(line) > 2 and line.startswith('/') and line.endswith('/'):
                out.append((line[1:-1], 'denylisted pattern'))
            else:
                out.append((r'\b%s\b' % re.escape(line), 'denylisted name'))
    return out


def staged_files():
    cmd = ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR']
    res = subprocess.run(cmd, capture_output=True, text=True)
    return [f for f in res.stdout.splitlines() if f.strip()]


def tracked_files():
    res = subprocess.run(['git', 'ls-files'], capture_output=True, text=True)
    return [f for f in res.stdout.splitlines() if f.strip()]


def main():
    scan_all = '--all' in sys.argv
    files = tracked_files() if scan_all else staged_files()
    patterns = BUILTIN + load_denylist()

    if not os.path.exists(DENYLIST):
        sys.stderr.write(
            'note: %s not found — only built-in patterns are active.\n'
            '      Create it with one client or product name per line.\n' % DENYLIST)

    hits = []
    for path in files:
        if path in ALLOW_PATHS or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding='utf-8', errors='replace') as fh:
                for n, line in enumerate(fh, 1):
                    for pat, why in patterns:
                        if re.search(pat, line):
                            hits.append((path, n, why, line.strip()[:90]))
                            break
        except OSError:
            continue

    if not hits:
        print('public-safe: clean (%d file%s scanned)'
              % (len(files), '' if len(files) == 1 else 's'))
        return 0

    sys.stderr.write('\nBLOCKED — this repo is public and these look client-identifying:\n\n')
    for path, n, why, text in hits[:40]:
        sys.stderr.write('  %s:%d  [%s]\n      %s\n' % (path, n, why, text))
    if len(hits) > 40:
        sys.stderr.write('  ... and %d more\n' % (len(hits) - 40))
    sys.stderr.write(
        '\nMove the content to ~/.claude/CLAUDE.local.md, or genericise it.\n'
        'If the mention is genuinely safe, commit with --no-verify.\n\n')
    return 1


if __name__ == '__main__':
    sys.exit(main())
