# Shell ground rules (PowerShell 5.1 and bash on Windows)

## PowerShell
- Scripts start with `$ErrorActionPreference = 'Stop'` for cmdlets, BUT wrap native executables
  in `'Continue'` and redirect `2>&1` into the log: PS 5.1 turns native stderr into a terminating
  error (Augur_Poll incident 2026-10-24). Propagate `$LASTEXITCODE` with `exit $LASTEXITCODE`.
- No `&&` / `||`, ternary or `??` in 5.1. Use `if ($?) { ... }`.
- `Set-Content`/`Out-File` with `-Encoding utf8` when another tool reads the file.
- Scheduled tasks run through `wscript //B run-hidden.vbs` with `-Hidden`; after registering, run
  once and require `LastTaskResult 0` and a non-empty log.

## bash
- Quote every path (`"$TEMP/x"`); this machine has paths with spaces (`Research 2026`).
- `set -euo pipefail` in scripts; long commands run in the background, not on the main thread.
- No in-place edits with fragile regex across many files: prefer a small Python script that
  preserves line endings (CRLF incident 2026-10-25).
- Never write source code through a Python string inside a heredoc: escapes like `\n` and `\s` are
  re-interpreted and land as real newlines (JS syntax errors, Foreman alerts.js 2026-10-25). Use the
  Edit tool, or a literal `cat <<'EOF'` with the exact text.
- git: never `--autostash` or bare `git stash` (the stash stack is shared across worktrees and
  sessions; slip 2026-10-25 on a Foreman rebase). Commit WIP or rebase with a clean tree.
