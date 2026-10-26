# Global Claude Code instructions

Facts and pointers for every session. How answers look: output style `terse-ledger`. Rules that must never be
broken are enforced in code (`~/.claude/hooks/guard.py`), not here. Each rule's history:
`~/.claude/docs/CLAUDE-2026-10-25-pre-refactor.md` and `~/.claude/docs/DECISIONS.md`.

## Critical
1. Work autonomously; stop only for a typed blocker (section 3).
2. The author of code is never its only verifier on a live, money or auth path.
3. Commands that may take more than ~30 s run in the background; the main thread stays free.

## 1. Environment
- Windows 11 Pro. Two shells, each in its own syntax: the PowerShell tool (5.1: no `&&`, `?:`, `??`) and the
  Bash tool (Git Bash, POSIX). Forward slashes in code; backslashes only where a Windows API needs them.
- `python` (C:/Python312), never `python3`. pnpm for JS/TS (exception: `SaaS/Workout Gen` uses npm).
  Node 20 is installed; target 22+ for new work.
- Editor VS Code (`code -r -g file:line`). Terminal WezTerm: only absolute drive-letter paths become links.
- Not on PATH: openssl, rg, curl (use `Invoke-RestMethod`). Installed: gh, vercel, pnpm.

## 2. Repo layout (D:/repo)
- `D:/repo/<Theme>/<project>`, never bare at the root. Themes:
  - `Finance/` crucible, augur, market-signal-watch
  - `Factory/` ostler -> foreman -> catwalk, herald
  - `SaaS/` cashcow (= Tarive), certify, nuwa, `pylon/*`, Workout Gen (= Ascension)
  - `Assistant/` cortex, groundtruth; `Lib/` telefi; `Life/` personal docs and apps; `web/personal/`;
    `Experiment/`; `_Misc/`; `_Archive/` (index `D:/repo/_Archive/README.md`)
- Legacy `AI/`, `Bot/`, `Data/` are being emptied. A new repo goes in a theme folder; say which.
- Moving a repo: `/repo-move`. Code derives paths from the repo root, never absolute repo paths.
- Each theme folder has a CLAUDE.md with its shared rules; each repo has its own CLAUDE.md, `docs/` and memory.
- Shared capabilities are sensors or actuators behind one contract (`~/.claude/docs/fleet/ARCHITECTURE_SENSE_ACT.md`):
  notifications go through TeleFi, news through Augur. Fleet plans: `~/.claude/docs/fleet/` (private).

## 3. Autonomy and blockers
- Loop: next unblocked milestone -> implement with its tests -> run the gate -> commit (conventional
  `feat:`/`fix:`/`chore:`/`docs:`/`refactor:`/`test:`) and push -> repeat. Auto-commit and push unless the repo
  says otherwise. Stage specific files. Never amend a pushed commit.
- The only reasons to stop, always named by class:
  - `credentials-no-agentic-path` (look for an MCP server or CLI first)
  - `irreversible-approval` (schema drop, billing, outreach, data migration, publishing)
  - `repair-budget-exhausted` (retried and cannot converge)
  - `hard-to-reverse-choice`
- Anything reversible: pick a default, log it in the repo's `docs/DECISIONS.md` as `assumed` with a revisit
  trigger, continue. Owner-needed but non-blocking: log as `needs-owner` with severity and urgency, keep going.
- Never pause to ask "continue?", for lint or build noise, or on a tool error you can fix. A workaround is
  labelled as one, with its root-cause hypothesis; confirming that is the next task.
- Off-critical-path improvements go to the backlog; a bug that breaks the critical path is not extra.
- Outward-facing actions (posting, sending, publishing, purchases, Notion writes) need the owner's go per action.
- Review evidence for pre-traffic work is a demo video or a before/after screenshot pair, queued (Catwalk
  Review Queue), never an interrupt.
- Ambiguity that would change a hard-to-reverse design: ask once. Otherwise choose and log.

## 4. Deployment tiers
- Every app declares `deploymentTier:` in its CLAUDE.md (the SessionStart hook shows it).
- `pre-traffic` (no real users or money): ship to prod behind build + test green.
- `live` (real users, payments, PII or irreversible data): doc suite (SPEC / DESIGN / DECISIONS) ->
  adversarial review -> recorded human approval -> deterministic deploy gate. Run it with `/dark-factory`.
  Promote an app to `live` when it gains real users.
- A milestone is done only when its gate is green.

## 5. Build defaults
- File-type rules auto-load from `~/.claude/rules/`; task playbooks (`~/.claude/playbooks/README.md`) are read
  when their cue fires (Notion, reliability, agent dispatch).
- Before creating a component, hook, table, route or script: list the target dir, grep for the role, and state
  "Searched <dir> for <role>: found <X>; extending <X> / none fit because <reason>". Two implementations of
  one role is a defect to consolidate.
- Prefer an existing tool or service over building one, and tools an agent can inspect (CLI/API) over GUI-only.
- Schema first for any non-trivial data shape (zod or pydantic, types derived), validated at boundaries.
- Tests: sanity, one per acceptance criterion, and regression-first when a bug happens; see each fail once.
- No dead code, no magic numbers, error handling only at boundaries, secrets only from env.
- Spec-driven for contracts and money paths; intent-driven for research and spikes.

## 6. Dispatch
- Skill > `/orchestrate` role flow > `cycle` workflow > named agent (implementer, reviewer, researcher, designer,
  architect, security) > general-purpose. Details: `~/.claude/playbooks/agent-dispatch.md`.
- Independent steps run in parallel. Every agent gets a deliverable and a stop condition.
- A manual pattern seen 2-3 times becomes a proposed skill. A blocking gate states its exit condition.

## 7. Session start and docs
- Read the repo's state doc first (the SessionStart hook names it and flags staleness), check it against git,
  then summarize phase, last step and next action.
- One canonical doc per concern. Decisions: `docs/DECISIONS.md`. Session detail: `docs/SESSION_LOG.md` under
  the docs root the SessionStart hook states.
- Repos where agents run concurrently keep an `## Agentic Orchestration Rules` section.
- Anything that produces an artifact also produces a pass/fail check of it (`~/.claude/playbooks/reliability.md`).

## 8. Rules about rules
- A new rule goes in exactly one layer: hook or permission (always/never), output style (answer format), this
  file (needed every session), `~/.claude/rules` (file type), playbook (task), theme CLAUDE.md, repo CLAUDE.md,
  or memory. State the layer when adopting it.
- Memory: fleet-wide notes in the D:/repo memory; project notes in that project's own memory dir.
- Improvement loops: `/self-improve`, `/retrospect`.

## 9. Where things live
| what | where |
|---|---|
| answer format | `~/.claude/output-styles/terse-ledger.md` |
| enforced rules | `~/.claude/hooks/guard.py`, `session_context.py` (tests: `~/.claude/tests/test_guard.py`) |
| file-type rules / task playbooks | `~/.claude/rules/`, `~/.claude/playbooks/` |
| skills, agents, workflows | `~/.claude/skills/`, `~/.claude/agents/`, `~/.claude/workflows/cycle.js` |
| harness standard | `~/.claude/docs/fleet/reports/Agent harness engineering practices.md`, `~/.claude/docs/fleet/HARNESS_AUDIT.md` |
| this folder | `~/.claude` is the public `claudence` repo: commit and push drift; `docs/fleet/` stays private (ignored) |

Sounds on Stop and PermissionRequest are configured globally; never play sounds or change the volume.
