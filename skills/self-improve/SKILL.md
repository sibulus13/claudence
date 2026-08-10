---
name: self-improve
description: Run the self-improvement loop. Scans recent session patterns, clusters by category, filters by threshold, and proposes additions to CLAUDE.md/memory/skill files. Logs run to ~/.claude/improve/history.jsonl for dashboard display.
version: 1.0.0
---

# /self-improve

Run the self-improvement loop: extract recurring patterns from recent sessions and promote them into durable orchestration context.

## When to use

- Manually, when you notice you've been repeating the same reminder
- **Automatically surfaced** — `improve/audit.py` runs on every Stop hook and `scripts/workspace-state.py` injects due-ness at SessionStart, so you are told when it is due rather than having to remember. (`CronCreate` is session-only and cannot schedule this; durable scheduling here is launchd + hooks.)
- After any session where `/retrospect` would have been useful but wasn't run

## Steps

### 1. Load config

Read `~/.claude/improve/config.json`. Use defaults if missing:
```json
{ "frequencyDays": 7, "thresholdOccurrences": 2, "maxSessionsToAnalyze": 10, "autoApply": false }
```

### 2. Ingest sources

**Read `~/.claude/improve/state.json` first** — `audit.py` has already measured context density,
cross-file duplication, staleness and due-ness. Do not re-derive those; they are deterministic and
already done. Your job starts where judgement starts.

Then read in parallel:
- `~/.claude/telemetry/reports/*.json` — friction reports (score, overrides, friction_notes, allow_suggestions)
- `~/.claude/projects/*/memory/MEMORY.md` — accumulated memory index files
- `~/.claude/projects/*/memory/feedback_*.md` — existing feedback memories (to avoid duplicating)
- Each active workspace's `docs/STATE.md` and `docs/TODO.md` — the state contract in the Session Start Protocol. Look for repeated blockers and items that keep moving between sessions without progressing

### 3. Extract patterns

From each source, identify:
- **Repeated corrections**: user said "don't do X" or "always do Y" more than once
- **Recurring follow-ups**: something that was "supposed to be done" but had to be reminded
- **Drift patterns**: context.md DRIFT fields from recent agent runs
- **Permission patterns**: tools that repeatedly hit permission gates (add to allow list)
- **Stack-specific discoveries**: non-obvious behavior found in a specific framework/library

For each pattern, record:
```json
{
  "pattern": "short description",
  "category": "global | project | stack | user-preference",
  "target": "which project (if project/stack) or 'all'",
  "occurrences": 3,
  "evidence": ["session A said X", "session B repeated X"],
  "proposedAddition": "exact text to add to target file"
}
```

### 4. Filter by threshold

Only patterns with `occurrences >= thresholdOccurrences` proceed.
Patterns already documented in the target file are skipped (check before proposing).

### 4b. Refactor and deduplicate — not only add

**A loop that only adds rules degrades monotonically.** For every item in `state.json`:

- `refactor` → propose the split. A file past 500 lines or a section past 60 gets its largest
  section extracted to `references/` with a two-line summary left behind.
- `duplication` → **designate one canonical home and make the other a pointer.** Never leave two
  copies "in sync"; they drift, and the reader cannot tell which is current.
- `stale` → either re-verify and bump `last-verified`, or archive per the knowledge-lifecycle rules.

Treat these with the same threshold discipline as additions: propose, do not silently restructure
governance.

### 5. Propose

Present grouped proposals:
```
## Self-Improvement Proposals — [date]

### Global (CLAUDE.md)
1. [pattern] → add: "[proposed text]"
   Evidence: seen 3 times — [brief quotes]

### Project: Crucible
2. [pattern] → add to Stock/Research 2026/CLAUDE.md: "[proposed text]"

### User preference (memory)
3. [pattern] → update feedback_responses.md: "[proposed text]"

Apply all? (y/n/selective)
```

**Blast radius decides autonomy** (`docs/AGENT-LOOP.md` §5), not the `autoApply` flag alone:

| Target | Mode |
|---|---|
| Allow-rules, brief templates, skill hints, per-class defaults | Auto-apply, logged and revertible |
| Gate thresholds, model/effort routing | Auto-apply **shadow first** — one cycle recording what *would* have changed |
| `CLAUDE.md`, memory, anything governance | **Propose only.** Agents never autonomously edit governance |

### 6. Apply changes

For each approved proposal:
- Write to the target file (CLAUDE.md, project CLAUDE.md, or memory file)
- Update MEMORY.md index if writing a new memory file

### 7. Log run

Append to `~/.claude/improve/history.jsonl`:
```json
{
  "id": "run-[timestamp]",
  "timestamp": "[ISO]",
  "sessionsAnalyzed": 8,
  "patternsFound": 12,
  "augmentations": [
    { "category": "global", "target": "~/.claude/CLAUDE.md", "rule": "...", "occurrences": 3, "appliedAt": "[ISO]" }
  ],
  "skipped": [
    { "pattern": "...", "reason": "below threshold" }
  ]
}
```

### 7b. Append to the ledger

Append what was applied to `~/.claude/improve/LEDGER.md` under `## Changes`, newest first, with the
revert id. **`history.jsonl` is the machine record; the ledger is the one a human reads** — and the
whole point of unattended operation is that the human reads afterwards rather than gating each change.

### 8. Reset telemetry

Archive processed friction reports to `~/.claude/telemetry/reports/archived/`.
Reset `cumulative.json` as in `/retrospect`.

### 9. Summary

```
## Self-Improvement Run — [date]

Sessions analyzed: N
Patterns found: N
Threshold (≥N occurrences): N applied, N skipped
Categories: N global, N project, N stack, N user-preference

Applied:
- [list of what was added and where]

Skipped (below threshold or already documented):
- [count]

Next scheduled run: [date] (every N days per config)
View history: `improve/LEDGER.md` (human) · `improve/history.jsonl` (machine)
```
