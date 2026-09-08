---
name: retrospect
description: Run a friction retrospective. Use this skill when the user invokes /retrospect, asks to review session friction, wants to improve Claude Code configuration based on past sessions, or wants to add allow rules and update CLAUDE.md based on accumulated friction reports.
version: 1.0.0
---

# /retrospect

Run a friction retrospective. Analyze accumulated session friction reports, propose concrete improvements, apply them, and update memory context.

## Steps

### 1. Load friction reports

**Read every report file in the directory — across ALL sessions and cwds, not filtered to the
current one.** (Owner instruction, 2026-09-01, made explicit after end-of-day pulled 5 reports
spanning 3 distinct sessions/repos in one pass.) A per-session retrospective sees only its own
slice; the friction that matters is what accumulated across the whole day, including peer sessions
(e.g. `e-tech`) working the same repo. Group findings by `cwd` when proposing fixes so a
project-specific pattern doesn't get proposed as a global one, but never skip a report because it
came from a different session than the one running this skill.

Read all JSON files in `~/.claude/telemetry/reports/`. For each report, extract:
- `score`, `overrides`, `additions`, `perm_req_count`, `perm_repeat_count`
- `friction_notes[]`
- `allow_suggestions[]`
- `frustration_streaks[]` — runs of >=2 consecutive override/addition/denial_context prompts,
  from `telemetry/analyze-session.py`'s `frustration_streaks()`. Already dedupes a harness
  redelivery of the identical text, so every entry here is a genuine run of back-to-back
  corrections — a stronger signal than the same count scattered across the session, because it
  means the user re-explained the same expectation more than once in a row
- `cwd` (which project this session was in)

Also read `~/.claude/telemetry/cumulative.json` for the aggregate picture.

**Discard any `friction_notes[]` entry whose embedded excerpt starts with `<task-notification` or
`<cross-session-message`** (case-insensitive, allowing for leading whitespace) before counting it
toward `overrides`/`additions` for pattern purposes. `telemetry/lib/classification.py` now tags
these `system_notification` and scores them 0 going forward, but reports written before that fix
still carry them scored as `override`/`addition` — a background-agent completion or a peer
session's message, not the user redirecting or adding context. Recompute the effective
override/addition counts per report after discarding, and note in the summary if any report's
score changes as a result.

### 2. Identify patterns

Group friction by type across reports, **using the discarded-notification-filtered counts from
step 1, never the raw ones**:
- **Override patterns**: Which cwds have high override rates? What task types trigger them? (Suggests Claude is misunderstanding direction — CLAUDE.md may need clarifying rules or the user's prompts need more upfront context)
- **Addition patterns**: Frequent additions suggest the user is regularly forgetting to include context upfront — consider a CLAUDE.md note to ask for clarifying info before starting
- **Sustained frustration** (from `frustration_streaks[]`): a streak of length >=3 is a distinct, higher-severity pattern from an isolated override or addition — it means the same expectation went unmet across consecutive turns, not that Claude merely misunderstood once. **Read the streak's own excerpts, not just its length** — they usually show the SAME correction being repeated because the first fix didn't fully land (partial rather than root-cause). Propose a memory or CLAUDE.md fix aimed at the specific expectation named in the streak, not a generic "reduce friction" note. Cross-check `~/.claude/projects/[project]/memory/` first — this project's own feedback memory may already capture the pattern from when it happened, in which case there is nothing new to propose
- **Permission patterns**: Which tools appear repeatedly in `allow_suggestions`? (Direct signal: add to settings.json allow list)

### 3. Propose and apply changes

For each pattern with 2+ occurrences, propose a concrete fix:

**For repeated permission requests** → add to the appropriate settings.json allow array.
- Global (`~/.claude/settings.json`) if the tool appears across multiple projects
- Project-level (`.claude/settings.json`) if it's project-specific

**For override/addition patterns** → propose CLAUDE.md additions:
- If overrides cluster around a project: suggest adding task-framing instructions to that project's CLAUDE.md
- If overrides suggest a systematic misunderstanding: add a clarifying rule to the relevant CLAUDE.md section
- If additions are frequent: suggest Claude ask one clarifying question before beginning complex tasks

**For memory context** → check `~/.claude/projects/[project]/memory/MEMORY.md`:
- If a pattern reveals a consistent preference (e.g., user always overrides a certain approach), add or update the relevant `feedback_*.md` memory file

Ask the user to confirm each change before applying. Group them: "Here are 3 allow-rule additions, 1 CLAUDE.md update, and 1 memory update — apply all?" unless items conflict.

### 4. Archive addressed reports

After changes are applied, move the analyzed report files to `~/.claude/telemetry/reports/archived/` so they don't re-appear in the next retrospective.

Reset `cumulative.json`:
```json
{ "total_score": 0, "sessions_since_review": 0, "last_review_ts": "<now>" }
```

### 5. Summary

Report what was changed:
- N allow rules added (list them)
- N CLAUDE.md lines added (list the files)
- N memory entries updated (list the files)
- N reports archived
