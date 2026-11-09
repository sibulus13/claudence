# Global Claude Code instructions

Facts and pointers for every session. How answers look: output style `terse-ledger`. Rules that must never be
broken are enforced in code (`~/.claude/hooks/guard.py`), not here. Each rule's history:
`~/.claude/docs/CLAUDE-2026-10-25-pre-refactor.md` and `~/.claude/docs/DECISIONS.md`.

## Critical
1. Work autonomously; stop only for a typed blocker (section 3).
2. The author of code is never its only verifier on a live, money or auth path.
3. Commands that may take more than ~30 s run in the background; the main thread stays free.
4. Before saying what exists, what is readable or what is done, check it this turn; memory and a partial view are not evidence.
5. A fix or change is not done until its real path has run once (the actual job, command or page, or a test of it), before returning to the owner. A probe of one part is not that run; never hand the owner a verification you can run yourself.

## 1. Environment
- Windows 11 Pro. Two shells, each in its own syntax: the PowerShell tool (5.1: no `&&`, `?:`, `??`) and the
  Bash tool (Git Bash, POSIX). Forward slashes in code; backslashes only where a Windows API needs them.
- `python` (C:/Python312), never `python3`. pnpm for JS/TS (exception: `SaaS/Workout Gen` uses npm).
  Node 20 is installed; target 22+ for new work.
- Editor VS Code (`code -r -g file:line`). Terminal WezTerm: only absolute drive-letter paths become links.
- Not on PATH: openssl, rg, curl (use `Invoke-RestMethod`). Installed: gh, vercel, pnpm.
- Patch scripts go in a file through the Write tool, not a heredoc (backslashes and quotes break). Never filter a
  failing command's output while diagnosing it.

## 2. Repo layout (D:/repo)
- `D:/repo/<Theme>/<project>`, never bare at the root. Themes:
  - `Finance/` crucible, augur, market-signal-watch
  - `Factory/` foreman -> catwalk, herald (ostler: reference only, idle since 2026-08-24)
  - `SaaS/` cashcow (= Tarive), certify, nuwa, `pylon/*`, Workout Gen (= Ascension)
  - `Assistant/` cortex, groundtruth; `Lib/` telefi, meter; `Life/` personal docs and apps; `web/personal/`;
    `Experiment/`; `_Misc/`; `_Archive/` (index `D:/repo/_Archive/README.md`)
- Legacy `AI/`, `Bot/`, `Data/` and bare `fitbit/` are being emptied (LEDGER roadmap). A new repo goes in a theme
  folder; say which.
- Moving a repo: `/repo-move`. Code derives paths from the repo root, never absolute repo paths.
- Each theme folder has a CLAUDE.md with its shared rules; each repo has its own CLAUDE.md, `docs/` and memory.
- Shared capabilities are sensors or actuators behind one contract (`$FLEET_DOCS/ARCHITECTURE_SENSE_ACT.md`):
  notifications go through TeleFi, news through Augur. Fleet plans: `$FLEET_DOCS` (default `D:/repo/docs`, private repo).

## 3. Autonomy and blockers
- Loop: next unblocked milestone -> design -> spec -> implement with its tests -> refactor -> QA by a fresh reviewer that
  runs the core use cases live (review-and-run) -> run the gate -> commit (conventional
  `feat:`/`fix:`/`chore:`/`docs:`/`refactor:`/`test:`) and push -> repeat. Auto-commit and push unless the repo
  says otherwise. Stage specific files. Never amend a pushed commit.
- A large milestone (a project, service or feature finished) or code going public ends with the refactor
  pass: `~/.claude/playbooks/refactor-pass.md`.
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
- Outward-facing actions (posting, sending, publishing, purchases) need the owner's go per action; Notion writes
  follow `playbooks/notion.md`.
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
- Before creating an agent, persona or skill: check `~/.claude/agents/`, `~/.claude/skills/` and Cortex `agents/`, fold the job into
  one that already holds the role, and state whether an existing agent should split that responsibility out (owner 2026-11-06).
- Decompose and decouple (standing order, 2026-10-31): every service, package or feature has ONE core
  responsibility. Split until it does. Parts talk only through versioned contracts (schema + shared enums +
  state machine), never through each other's internals. Shared capabilities become standalone services with a
  standard external schema (the TeleFi pattern). Project specifics live in a per-project manifest, not in shared code.
- Prefer an existing tool or service over building one, and tools an agent can inspect (CLI/API) over GUI-only.
- A new product, service, platform or large feature starts with `~/.claude/playbooks/product-development.md`: POC on the core use cases before any full spec (owner 2026-11-08).
- Schema first for any non-trivial data shape (zod or pydantic, types derived), validated at boundaries.
- Test-driven: write the failing test before the code (red, then green, then refactor), and see each test fail once.
  Write one behaviour test per acceptance criterion, plus a regression test first when a bug happens.
- Contract tests at every integration boundary: the producer and the consumer both test against the same versioned
  schema and fixtures (e.g. TeleFi `envelope.v1`, the job-lifecycle result schema), so a change breaks the build on
  both sides. Detail: `~/.claude/rules/testing.md`.
- No dead code, no magic numbers, error handling only at boundaries, secrets only from env.
- Every plan or system states time-boxed milestones, known blockers and a review or stop date, so no direction runs open-ended.
- Before anything slow or costly, prove the method on the smallest real sample (the first 5 seconds of a clip, one row, one
  page). A failed sample means change the method, not run it bigger.
- Every subprocess, network call, lock wait and retry loop has a timeout and a bound. On expiry it reports a named
  failure; it never hangs and never silently skips (hooks: `~/.claude/rules/hooks.md`).
- Every feature, fix or build starts from a persistent work item, `<repo>/docs/work/<id>/` (README + layer files,
  `~/.claude/skills/dark-factory/WORK-ITEM-STANDARD.md`): acceptance criteria with pass/fail conditions and a test each.
  Enforced by the git commit-msg hook (pre-commit, `scripts/spec_gate.py`): a source commit on the default branch needs
  a `Spec: docs/work/<id>/README.md` trailer naming a `building`/`shipped` item that passes `scripts/spec_check.py`.
  Research and spikes are exempt until their code is committed.

## 6. Dispatch
- Skill > `/orchestrate` role flow > named agents (researcher, designer, implementer, reviewer) > general-purpose.
  `cycle.js` is suspended, so run its stages by hand. Details: `~/.claude/playbooks/agent-dispatch.md`.
- Hand off only approved, well-specified work, and every hand-off has an independent reviewer; ambiguous work told to
  start stays in the main session.
- Independent steps run in parallel. Every agent gets a deliverable and a stop condition.
- A manual pattern seen 2-3 times becomes a proposed skill. A blocking gate states its exit condition.

## 7. Session start and docs
- Read the repo's state doc first (the SessionStart hook names it and flags staleness), check it against git,
  then summarize phase, last step and next action.
- One canonical doc per concern. Decisions: `docs/DECISIONS.md`. Session detail: `docs/SESSION_LOG.md` under
  the docs root the SessionStart hook states.
- Fleet-wide journal and roadmap: `$FLEET_DOCS/LEDGER.md` (private). Update it with `/ledger` at the end
  of a working session: one row per meaningful change with its why and commit ref.
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
| harness standard | `$FLEET_DOCS/reports/agent-harness-engineering-practices.md`, `$FLEET_DOCS/HARNESS_AUDIT.md` |
| docs, by audience | public harness docs `~/.claude/docs/` (claudence) · private fleet-wide docs `$FLEET_DOCS` = `D:/repo/docs` (own repo: ledger, plans, audits) · one project's docs `<repo>/docs/` · one project's memory `~/.claude/projects/D--repo-<Theme>-<project>/memory/` |
| this folder | `~/.claude` is the public `claudence` repo: commit and push drift; the private fleet docs live outside it, at `$FLEET_DOCS` |

Sounds on Stop and PermissionRequest are configured globally; never play sounds or change the volume.
