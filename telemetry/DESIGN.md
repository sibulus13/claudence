# Claude Friction Tracker — Design Document

## Intent

Claude Code sessions accumulate friction that the user never explicitly names: a tool gets denied,
a prompt gets injected mid-run, the user escapes and immediately re-prompts. Individually these are
minor; in aggregate they reveal gaps between how Claude is configured and how it's actually used.

The goal is to capture that friction automatically and surface actionable improvements (specific
allow rules, CLAUDE.md additions, memory updates) at the end of sessions — and prompt a full
retrospective when enough has accumulated across sessions.

**What this is not:**
- A best-practices guide or template system
- A token/cost dashboard
- A security audit log

---

## Friction Signals

| Signal | Score | How detected |
|---|---|---|
| Mid-run interrupt | +3 | `UserPromptSubmit` fires but last session event is NOT a `stop` — Claude was still executing |
| Quick correction | +2 | `UserPromptSubmit` fires within 60s of a `stop` event — user escaped or Claude finished and user immediately re-prompted |
| Permission request | +1 | `PermissionRequest` hook fires — tool not pre-approved; generates specific allow-rule suggestion |

**What is NOT tracked (API limitation):**
- Whether the user clicked "Yes" or "No" at a permission dialog — no hook captures the response
- Context the user typed alongside a permission decision
- Ctrl+C vs. natural stop (both emit the same `Stop` event)

---

## Architecture

```
Claude Code session
        │
        ├── UserPromptSubmit ──► log-prompt.ps1
        │     • inspects last event in session JSONL
        │     • classifies: first_prompt | interrupt | correction | followup
        │     • appends {event:"prompt", classification, ts, session_id, cwd}
        │     • updates current-session.json (status bar KPIs)
        │     • refreshes /tmp/claude_start.txt (Stop sound elapsed-time)
        │
        ├── PermissionRequest ──► log-permission.ps1
        │     • appends {event:"permission_req", tool, input_preview, ts, session_id}
        │     • updates current-session.json (increments perm_reqs)
        │
        ├── Stop (sync) ──► analyze-session.ps1
        │     • appends {event:"stop"} FIRST — interrupt detection for next prompt
        │     • scores: interrupts×3 + corrections×2 + perm_reqs×1
        │     • writes reports/<session_id>.json
        │     • updates cumulative.json
        │     • outputs systemMessage if score ≥ 2 or cumulative threshold met
        │
        ├── Stop (async, 400ms delay) ──► sound hook (elapsed-time based)
        │
        └── statusLine ──► statusline.ps1  (runs after every assistant message)
              • reads current-session.json → P / I / B KPI counters
              • reads stdin JSON → context_window.used_percentage, cost.total_cost_usd
              • outputs: P:<n>  I:<n>  B:<n>  |  ctx <n>%  $<n>
              • color: cyan (P), green/yellow/red by threshold (I, B, ctx%)
```

### Why Stop fires correctly for interrupt detection

The official docs confirm: **Stop does NOT fire when the user presses Escape or Ctrl+C** (feature request #9516, open since Oct 2025). This means:
- Natural completion → Stop fires → analyze-session.ps1 writes `{event:"stop"}` synchronously → next prompt sees "stop" as last event → classified `correction` or `followup`
- Escape → Stop does NOT fire → no stop event in log → next prompt sees last event is NOT "stop" → classified `interrupt`

The synchronous Stop hook guarantees the stop event is written before Claude Code accepts the next UserPromptSubmit.

### Why Stop is synchronous

`analyze-session.ps1` runs without `async: true`. This ensures the `stop` event is written to the
session JSONL before Claude Code accepts the next user prompt. If it were async, a rapid re-prompt
could race and be misclassified as an interrupt.

---

## Data layout

```
~/.claude/
├── statusline.ps1                 status bar script (reads current-session.json + stdin)
└── telemetry/
    ├── sessions/
    │   └── <session_id>.jsonl     one per session, append-only
    ├── reports/
    │   ├── <session_id_prefix>.json  written once per Stop
    │   └── archived/              moved here after /retrospect processes them
    ├── current-session.json       live KPI state read by status bar
    ├── cumulative.json            aggregate score + sessions_since_review counter
    ├── log-prompt.ps1
    ├── log-permission.ps1
    ├── analyze-session.ps1
    └── analyze-permissions.ps1   legacy batch analysis script
```

### Session JSONL schema

```jsonc
{ "ts": "ISO8601", "session_id": "...", "event": "prompt",
  "classification": "first_prompt|interrupt|correction|followup", "cwd": "..." }

{ "ts": "ISO8601", "session_id": "...", "event": "permission_req",
  "tool": "Bash", "input_preview": "npx tsc --noEmit", "cwd": "..." }

{ "ts": "ISO8601", "session_id": "...", "event": "stop" }
```

### Report schema

```jsonc
{
  "ts": "ISO8601", "session_id": "...", "cwd": "...",
  "score": 5, "total_events": 9,
  "prompt_count": 3, "interrupts": 1, "corrections": 1, "perm_req_count": 1,
  "friction_notes": ["Mid-run interrupt (+3): ...", "Quick correction (+2): ...", "Permission needed (+1): ..."],
  "allow_suggestions": ["Bash(npx:*)"]
}
```

### Cumulative tracker schema

```jsonc
{ "total_score": 12, "sessions_since_review": 4, "last_review_ts": "ISO8601" }
```

---

## Notification thresholds

| Condition | Action |
|---|---|
| Per-session score < 2 | Silent |
| Per-session score 2–4 | Notify sound + systemMessage with report path |
| Per-session score ≥ 5 | Ring sound + systemMessage with specific allow-rule suggestions |
| sessions_since_review ≥ 3 AND cumulative_score ≥ 6 | Ring sound + systemMessage prompting `/retrospect`; resets cumulative counter |

---

## Retrospection workflow (`/retrospect`)

Defined in `~/.claude/skills/retrospect.md`. When invoked:

1. Read all JSON files in `reports/`
2. Group friction by type and project
3. For repeated permission requests → propose allow-rule additions to `settings.json`
4. For interrupt/correction clusters → propose CLAUDE.md task-framing additions
5. For consistent preference corrections → update `memory/feedback_*.md` files
6. Confirm with user, apply changes
7. Move processed reports to `reports/archived/`
8. Reset `cumulative.json`

---

## Status bar KPIs

Displayed after every assistant message. Hidden during permission prompts and autocomplete.

| Column | Label | Source | Color logic |
|---|---|---|---|
| Prompts sent | `P` | `UserPromptSubmit` count | Always cyan |
| Mid-run interrupts | `I` | `interrupt`-classified prompts | Green(0) → Yellow(1-2) → Red(3+) |
| Blocked tool calls | `B` | `PermissionRequest` count | Green(0) → Yellow(1-2) → Red(3+) |
| Context window | `ctx N%` | statusLine stdin | Green(<50%) → Yellow(50-80%) → Red(>80%) |
| Session cost | `$N.NN` | statusLine stdin | Dim (informational only) |

**Note on B (Blocked):** This counts all PermissionRequest events — both approved and denied by the user. True denial count cannot be separated without a `PostPermissionRequest` hook (feature request #11891).

## Gaps and deferred work

| Gap | Reason deferred |
|---|---|
| Permission denial detection (user clicks "No") | No shared req_id between PermissionRequest and PostToolUse; requires API support (#11891) |
| Context typed at permission dialog ("tab to add context") | UI consumes this text; no hook receives it. `ElicitationResult` only covers MCP dialogs, not permission prompts |
| Distinguish Escape from natural stop | Stop does NOT fire on Escape (confirmed). Our system handles this correctly via absence of stop event — no change needed |
| Cross-device portability | `setup.ps1` covers manual bootstrap; npm packaging deferred |
