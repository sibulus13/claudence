---
name: self-improve
description: Run the self-improvement loop. Scans recent session patterns, clusters by category, filters by threshold, and proposes additions to CLAUDE.md/memory/skill files. Logs run to ~/.claude/improve/history.jsonl for dashboard display.
version: 1.0.0
---

# /self-improve

Run the self-improvement loop: extract recurring patterns from recent sessions and promote them into durable orchestration context.

## When to use

- Manually, when you notice you've been repeating the same reminder
- Automatically via CronCreate (see config at `~/.claude/improve/config.json`)
- After any session where `/retrospect` would have been useful but wasn't run

## Steps

### 1. Load config

Read `~/.claude/improve/config.json`. Use defaults if missing:
```json
{ "frequencyDays": 7, "thresholdOccurrences": 2, "maxSessionsToAnalyze": 10, "autoApply": false }
```

### 2. Ingest sources

Read in parallel:
- `~/.claude/telemetry/reports/*.json` — friction reports (score, overrides, friction_notes, allow_suggestions)
- `~/.claude/projects/*/memory/MEMORY.md` — accumulated memory index files
- `~/.claude/projects/*/memory/feedback_*.md` — existing feedback memories (to avoid duplicating)
- Active project `context.md` files: Helm, Envoy, Crucible — look for drift notes and open decisions

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

If `autoApply: true`, skip the prompt and apply directly.

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
View history: http://localhost:3000/system
```
