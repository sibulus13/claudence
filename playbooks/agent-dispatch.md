# Agent dispatch playbook (cue: Agent, Workflow, /orchestrate)
- Order: named skill > role flow (`/orchestrate`) > `cycle` workflow (`~/.claude/workflows/cycle.js`) > named agent (implementer, reviewer, researcher, designer, architect, security) > general-purpose (say why).
- Before any fan-out, pin per stage: persona, model and effort, input/output contract, the exact gate command (interpreter included), worktree isolation, and an independent reviewer with a verdict scale (CONFIRMED / PLAUSIBLE / FAILED). The author never verifies their own work.
- `isolation: worktree` cuts from the session's repo. For another repo, `git -C <repo> worktree add` first and dispatch without isolation.
- Give every agent a deliverable and a stop condition. Subagents never edit governance or land on main (enforced: hooks/guard.py); the parent reviews and commits.
- Tell reviewers to flag only gaps that affect correctness or the stated requirements (they over-report otherwise).
- Separate repos need no worktree; same-repo parallel writers each get one.

## Lock before build; scope changes are new work items (owner, 2026-10-31)
- Dispatch an implementer only against a work item at `spec-locked` or later. Never build while its spec is still
  under review.
- A new requirement that arrives mid-build becomes a NEW work item queued behind the current one. It is never an
  edit to the running build, because each edit invalidates work already done and resets review.
- Split by the nesting rule before dispatch (more than 15 ACs means children). One implementer gets one child's
  context pack, not the whole tree.
- Review budget per item: one review plus one fix round. A second fix-first review is a stop. Classify it with
  `playbooks/first-principles.md`: if it is an approach finding, redesign; otherwise cut scope.
- Why: the spec-gate checker took 6+ review rounds on 2026-10-31. The spec grew during the build (v2 merge, work
  breakdown, context packs, off-the-shelf validators, exemption policy) inside one 46-rule work item.

## Feed review findings back into design (owner, 2026-10-31)
- Every review (in the cycle workflow or a direct reviewer agent) returns findings tagged with a gap category and a class.
  The parent appends the design- and spec-class ones to `docs/SPEC-GAP-LEDGER.md`: a new category gets a new row, and a
  repeat adds evidence to the existing row.
- Escape = a design-class finding in a category the item's `## Gap-ledger check` claimed. The goal is zero escapes:
  review finds only implementation slips, never design gaps.
- A category with 2+ escapes changes the designer persona or the standard (a checklist row or a checker rule), via
  `/retrospect`.

## Design briefs carry the survey verbatim (owner, 2026-10-31)
- A design brief includes the fleet survey's file:line findings for the role, and the web research sources,
  copied verbatim, never paraphrased. The Spindle specs missed Foreman's working worktree code because the
  brief summarized it away.
