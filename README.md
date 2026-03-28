# Claude Code Dotfiles

Personal Claude Code configuration for Windows 11 — friction tracking, session telemetry, and project templates.

## What This Is

A hooks-driven system that measures and surfaces session friction in real time:

- **Status bar** — live KPIs after every response: prompts, interrupts, blocked tools, context %, cost, runtime
- **Friction scoring** — classifies prompts and tool approvals by friction type; plays sound on stop
- **Session reports** — per-session JSON report with turn breakdown, approval/denial inference, allow-rule suggestions
- **Rolling averages** — 5-session window for I/P and B/P rates; trend markers in status bar
- **Retrospection** — `/retrospect` skill to review accumulated friction and propose allow rules + memory updates

## Directory Layout

```
~/.claude/
├── CLAUDE.md               # Global instructions for all projects
├── PARALLELIZATION.md      # Parallelization guidelines for subagents
├── settings.json           # Hooks, permissions, statusLine
├── statusline.ps1          # Status bar script (runs after every response)
├── setup.ps1               # Bootstrap script — run once on a new machine
├── telemetry/
│   ├── DESIGN.md           # System design and friction model
│   ├── analyze-session.ps1 # Stop hook: score friction, play sound, write report
│   ├── analyze-permissions.ps1
│   ├── log-permission.ps1  # PermissionRequest hook: log + play ding
│   ├── log-prompt.ps1      # UserPromptSubmit hook: classify prompt
│   ├── log-tool-done.ps1   # PostToolUse hook: log for denial inference
│   └── record-compact.ps1  # PostCompact hook: capture summary in JSONL
├── skills/
│   └── retrospect.md       # /retrospect skill definition
└── templates/              # Project starter templates
    ├── expo-react-native.md
    ├── hono-api.md
    ├── nextjs.md
    ├── pnpm-monorepo.md
    └── typescript.md
```

## Installing on a New Machine

1. Install [Claude Code](https://docs.anthropic.com/claude-code)
2. Clone this repo to `~\.claude`:
   ```powershell
   git clone <repo-url> "$env:USERPROFILE\.claude-dotfiles"
   # Copy or symlink files into ~\.claude — do NOT clone directly into ~\.claude
   # as Claude Code writes runtime state there
   ```
   Or clone into a staging directory and run:
   ```powershell
   robocopy "$env:USERPROFILE\.claude-dotfiles" "$env:USERPROFILE\.claude" /E /XD .git
   ```
3. Run the bootstrap script:
   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\.claude\setup.ps1"
   ```
   This creates the required directories and generates the sound files from Windows Media.

4. Open Claude Code and run `/hooks` once to reload the settings.

## Hooks Wired

| Event | Script | Async | Purpose |
|-------|--------|-------|---------|
| `UserPromptSubmit` | `log-prompt.ps1` | yes | Classify prompt (first/followup/correction/interrupt/enrichment) |
| `Stop` | `analyze-session.ps1` | **no** | Score friction, play sound, write report, update rolling averages |
| `PostToolUse` | `log-tool-done.ps1` | yes | Log tool completions for approval/denial inference |
| `PostCompact` | `record-compact.ps1` | yes | Append compact summary to session JSONL |
| `PermissionRequest` | `log-permission.ps1` + ding | yes | Log permission event; play ding sound |

## Sound Logic (in `analyze-session.ps1`)

| Condition | Sound |
|-----------|-------|
| elapsed > 30s OR friction score ≥ 5 OR retrospect needed | `ring-half.wav` (chimes) |
| friction score ≥ 2 | `notify-half.wav` |
| otherwise | `notify-half.wav` (soft) |
| PermissionRequest | `ding-half.wav` |

Sounds are generated at 80% volume from Windows Media by `setup.ps1`.

## Friction Model

| Classification | Score | When |
|----------------|-------|------|
| `interrupt` | +3 | Short prompt while Claude was mid-run |
| `correction` | +2 | Re-prompt within 60s of Claude stopping |
| `enrichment` | +1 | Long/multi-topic prompt while Claude was mid-run |
| `permission_req` | +1 | Tool needed approval |
| `perm_repeat` | +2 | Same tool blocked again this session |

When cumulative score ≥ 6 across ≥ 3 sessions since last review, Claude suggests running `/retrospect`.

## Status Bar Layout

```
Prompts:4  Interrupts:0  Blocked:1  |  ctx 12%  $0.08  47m
Prompts:4  Interrupts:1 20%+  Blocked:2 50%+  |  ctx 67%  $0.13  12m
```

- **Prompts** (cyan label) — total prompts this session
- **Interrupts** (yellow label) — mid-run short injections; rate% and trend shown when history exists
- **Enrichments** (blue label) — mid-run rich context additions; only shown if > 0
- **Blocked** (red label) — tool calls needing approval; repeat blocks shown separately
- **ctx** (green label) — context window used %
- **$cost** (dim) — session cost
- **Xm / Xh Xm** (dim) — session elapsed time

Label colors are static. Value colors change only when thresholds are crossed.
