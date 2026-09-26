---
name: orchestrate
description: Six named role-flows (feature / bugfix / arch-decision / security-review / go-to-market / hotfix) that sequence real agent personas with structural review gates, and hand multi-component fan-out to the fanout-design-build-audit workflow rather than re-deriving partition/execute logic ad hoc.
version: 2.0.0
---

# orchestrate

Rewritten 2026-09-03 — the previous version (v1.0.0) was a generic, stack-hardcoded
"partition → execute → verify → report" template that never actually implemented the six
named flows `~/.claude/CLAUDE.md`'s Skill-First Dispatch section has described this skill as
having since before this rewrite. It also used `subagent_type="general"` (not a real type —
`general-purpose` is) and told every session "No worktree isolation in this repo," directly
contradicting the global worktree-by-default rule. If you're reading this skill because CLAUDE.md
pointed you here, this version is what actually backs that description now.

## Real building blocks this skill dispatches — nothing here is prose-only

- **Personas**: `~/.claude/agents/{implementer,researcher,reviewer,designer,architect}.md` are real,
  dispatchable subagent types — pass `subagent_type: "implementer"` / `"researcher"` / `"reviewer"` /
  `"designer"` / `"architect"` to the Agent tool (or `agentType` to a `Workflow` script's `agent()`
  calls) and get the real persona file, not a prompt you hand-roll. Planner is covered by the
  built-in `Plan` agent; QA is covered by the `/qa` skill; Questioner/Security/Marketing/Business are
  deferred (see the Agent Personas table in CLAUDE.md for each one's build trigger) — write their
  persona into the prompt text explicitly if a flow below needs one before it's promoted to a file.
- **Multi-component fan-out**: when a flow's work naturally splits into ≥2 independently-testable
  components (separate files/modules, each with its own test boundary), delegate the actual
  build-review-audit-fix mechanics to the saved workflow at
  `~/.claude/workflows/fanout-design-build-audit.js` via
  `Workflow({ scriptPath: "~/.claude/workflows/fanout-design-build-audit.js", args: { repo, pyInterpreter, designDoc, schemasFile, components, maxLoopIterations } })`
  rather than re-implementing partition/execute/verify logic here. That script already encodes the
  Fan-Out Workflow Pre-Flight Checklist (persona/model/effort per stage, determinism pinned,
  independent reviewer mandatory, worktree-by-default) — don't duplicate it.
- **Single-component or non-fan-out work**: dispatch personas directly via the Agent tool in the
  sequence each flow below specifies — no Workflow script needed for a single implementer+reviewer
  pass.

## Pre-flight, every flow, before dispatching anything

1. **Determine the real test/build/typecheck commands from the project itself** — read
   `package.json`/`pytest.ini`/`pyproject.toml`/whatever the repo actually uses. Never assume `pnpm
   test` or any other stack's convention; the previous version of this skill hardcoded pnpm and was
   wrong for every non-JS repo.
2. **Determine the real interpreter/environment** — if a `.venv` or equivalent exists, pin its exact
   path for every agent that needs to run something, per the Fan-Out Checklist's determinism item.
3. **Worktree-by-default** for any stage where ≥2 agents write to the same repo in parallel. State
   the reason if you deliberately skip it for a given stage (e.g. read-only research agents never
   need it).

## The six flows

### feature
Researcher (gather existing patterns/conventions — "reuse before you build," per the
`implementer` persona's own rule) → Designer (interface/schema, no implementation) → Implementer →
Reviewer → QA (`/qa` skill: per-AC-item MET/PARTIAL/FAILED verdict) → Security (deferred persona,
Opus-tier prompt — **only** if the feature touches auth, money, external API exposure, or secret
handling; skip otherwise, don't pad — and this is the trigger to finally promote it to a real file).
Use the fan-out workflow if the feature decomposes into multiple components; a single Agent-tool
dispatch chain is enough for a one-file feature.

### bugfix
Researcher (reproduce the failure as a runnable check — a failing test or a script that reproduces
the exact symptom, never diagnose from logs alone) → Implementer (fix + a regression test proving
it) → Reviewer (adversarial — confirm the root cause was actually fixed, not just the reported
symptom; this is exactly the kind of thing a self-certifying fix misses). No Designer/QA/Security
unless the bug is in one of those surfaces.

### arch-decision
Architect (`~/.claude/agents/architect.md`, ADR format: context → options → decision → rationale).
For a genuinely contested decision with real trade-offs, use a judge-panel pattern instead of one
agent's opinion: dispatch 2-3 independent agents each arguing a different option from first
principles, then a final Architect-persona agent synthesizes given all arguments — cheap insurance
against one framing anchoring the whole decision.

### security-review
Security (prompt-only persona, Opus-tier, OWASP-mapped threat list with severity). For a
broad-surface review, fan out by threat category (auth, data storage, injection, secret handling,
external API exposure) as parallel Security-persona agents, then synthesize findings into one
severity-ranked list — don't let one agent's context window be the only lens across a large attack
surface.

### go-to-market
Marketing (prompt-only persona: copy variants + positioning + ICP mapping) and Business
(prompt-only persona: unit economics + recommendation + stated assumptions) run in parallel — they
answer different questions and neither blocks the other — then synthesize into one deliverable.

### hotfix
The fastest path, but **the Reviewer step is not skippable even here** — self-certification risk is
about a builder's blind spots being invisible to the builder, not about how urgent the fix is.
Implementer (fix, minimal scope, no refactoring while you're in there) → Reviewer (fast adversarial
pass, still a real independent check) → ship. Skip Researcher/Designer/QA/Security unless the
hotfix itself touches one of those surfaces.

## Reporting

Every flow ends with a structured summary, not prose: what was done, each stage's real verdict
(not just "passed"), what's still open, and — if a Reviewer or Security pass found blockers — those
listed explicitly rather than folded into a vague "mostly done."
