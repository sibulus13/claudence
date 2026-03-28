# /retrospect

Run a friction retrospective. Analyze accumulated session friction reports, propose concrete improvements, apply them, and update memory context.

## Steps

### 1. Load friction reports

Read all JSON files in `C:/Users/Michael/.claude/telemetry/reports/`. For each report, extract:
- `score`, `interrupts`, `corrections`, `perm_req_count`
- `friction_notes[]`
- `allow_suggestions[]`
- `cwd` (which project this session was in)

Also read `C:/Users/Michael/.claude/telemetry/cumulative.json` for the aggregate picture.

### 2. Identify patterns

Group friction by type across reports:
- **Interrupt patterns**: Which cwds have high interrupt counts? What task types trigger them? (Suggests CLAUDE.md needs better upfront context or task decomposition instructions)
- **Correction patterns**: Rapid re-prompts after stop — what were the sessions working on? (Suggests Claude is misunderstanding something that needs clarification in CLAUDE.md)
- **Permission patterns**: Which tools appear repeatedly in `allow_suggestions`? (Direct signal: add to settings.json allow list)

### 3. Propose and apply changes

For each pattern with 2+ occurrences, propose a concrete fix:

**For repeated permission requests** → add to the appropriate settings.json allow array.
- Global (`C:/Users/Michael/.claude/settings.json`) if the tool appears across multiple projects
- Project-level (`.claude/settings.json`) if it's project-specific

**For interrupt/correction patterns** → propose CLAUDE.md additions:
- If interrupts cluster around a project: suggest adding task-framing instructions to that project's CLAUDE.md
- If corrections suggest a misunderstanding: add a clarifying rule to the relevant CLAUDE.md section

**For memory context** → check `C:/Users/Michael/.claude/projects/[project]/memory/MEMORY.md`:
- If a pattern reveals a consistent preference (e.g., user always corrects a certain code style), add or update the relevant `feedback_*.md` memory file

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
