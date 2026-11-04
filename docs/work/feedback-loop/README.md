---
id: feedback-loop
type: feature
standard: 3
tier: T2
risk: [contract, enforcement]
status: spec-locked
touches: [harness]
layers: {architecture: none, component: none, functional: none, data: none}
created: "2026-11-03"
owner: harness
---
# Feedback loop: specs keep their history, escaped bugs trace back to the stage that missed them

```mermaid
flowchart TD
  B["bug found: review, after ship or in production"] --> E["escape record: which spec, AC, dimension, stage"]
  E --> A["Amendments row appended to the original spec"]
  A --> S["fold into capability SPEC.md at ship (capability-layer item)"]
  E --> T["tally by stage and cause"]
  T --> P["proposal: probe or adversary checklist line"]
  T --> V["proposal: reviewer check"]
  P --> N["owner harness applies or rejects it"]
  V --> N
  N -. "recurrence after applied reopens" .-> T
```

Companion to `docs/work/agentic-loop/` (split by its 5-milestone limit). Implements decision D43 (owner-confirmed).
Build order across the three specs, the owner of each shared file and the cross-spec contracts:
[INDEX](../../capabilities/INDEX.md).

## Decisions (one-way doors)

| # | Decision | Status | Choice | Alternatives | Why it is hard to reverse |
|---|---|---|---|---|---|
| D-A | History model | **confirmed** (D43) | frozen original, append-only Amendments log (rows `A-n`), folded current view; items opt in by the frontmatter marker `amendments: v1` (FL-3); the fold waits for the capability-layer item | in-place edits (D37) | every spec's format |
| D-G | Where an escape is recorded | **confirmed** (owner 2026-11-03, D45) | on the bug record itself (an `Escape` table), linked to the origin spec's Amendments row | a separate defect database | every bug record and the tally read it |
| D-H | The escape classes | **confirmed** (owner 2026-11-03, D45): one enum, one meaning source | the table below, adapted from IBM's Orthogonal Defect Classification (trigger and stage) | free text | the tally and every agent checklist key on it |

### Escape classes (D-H)

The question for each bug: **which stage should have caught it, and why didn't it?** The enum and each value's
meaning have one source, `contracts/escape-class.v1.json`; this table is a rendering of it, and a test keeps the two
equal (AC-11). The glossary points to the contract instead of restating it.

| Should have caught it | Signal in the origin spec | Cause class | What changes next time |
|---|---|---|---|
| probe | the area's existing spec, code or a known practice was not read | `context-not-loaded` | a probe checklist line for that capability |
| design | no AC and no Outcomes row covered the behaviour, or its level was L1 with a weak reason | `spec-gap` | an adversary question for that dimension |
| design | an Assumptions row held, then broke in reality | `envelope-broke` | the assumption gets a detector |
| implementation | an AC covered it but no test pinned it, or the test was tautological | `test-gap` | a reviewer check plus a mutation target |
| code review | the test existed, the review passed, the behaviour was wrong | `review-miss` | a reviewer check (an eval case waits for an eval harness) |
| final gate | every AC passed but the goal was not met | `goal-miss` | a goal-check question |
| none (production only) | depended on real traffic, data or time | `env-only` | a monitoring signal in Operations |

## Purpose

Bugs found after design are fixed but not traced back: nothing records which spec missed them, at which stage, or
why, so the same class recurs. The retro queue dead-ends (`/retrospect` reads only telemetry) and `/self-improve` has
never logged a run (internal survey). The owner wants every finding appended to the original spec and fed back into
the designer's and implementer's awareness (owner design O-16, O-17; follow-up 2026-11-03).

## Goals and non-goals

- Goal: after lock, a spec's original text is frozen; findings append as classed Amendments rows with ids `A-n`.
- Goal: every bug record names its origin spec and AC (or the missing one), the stage that should have caught it, and
  a cause class.
- Goal: escapes are tallied per origin spec (per capability once the capability-layer item exists) and per stage;
  a recurring class opens a tracked proposal to change a probe or adversary checklist line or a reviewer check.
- Non-goal: a defect database or dashboard (the tally is a generated table); per-team metrics; agent evals (they wait
  for an eval harness); the fold into capability SPEC.md and the probe citation rule (capability-layer item, INDEX).

## Background

- **Orthogonal Defect Classification (ODC)**: classify each defect by what triggered it and which stage let it
  through, so the process, not the person, is fixed.
- **Defect removal efficiency**: the share of defects each stage removes; escapes show which stage underperforms.
- **Blameless postmortem action items**: each has an owner, a tracking item and a closed state, or it is forgotten.
- **Evals from real failures**: a small set of real failures, kept passing, steers an agent better than new rules.

<details>
<summary>Detail and sources</summary>

- ODC: IBM Research (Chillarege et al., 1992); trigger and defect type separate "what found it" from "what was wrong".
- Defect removal efficiency: Capers Jones (2011), design inspection about 87%, unit tests 32-38% on average.
- Postmortems: Google SRE workbook, postmortem culture: action items without a tracking ticket are forgotten.
- Evals: Anthropic (2026-01-09, vendor): start from 20-50 real failures; keep regression evals near 100%.
- Notes: `D:/repo/docs/research_notes/Agentic loop design/web_gates_history.md` (questions 4, 5).

</details>

## Approach

Baseline: today (D37 in-place amendments, bugs fixed without trace-back, a retro queue nobody reads).

| Dimension | A: free-text retro notes | B: recommended (classed escapes on the bug record, tally, tracked proposals) | C: a defect-tracking database |
|---|---|---|---|
| Owner time | 0 | 0 the tally is generated | - another tool to read |
| Agent cost | 0 | - one Escape table per bug | - |
| Recurrence of a class | 0 nothing reads notes | + the next probe and review face the class | + |
| Reversibility | + | + plain files | - data locked in a tool |
| Build complexity | + | - gate rule, tally, checklist wiring | - |

Chosen: **B**.

## Milestones

```mermaid
flowchart TD
  F1["F1 walking skeleton: Amendments log append-only after lock"] --> F2["F2 escape record on bug records"]
  F2 --> F3["F3 tally, tracked proposals, /retrospect reads them"]
```

| Milestone | Slice (what works after it) | Depends on | Owns | Outer test (red first) | Unblocks |
|---|---|---|---|---|---|
| F1 | after lock only `## Amendments` grows: rows have ids `A-n`, a class, finding, source and (fix-now) a test; editing, deleting or reordering a row is refused; a move back to draft lifts the freeze; the marker `amendments: v1` selects this regime | AL-M2 (file order, INDEX) | `scripts/amendments.py`, `scripts/spec_gate.py`, `scripts/spec_v3.py`, `contracts/work-item.v3.json` | AC-1 | D43 in force for marked items; D37 kept for the rest |
| F2 | a bugfix record carries an Escape table naming origin spec, AC or `none`, dimension, stage and class; it appends a row to the origin spec's Amendments | F1 | `scripts/spec_v3.py`, `contracts/work-item.v3.json` | AC-4 | every bug traces back |
| F3 | escapes and hold rows are tallied per origin spec and stage; a class seen twice opens a proposal with an id, a state and the owner `harness`; the tally reports open count and age; `/retrospect` lists open proposals and offers to close them | F2, PM-P1 (effective config) | `scripts/escape_tally.py`, `skills/retrospect/`, `agents/adversary.md`, `agents/designer.md`, `agents/implementer.md`, `agents/reviewer.md` | AC-7 | agents learn from escapes, and the loop closes |

**Deferred: capability-layer** (INDEX; planned, not drafted). It owns the fold of Amendments rows into the capability
SPEC.md at ship (the former AC-2), the per-capability tally key and the rule that a T2 probe cites its capability's
escapes (the former AC-8). Until it exists, nothing checks a fold and the tally keys by origin spec id.

## Contracts

| Name | Version | Schema | Fixtures |
|---|---|---|---|
| Amendments row (id `A-n`) and the frontmatter marker `amendments: v1` | v1 | `contracts/work-item.v3.json` | `contracts/fixtures/amendments-*.md` |
| Escape table | v1 | `contracts/work-item.v3.json` | `contracts/fixtures/escape-*.md` |
| escape classes: enum, meaning, stage, next-time change | v1 | `contracts/escape-class.v1.json` | `contracts/fixtures/escape-class-*.json` |
| escape tally and retro proposal (id `RP-n`, state `open` / `applied` / `rejected`, owner `harness`, target kind, open count and age) | v1 | `contracts/escape-tally.v1.json` | `contracts/fixtures/tally-*.json`, `proposal-*.json` |

## Behaviour

| AC | Traces | Given / when | Pass when | Fail when | Test |
|---|---|---|---|---|---|
| AC-1 | F1, D-A, FL-1 | a locked spec with `amendments: v1`: an edit above `## Amendments`; an edit, deletion or reorder of an existing row; a row with a missing or duplicate `A-n` id, or without class, finding or source; a fix-now row without a test; a well-formed appended row; a `status:` change; an edit after a move back to draft; a write under `evidence/` or `reviews/` | the first four refused by name; the appended row, the status change, the draft edit and the evidence write land | any refusal lands, or a landing case is refused | tests/test_feedback_loop.py |
| AC-3 | F1, compatibility | every item locked without the marker | still judged by D37's rules | its result changes | tests/test_feedback_loop.py |
| AC-4 | F2, D-G | bugfix records: with a full Escape table; without one; naming a spec or AC that does not exist; a class outside the list | the first lands; the others refused by name | otherwise | tests/test_feedback_loop.py |
| AC-5 | F2 | a bugfix whose origin spec is shipped: with the marker; without it | with: its ship appends a row to the origin spec's Amendments with the escape class and a link back; without: the escape stays on the bug record and no row is appended | the marked origin is unchanged, or an unmarked shipped spec is edited | tests/test_feedback_loop.py |
| AC-6 | F2, D-H | each class's signal (no AC; an AC with no pinning test; a broken assumption; a passing wrong test; an unmet goal; production only) | the checker suggests the matching class; a mismatch is a warning, not a refusal | no suggestion is made | tests/test_feedback_loop.py |
| AC-7 | F3, FL-4 | two escapes of one class in one origin spec; a third; the effective config's `fleetDocs` | one proposal `RP-n` in state `open`, owner `harness`, target a probe or adversary checklist line or a reviewer check, is appended to `<fleetDocs>/RETRO-QUEUE.md`; the third adds no duplicate | no proposal, a duplicate, a target outside the three, or a path not taken from the effective config | tests/test_feedback_loop.py |
| AC-9 | F3, FL-4 | `/retrospect` run with a tally holding open and closed proposals | it lists the open ones with id and age and offers to close each as `applied` or `rejected` | it reads only telemetry, or lists a closed one | tests/test_feedback_loop.py |
| AC-10 | docs | agents/designer.md, adversary.md, implementer.md, reviewer.md and SPEC-STANDARD-V3.md | each states its part: read escapes at the probe, append don't edit, classify escapes | a doc contradicts the code | tests/test_feedback_loop.py |
| AC-11 | D-H | `contracts/escape-class.v1.json` and the Escape classes table in this README; a temp copy of the contract with a value added | the table equals the contract; the checker accepts the new value and refuses one absent from the contract | the table drifts, or any code keeps its own list | tests/test_feedback_loop.py |
| AC-12 | F1, FL-3 | the marker: a new item (first commit after F1's ship commit) locked without it; the marker removed past draft; the marker added in place to a locked pre-F1 item; the same item moved `spec-locked` to `draft` with the marker added | the first three refused by name; the draft route lands | any of the first three lands, or the draft route is refused | tests/test_feedback_loop.py |
| AC-13 | F3, FL-4 | a tally with an `applied` proposal and a new escape of its class; a `rejected` one; an `open` one aged 40 days | the `applied` proposal reopens under its id; the rejected stays closed; the tally shows the open count and each open proposal's age | a recurrence after `applied` is silent, or an open proposal's age is missing | tests/test_feedback_loop.py |

## Outcomes

| Dimension | Level | Row or n/a reason | AC |
|---|---|---|---|
| success | L3 | a bug traces to its origin and changes the next probe | AC-5 |
| invalid input | L3 | malformed Amendments rows and Escape tables are refused by name | AC-1 |
| dependency fails | L3 | an origin spec that does not exist is refused | AC-4 |
| timeout | L1 | no clocks, leases or waits in these checks | |
| crash mid-step | L1 | the checker and gate are pure functions over one commit, so a crash refuses that commit | |
| concurrent actor | L3 | two branches appending the same `A-n` collide at merge and are refused | AC-1 |
| duplicate or replay | L3 | a third escape of a class adds to the tally without a duplicate proposal; a recurrence reopens | AC-7 |
| arrival channel | L3 | an item adopts the regime only through the marker and the draft route | AC-12 |
| performance or cost | L1 | the tally is regenerated from files on demand, with no service to run | |
| security | L1 | no secrets, users or permissions are involved in these files | |
| data and compatibility | L3 | items without the marker keep D37's rules | AC-3 |
| operability | L3 | `/retrospect` surfaces open proposals; a stale or reopened one stays visible | AC-13 |

## Assumptions

| Assumption | Observed | If violated |
|---|---|---|
| The retrospect skill can be changed to read more sources | `C:/Users/Michael/.claude/skills/retrospect/SKILL.md:13` | refuse: F3 does not ship until it reads the tally |
| The capability-layer item (INDEX) will own the fold and the per-capability tally | `C:/Users/Michael/.claude/docs/capabilities/INDEX.md:29` | defer: no fold is checked and the tally keys by origin spec id |
| The effective config exposes the fleet-docs path as `fleetDocs`, derived from `fleet_docs_dir()` | `C:/Users/Michael/.claude/scripts/fleet_paths.py:16` | refuse: F3 writes no queue row; proposals stay in the tally |

## Design fix round 1

Fixed (record `reviews/2026-11-03-design-b5450096.md`): FL-1 (F1 cut to the append-only gate, ids `A-n`, AC-1, fold and
AC-8 deferred), FL-2 (freeze scope, AC-1), FL-3 (marker, AC-12, AC-3), FL-4 (proposals, AC-7, AC-9, AC-13). In passing: FL-6, FL-8.

## Probe

[Probe](evidence/probe.md): the owner's follow-up verbatim and the shared critique (agentic-loop, rows O-16 and O-17).
