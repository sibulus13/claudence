# /retrospect

Run a friction retrospective. Analyze accumulated session friction reports, propose concrete improvements, apply them, and update memory context.

## Steps

### 1. Load friction reports

Read all JSON files in `C:/Users/Michael/.claude/telemetry/reports/`. For each report, extract:
- `score`, `overrides`, `additions`, `perm_req_count`, `perm_repeat_count`
- `friction_notes[]`
- `allow_suggestions[]`
- `cwd` (which project this session was in)

Also read `C:/Users/Michael/.claude/telemetry/cumulative.json` for the aggregate picture.

### 2. Identify patterns

Group friction by type across reports:
- **Override patterns**: Which cwds have high override rates? What task types trigger them? (Suggests Claude is misunderstanding direction — CLAUDE.md may need clarifying rules or the user's prompts need more upfront context)
- **Addition patterns**: Frequent additions suggest the user is regularly forgetting to include context upfront — consider a CLAUDE.md note to ask for clarifying info before starting
- **Permission patterns**: Which tools appear repeatedly in `allow_suggestions`? (Direct signal: add to settings.json allow list)

### 3. Propose and apply changes

For each pattern with 2+ occurrences, propose a concrete fix:

**For repeated permission requests** → add to the appropriate settings.json allow array.
- Global (`C:/Users/Michael/.claude/settings.json`) if the tool appears across multiple projects
- Project-level (`.claude/settings.json`) if it's project-specific

**For override/addition patterns** → propose CLAUDE.md additions:
- If overrides cluster around a project: suggest adding task-framing instructions to that project's CLAUDE.md
- If overrides suggest a systematic misunderstanding: add a clarifying rule to the relevant CLAUDE.md section
- If additions are frequent: suggest Claude ask one clarifying question before beginning complex tasks

**For memory context** → check `C:/Users/Michael/.claude/projects/[project]/memory/MEMORY.md`:
- If a pattern reveals a consistent preference (e.g., user always overrides a certain approach), add or update the relevant `feedback_*.md` memory file

Ask the user to confirm each change before applying. Group them: "Here are 3 allow-rule additions, 1 CLAUDE.md update, and 1 memory update — apply all?" unless items conflict.

### 4. Archive addressed reports

After changes are applied, move the analyzed report files to `C:/Users/Michael/.claude/telemetry/reports/archived/` so they don't re-appear in the next retrospective.

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
