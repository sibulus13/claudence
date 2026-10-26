---
paths:
  - "**/*.ps1"
  - "**/*.psm1"
  - "**/*.sh"
  - "**/*.cmd"
  - "**/*.bat"
  - "**/*.vbs"
---
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

## Windows, scheduled tasks, live workspaces
- Every scheduled task / daemon runs hidden: action `wscript.exe //B //Nologo <repo>\scripts\run-hidden.vbs <program> [args]` (copy from `D:/repo/Assistant/cortex/scripts/run-hidden.vbs`) or `pythonw.exe`; register with `-Hidden`. Never `powershell -WindowStyle Hidden` (it flashes). Node children use `windowsHide: true`. (Enforced: hooks/guard.py.)
- After `Register-ScheduledTask`: `Start-ScheduledTask`, then require `LastTaskResult` 0 and a non-empty log. A gate is verified by running its exact configured command.
- A task that runs "whether logged on or not" needs the owner's password to change: hand them a script (see `~/.claude/scripts/fix_marketopen_task.ps1`), never ask for the password in chat.
- Never spawn, switch or kill panes in the owner's live WezTerm workspaces while testing; validate headless and clean up.
- Preserve line endings when editing (CRLF files stay CRLF); repos declare them in `.gitattributes`.
- Kill stale dev servers you started; never build into a running dev server's `.next`.
- PowerShell 5.1: `ConvertFrom-Json` emits a JSON array as ONE object, so unroll (`| ForEach-Object { $_ }`) before filtering or sorting. Git Bash rewrites `/x` arguments into Windows paths: set `MSYS_NO_PATHCONV=1` or call from PowerShell.
