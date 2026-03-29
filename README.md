# Claudence

A hooks-driven telemetry and workflow system for [Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview) on Windows. It tracks session friction in real time, plays sound notifications, and periodically prompts you to reflect on how you're collaborating with Claude — so each session runs more smoothly than the last.

---

## What You Get

**A live status bar after every response:**

```
Prompts:6  Overrides:1 17%+  Additions:2  Blocked:1 17%  |  ctx 34%  $0.21  28m
```

**Sound notifications:**
- Chime when Claude finishes (louder for long or high-friction runs)
- Ding when a tool needs your approval

**Per-session friction reports** saved to `~/.claude/telemetry/reports/` — what was overridden, which tools you blocked, what patterns are emerging.

**Trend tracking** across your last 5 sessions — the status bar shows `+` or `-` next to override and block rates when they drift meaningfully from your rolling average.

**Retrospection prompts** — after enough friction accumulates across sessions, Claude will suggest running `/retrospect` to review patterns, update allow rules, and refresh context.

---

## How It Works

Every prompt you send is classified into one of four types:

| Type | When | Friction |
|------|------|---------|
| `first_prompt` | First message in a session | 0 |
| `followup` | Clean next turn after Claude stopped | 0 |
| `override` | Replacement language after stop ("actually", "instead", "forget that", "start over") | +3 |
| `addition` | Additive language ("also", "note that", "by the way") OR any prompt sent mid-run | +1 |

And every tool approval or denial is tracked:

| Event | Friction |
|-------|---------|
| Tool needed approval | +1 |
| Same tool blocked again this session | +2 |

**Why this matters:** High override rates mean Claude is consistently going in the wrong direction — your prompts may need more upfront context or constraints. High block rates mean your allow rules are out of date. The system surfaces these patterns so you can fix the root cause instead of living with the friction.

---

## Status Bar Explained

```
Prompts:4  Overrides:0  Blocked:1  |  ctx 12%  $0.08  14m
```

| Field | Color | Meaning |
|-------|-------|---------|
| `Prompts:N` | cyan label | Total prompts sent this session |
| `Overrides:N` | red label | Prompts that replaced the current direction |
| `Additions:N` | yellow label | Only shown if > 0. Context injected mid-run or additively |
| `Blocked:N` | red label | Tool calls that needed approval |
| `ctx N%` | green label | Context window used |
| `$N.NN` | dim | Session cost |
| `Nm` / `Nh Nm` | dim | Session elapsed time |

Values are default terminal color until they cross a threshold, then turn **yellow** (warning) or **red** (critical). With 2+ sessions of history, override and block rates show a trend marker: `+` means worse than your rolling average, `-` means better.

---

## Prerequisites

- Windows 11 (uses Windows Media sounds and PowerShell)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview) installed
- PowerShell 5.1+ (ships with Windows 11)

---

## Installation

**1. Clone this repo** into a staging directory (do NOT clone directly into `~\.claude` — Claude Code writes runtime state there and will conflict with git):

```powershell
git clone https://github.com/michaelruiz/claudence "$env:USERPROFILE\.claude-dotfiles"
```

**2. Copy files into `~\.claude`:**

```powershell
robocopy "$env:USERPROFILE\.claude-dotfiles" "$env:USERPROFILE\.claude" /E /XD .git /XF .gitignore README.md
```

**3. Run the bootstrap script** to create directories, generate sound files from Windows Media, install Pester 5, and wire the pre-commit hook:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\.claude\setup.ps1"
```

**4. Reload hooks** — open Claude Code and run `/hooks` once, or restart.

That's it. The status bar and sound notifications are active from your next session.

---

## File Layout

```
~/.claude/
├── CLAUDE.md                    # Global instructions injected into every session
├── settings.json                # Hooks, permissions, statusLine config
├── statusline.ps1               # Status bar — runs after every response
├── setup.ps1                    # Bootstrap — run once on a new machine
│
├── telemetry/
│   ├── lib/
│   │   └── classification.ps1   # Pure classification functions (dot-sourced by tests)
│   ├── log-prompt.ps1           # UserPromptSubmit: classify + record prompt
│   ├── analyze-session.ps1      # Stop: score session, play sound, write report
│   ├── log-permission.ps1       # PermissionRequest: log + play ding
│   ├── log-tool-done.ps1        # PostToolUse: log completions (for denial inference)
│   └── record-compact.ps1       # PostCompact: capture summary in session log
│
├── tests/
│   ├── classification.tests.ps1 # 57 Pester 5 tests for classification logic
│   └── run-tests.ps1            # Test runner (auto-installs Pester 5 if missing)
│
├── hooks/
│   └── pre-commit               # Gates telemetry/ commits on passing tests
│
├── skills/
│   └── retrospect.md            # /retrospect skill definition
│
└── templates/                   # Project starter templates for Claude
    ├── expo-react-native.md
    ├── hono-api.md
    ├── nextjs.md
    ├── pnpm-monorepo.md
    └── typescript.md
```

---

## Hooks Wired

| Event | Script | Blocking | Purpose |
|-------|--------|----------|---------|
| `UserPromptSubmit` | `log-prompt.ps1` | yes | Classify prompt before Claude responds (sync ensures status bar is always current) |
| `Stop` | `analyze-session.ps1` | yes | Score session, play sound, write report, update rolling averages |
| `PostToolUse` | `log-tool-done.ps1` | no | Log completions for approval/denial inference |
| `PostCompact` | `record-compact.ps1` | no | Append compact summary to session JSONL |
| `PermissionRequest` | `log-permission.ps1` + ding | no | Log event; alert you with a ding |

---

## Use Cases

### 1. Tighten your allow rules over time

Every time Claude asks for tool approval, it's logged. After a session, the report at `~/.claude/telemetry/reports/<id>.json` includes `allow_suggestions` — exact permission rule strings you can paste into `settings.json` to stop being asked next time. Run `/retrospect` and Claude will propose the rules for you.

### 2. Diagnose why a session felt rough

Open the session report after a high-friction run. The `turns[]` array shows every turn: what prompt classification it got, how many tool calls happened, and whether each approval was granted or denied. A turn with `classification: "override"` means you had to redirect Claude — which is a signal that the original prompt left too much ambiguous.

### 3. Improve your prompting habits

If your `Overrides` rate is consistently `+` (worse than average), your initial prompts aren't giving Claude enough direction to run unattended. The status bar makes this visible in real time — before bad habits compound. Use `/retrospect` to review your last few sessions and get concrete suggestions for what to clarify upfront.

### 4. Track cost and context across a long session

The status bar shows `ctx %` and `$cost` after every response. When context climbs past 50% (yellow) or 80% (red), you know a `/compact` is coming. Seeing the cost tick up in real time keeps you aware of how expensive exploratory sessions are versus focused ones.

### 5. Know exactly when Claude is done — without watching the screen

The chime fires the moment Claude stops. Short tasks get a soft notify; anything over 30 seconds or with significant friction gets a full chime. You can go do something else and come back when you hear the sound.

---

## Customization

**Change friction thresholds** — edit the scoring in `telemetry/analyze-session.ps1` (the `foreach ($p in $prompts)` block).

**Change sound logic** — the unified decision is near the bottom of `analyze-session.ps1`:
```powershell
$play_ring = ($elapsed -gt 30 -or $score -ge 5 -or $retrospect_needed)
```

**Add your own instructions** — `CLAUDE.md` is injected into every session. Add project conventions, personal preferences, or anything else you want Claude to always know.

**Add project templates** — drop a `.md` file into `templates/`. These can be referenced in `CLAUDE.md` or loaded manually at the start of a session.

---

## Runtime Files (not committed)

These are created at runtime and excluded from the repo:

| Path | Contents |
|------|----------|
| `telemetry/current-session.json` | Live KPIs for the active session |
| `telemetry/rolling-averages.json` | 5-session rolling averages |
| `telemetry/cumulative.json` | Cross-session friction accumulator |
| `telemetry/sessions/<id>.jsonl` | Raw event log per session |
| `telemetry/reports/<id>.json` | Scored report per session |
| `sounds/*.wav` | Regenerated from Windows Media by `setup.ps1` |

---

## Roadmap

Nice-to-have additions that aren't built yet:

### Skills
| Skill | What it would do |
|-------|-----------------|
| `/friction` | Print the current session's live friction score and notes on demand, without waiting for Stop |
| `/report` | Summarize the last session's friction report in readable prose — score, overrides, blocked tools, turn breakdown |
| `/session` | Show a timeline of all events logged for the current session (prompts, tool calls, permission requests, compactions) |

### Hook gaps
| Hook | What it enables |
|------|----------------|
| `Notification` | Play a sound when Claude needs your attention while you're away from the screen |
| `PreCompact` | Prompt you to specify what context to preserve before compaction runs |
| `PreToolUse` | Log what Claude intends to do before it does it — richer telemetry and optional input rewriting |

### Scale
| Item | What it would do |
|------|-----------------|
| Cross-machine sync | Push telemetry reports to a remote store so rolling averages survive machine changes |
| Team mode | Aggregate friction data across multiple users in a shared repo |

---

## License

MIT
