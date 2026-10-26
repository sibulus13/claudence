---
paths:
  - "**/*.md"
---
# Docs ground rules
- Open every doc with a Mermaid diagram (flowchart TD, at most 5 nodes per row, at most 5 participants per sequence). Prose only for contracts, exact copy and tables.
- One canonical doc per concern: update it instead of creating a parallel one; mark an overlapping doc `SUPERSEDED` with a pointer.
- Decisions go in the repo's `docs/DECISIONS.md`, one row: `| id | date | decision | status (assumed/confirmed/superseded/needs-owner) | rationale | revisit-when |`.
- Repos with several living docs keep a table mapping each doc to its purpose and update trigger.
- Cite files as absolute forward-slash paths with a line number (`D:/repo/x/docs/Y.md:1`) so WezTerm makes them clickable.
