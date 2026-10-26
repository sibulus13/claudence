---
paths:
  - "**/.claude/settings*.json"
  - "**/.claude/hooks/**"
  - "**/hooks/*.py"
  - "**/hooks/*.ps1"
---
# Claude Code hook ground rules
- A hook enforces only if it fails closed: PreToolUse blocks with exit 2 (reason on stderr) or a JSON `permissionDecision` of `deny`/`ask`. Exit 0 with no output = allow; any other exit code only warns.
- Stop hooks can loop: check `stop_hook_active` in the input and block at most once.
- Match against the command minus quoted strings (commit messages are data, not flags).
- Distinguish unattended runs (`permission_mode: bypassPermissions`, or an env flag the job sets) before applying interactive-only rules.
- Python hooks start fast; PowerShell hooks cost ~0.5 s each, so keep them off hot events (PreToolUse/PostToolUse).
- Project `.claude/settings.json` is not inherited from parent folders: a D:/repo session runs a project's hooks only through the D:/repo router.
- Every hook ships with acceptance tests that run it as Claude Code does (JSON on stdin) and are seen failing against a no-op hook.
