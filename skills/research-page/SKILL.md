---
name: research-page
description: One page of research before any new work, for any project, internal or external. Compares what we already have with current practice, names the gaps, and picks the top changes. Use before a spec, a tool or convention choice, or an improvement review. Trading studies keep their own protocol and put this page in front.
---

# Research page

Answer four questions on one page. Stop when they are answered: this is not a survey.

**First**, look up what was explored before:
- `python C:/Users/Michael/.claude/scripts/context_index.py lookup <term> ...`
- Read the entries it returns before searching. An entry is a lead, so confirm it still holds.
- The index is `D:/repo/docs/CONTEXT_INDEX.md`: one row per area, each linking `D:/repo/docs/context/<area>.md`.

**Last**, update the index for every local file that answered something:
- Add a row `| Topic | Where | Kind | Summary | Verified |`, or move an existing row's Verified date to today.
- Where is an absolute `file:line`; Kind is code, spec, plan, decision, report, config, service or index.
- A detail that grows past a few rows gets its own area file, linked from the parent area as Kind `index`.
- A new area also gets a row in the root.
- Then run `python C:/Users/Michael/.claude/scripts/context_index.py check`.

| Question | How |
|---|---|
| **Have**: what do we already run, know, plan or decide? | Grep every repo for the role, then read the roadmap, specs, decisions, reports, memory and the fleet docs. Files named in the brief are a starting point, not the scope. Cite absolute `file:line`. Run the thing if it exists. |
| **Standard**: what is current practice? | Primary sources first, dated. Label blogs and vendor pages as weak. Say what you could not confirm. |
| **Gap**: where do we differ, and what does nobody offer? | Compare the two, row by row. A difference is only a gap if it costs something real. |
| **Do**: what are the top 3 changes? | Rank by how much it hurts today, with evidence from our own records. Name what to ignore. |

## Rules

- Measure before you claim: counts from real logs beat opinions.
- Reuse beats building. If something fits, say so and stop.
- "What we have" includes plans as well as code. Search the roadmap (`$FLEET_DOCS/LEDGER.md`), `$FLEET_DOCS/ARCHITECTURE_*.md`, and every repo's `docs/work` and `docs/specs` for the role before proposing anything.
- Keep to 300 words plus one comparison table.
- Give each row a criticality: high, medium or low. Only high rows reach the owner.
- State your sample and who rated it when you classify anything by judgement.

## Output

```
Question: <one line>
| Area | Have | Standard | Gap | Criticality |
Do: 1, 2, 3
Ignore: ...
Sources: ...
```
