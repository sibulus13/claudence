---
name: qa
description: Validate an implementation against its spec acceptance criteria. Outputs per-item verdict (MET/PARTIAL/FAILED) plus regression risk analysis. Use after any Implementer agent completes.
version: 1.0.0
---

# /qa

Run a QA validation pass against a project's spec acceptance criteria.

## When to use

- After an Implementer agent completes a milestone
- When the user asks "does this pass?" or "validate against spec"
- As the final step in any `feature` or `bugfix` flow

## Steps

### 1. Load the AC

Read the project's `context.md`. Find the `## Next milestone — acceptance criteria` section.
Extract each AC item as a checkable condition.

### 2. Determine test invocation

From the project's stack, identify how to run tests:
- TypeScript/Next.js: `pnpm tsc --noEmit && pnpm vitest run`
- Python: `pytest --timeout=30 -x`
- No tests: note explicitly — do not invent tests at this stage

### 3. Validate each AC item

For each AC item, verify it independently:
- **MET**: condition is demonstrably satisfied (test passes, file exists, output matches)
- **PARTIAL**: condition is partially satisfied; describe what's missing
- **FAILED**: condition is not satisfied; describe what's wrong

Do not interpret "it seems to work" as MET. Be conservative.

### 4. Regression surface analysis

Identify files changed since the last milestone. For each changed file:
- List which existing features depend on it
- Flag any that could be affected: `[RISK] file.ts:42 — used by X, could be affected by Y`

### 5. Output

```
## QA Report — [Project] [Milestone]

### AC Verdicts
- [ ] AC 1: [description] → FAILED — reason
- [x] AC 2: [description] → MET
- [~] AC 3: [description] → PARTIAL — what's missing

### Regression Risk
- LOW: no shared dependencies changed
- [or] [RISK] lib/schemas.ts — shared by Envoy + Helm; HelmStatusSchema addition is additive, no breaking change

### Test results
[paste tsc / vitest / pytest output or "tests not yet written"]

### Verdict
PASS / FAIL / PASS WITH NOTES
```

If FAIL or PARTIAL: do not mark the milestone as done in context.md. Surface what needs to be fixed.
