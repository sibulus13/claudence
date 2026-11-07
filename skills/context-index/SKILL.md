---
name: context-index
description: Look up where a role, spec, plan or doc already lives before searching or building, and record what you explored afterwards. The index is D:/repo/docs/CONTEXT_INDEX.md, nested by area. Use at the start of any research, design, build or review that touches local code or docs.
---

# Context index

**First**, before searching or creating anything:
- Run `python C:/Users/Michael/.claude/scripts/context_index.py lookup <term> ...` with the role's words (for example `runner hang`, `persona skill`).
- Read the entries it returns before grepping. An entry is a lead: confirm it still holds.
- A planned or locked spec counts as existing work, so build on it or name the split.
- For the whole map of services, runtimes, agents and practices, read `D:/repo/docs/README.md`.

**Last**, for every local file that answered something:
- Add a row `| Topic | Where | Kind | Summary | Verified |` to the matching `D:/repo/docs/context/<area>.md`, or move an existing row's Verified date to today.
  - Where is an absolute `file:line`.
  - Kind is one of code, spec, plan, decision, report, config, service or index.
- When a topic grows past a few rows, give it its own area file and link it from the parent area as Kind `index`. A new area also gets a row in `D:/repo/docs/CONTEXT_INDEX.md`.
- Then run `python C:/Users/Michael/.claude/scripts/context_index.py check`.

If you have no file-edit tool, list the new rows in your report under "Context index rows", and whoever dispatched you adds them.

Skip both steps for work that touches no local code or docs.
