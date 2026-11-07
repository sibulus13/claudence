---
name: spec-deltas
description: Record what the build, refactor or QA found that the spec did not say - a state, input, dependency, environment fact or behaviour change - in the work item and in the cross-project spec-gap ledger that retros read. Use during implementation, a refactor pass, or a QA or live run of any work item.
---

# Spec deltas

A delta is anything the work met that the spec did not cover. For example: a state the diagram misses, an input or failure seen live, an environment fact (line endings, PATH), a dependency's real behaviour, or a behaviour that had to change. Record it the moment you find it.

1. **In the work item.** Append a row to `## Build amendments`, the README's last section; create it if it is missing.
   - Header: `| Stage | Change or discovery | Why (what exposed it) | Test |`
   - Stage is `implement`, `refactor` or `qa`.
   - Test names the test that pins the delta. A discovery with no behaviour change writes `none: <reason>`.
   - A behaviour change also tightens the AC or state it touches (`C:/Users/Michael/.claude/skills/dark-factory/WORK-ITEM-STANDARD.md`, "Build amendments"). Fix the diagram in the same commit.
2. **In the cross-project ledger,** for the retros. Append one row to `C:/Users/Michael/.claude/docs/SPEC-GAP-LEDGER.md`:
   - Date, Project (`<repo> <item id> (<stage>)`), What was missed (one line plus the item path), and Category (an existing one, or `NEW: <name>`).
   - Put `pending retro` in "Now checked in Phase 2 as".
   - That file is in the public `claudence` repo, so give a project name and a plain description only: no private paths, names or data.
3. **In your report,** list the rows under "Spec deltas".

A change of approach (another layer or contract) is not a delta. Stop and go back to design.

If nothing was found, write nothing.
