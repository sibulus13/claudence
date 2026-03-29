# Global Claude Code Instructions

These instructions apply to every project on this machine. Project-level CLAUDE.md files extend and override these.

---

## Environment

- **OS**: Windows 11 Pro — always use PowerShell syntax, never cmd.exe
- **Shell**: bash (Claude Code shell), but commands that invoke Windows tools use `powershell.exe -NoProfile -Command "..."`
- **Node**: 20 LTS
- **Package manager**: pnpm for all JavaScript/TypeScript projects — never use `npm install` or `yarn` inside a pnpm workspace
- **Python**: available at `python` (not `python3`)
- **Path separators**: use forward slashes in code; backslashes only when required by Windows APIs

## Response Style

- Be concise — lead with the answer, not the reasoning
- Do not summarize what you just did at the end of a response
- Do not add unsolicited comments, docstrings, or type annotations to code you didn't change
- Do not add emojis unless explicitly asked
- Reference code by `file:line` pattern so the user can navigate directly

## Code Quality — Universal

- **TypeScript**: strict mode always (`"strict": true`). No implicit `any`. Explicit return types on exported functions
- **No dead code**: remove unused imports, variables, and functions rather than commenting them out
- **No magic numbers**: extract constants with descriptive names
- **Error handling**: only handle errors at system boundaries (user input, external APIs). Do not add try/catch defensively around internal code that shouldn't fail
- **No over-engineering**: three similar lines of code is better than a premature abstraction. No helpers for one-time operations
- **Secrets**: never hardcode secrets, API keys, or credentials. Always use environment variables. Never commit `.env` files

## Security

- Validate input only at system boundaries; trust internal code
- Sanitize before interpolating user input into SQL, shell commands, or HTML
- Use parameterized queries — never string-concatenated SQL
- Dependencies: prefer well-maintained packages with known security posture; flag suspicious transitive deps

## Git Conventions

- Conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`
- Never force-push `main` or `master`
- Never use `--no-verify` unless explicitly requested
- Never amend published commits — create new ones instead
- Stage specific files, not `git add -A`, unless all changes are intentional

## Windows-Specific Conventions

- File copies: `Copy-Item` not `cp`
- Directory listing: `Get-ChildItem` not `ls` (or use the Read/Glob tools directly)
- Generate random secrets: `-join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) })`
- Firewall rules: `New-NetFirewallRule` not `netsh advfirewall`
- Never assume `openssl`, `curl` (use `Invoke-RestMethod`), or Unix utilities are in PATH

## Task Execution — Parallelization First

**Default to parallel, not sequential.** Before executing any multi-step task, identify which steps are independent and run them concurrently.

- Dispatch independent research, exploration, and file reads as parallel tool calls in a single message
- Use background subagents (`run_in_background: true`) for tasks whose results aren't immediately needed
- Use `isolation: worktree` for any subagent that writes files, to prevent conflicts
- Sequential only when: output of step N is required input for step N+1, or both steps touch the same file
- Safe concurrency: up to 3–5 background subagents on Max plan before rate limits become a constraint
- Model allocation: Sonnet for worker subagents, Haiku for pure exploration, Opus for orchestration decisions only

## Audio Hooks (Do Not Interfere)

Sound notifications are configured globally:
- **Stop**: chimes (end of execution — ring-half.wav)
- **PermissionRequest**: ding (tool call needs approval — ding-half.wav)

Do not play sounds manually or adjust system volume unless explicitly asked.

## Memory System

Auto-memory is active at `C:\Users\Michael\.claude\projects\[project]\memory\`. When learning something non-obvious about the user, project, or workflow, save it to the appropriate memory file and update `MEMORY.md`. Check existing memories before starting work on a familiar project.

## Available Skills

These user-defined skills are loaded at session start from `~/.claude/skills/`:

- `/retrospect` — Review accumulated session friction reports, propose allow-rule additions and CLAUDE.md updates, apply them, and reset the cumulative counter. Run this when the status bar shows a high override or block rate, or when Claude suggests it automatically.
