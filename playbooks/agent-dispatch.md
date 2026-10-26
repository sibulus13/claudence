# Agent dispatch playbook (cue: Agent, Workflow, /orchestrate)
- Order: named skill > role flow (`/orchestrate`) > `cycle` workflow (`~/.claude/workflows/cycle.js`) > named agent (implementer, reviewer, researcher, designer, architect, security) > general-purpose (say why).
- Before any fan-out, pin per stage: persona, model and effort, input/output contract, the exact gate command (interpreter included), worktree isolation, and an independent reviewer with a verdict scale (CONFIRMED / PLAUSIBLE / FAILED). The author never verifies their own work.
- `isolation: worktree` cuts from the session's repo. For another repo, `git -C <repo> worktree add` first and dispatch without isolation.
- Give every agent a deliverable and a stop condition. Subagents never edit governance or land on main (enforced: hooks/guard.py); the parent reviews and commits.
- Tell reviewers to flag only gaps that affect correctness or the stated requirements (they over-report otherwise).
- Separate repos need no worktree; same-repo parallel writers each get one.
