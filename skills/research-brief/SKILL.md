---
name: research-brief
description: Brief a research or web-search agent so every question comes back with an explicit status — FOUND, CONVERGED, CONTESTED, WITHHELD, EMPTY or ERROR — never a plausible narrative with silent gaps. Use before dispatching any agent whose job is to find things out.
---

# Briefing research

**Six research agents were dispatched in one session with hand-written contracts, and the
contracts drifted.** Two returned findings that quietly contradicted each other; one answered
five of eight questions and the gap was invisible because the prose read complete. **This exists
so the contract is written once.**

## The persona question, answered

**`Researcher` at the cheap tier is for retrieval with NO judgement** — find the file, list the
symbols, extract the values. **Most "research" is not that.** Deciding whether a library fits a
constraint, whether two sources actually agree, whether a benchmark transfers to our schema —
that is judgement, and it is a **Designer** or **Reviewer**, not a Researcher.

| The work | Persona | Tier |
|---|---|---|
| Find, extract, enumerate — the answer is on a page | **Researcher** | cheap |
| **Assess fit against stated constraints; recommend and reject** | **Designer** | mid |
| **Adjudicate contested sources; refute a claim** | **Reviewer, adversarial mandate** | mid |
| Structural trade-off where the choice is costly to undo | **Architect** | top |

**Naming the persona in the prompt is not the allocation** — the model argument is. A persona
named but not allocated inherits the session model, which is how expensive work gets done
cheaply and cheap work expensively.

## Every question carries a status, and a report missing one is incomplete

**This is the whole point.** A research report is not prose — it is a set of questions, each
resolved to exactly one state. **The failure mode it prevents: an agent answers the easy
questions well, the hard one briefly, and the reader cannot tell which was which** because
fluent prose covers both identically.

| Status | Means | The trap it prevents |
|---|---|---|
| **`FOUND`** | Answered, with a citable source | — |
| **`CONVERGED`** | **Several INDEPENDENT sources agree.** Independence stated, not assumed | Three blogs quoting one paper reported as three sources |
| **`CONTESTED`** | **Sources genuinely disagree** — report the disagreement, do not pick a winner silently | The single most valuable status, and the one agents avoid because it looks like failure |
| **`WITHHELD`** | Found, but the agent judges it unreliable or inapplicable, **and says why** | A weak source laundered into a strong claim by omitting the doubt |
| **`EMPTY`** | **Searched properly; nothing exists.** A FINDING, not a failure | Absence reported as though never asked |
| **`ERROR`** | Could not search — blocked, rate-limited, no access | A gap that reads as an answer |

**`CONTESTED` and `EMPTY` are successes.** An agent that never returns them is not thorough, it
is agreeable — and agreeableness in a research agent is indistinguishable from fabrication at
reading time.

## Every claim is marked, every time

| Mark | Means |
|---|---|
| **`DOCUMENTED`** | Primary source, with a link or quote |
| **`ASSERTED`** | Widely repeated, **not measured** — say so |
| **`INFERENCE`** | The agent's own reasoning, not anyone's claim |

**A claim marked `INFERENCE` may not enter a decision register as `assumed` — it enters as
`contested`.** Observed 2026-08-19: a survey rejected three tools by *extending a rule measured
on a fourth*, marked it `INFERENCE` honestly, and the verdict was still recorded as settled —
where it read as measured a day later. **The mark has to survive the transcription, or marking
was theatre.**

**An unmarked claim is treated as fabricated.** This is not paranoia: a measured claim and an
inferred one read identically six weeks later, and the second gets cited as the first.

## The brief's required shape

```
PERSONA: <persona>. <one line on the mode of thought>

CONTRACT: <what it owes back, in one sentence — recommend, do not enumerate>

<the problem, concretely — including what makes it HARD, so candidates are judged
 against real constraints rather than described>

QUESTIONS: numbered, each answerable, each getting a status

CONSTRAINTS: read-only unless stated · what may not leave the network · licence limits

DONE WHEN: every numbered question carries one status; every claim carries one mark;
           rejections are named with reasons, not omitted
```

## Rules that keep a report honest

- **Ask for rejections, not just recommendations.** A report that names only what to adopt has
  hidden its reasoning — the rejected candidates are where the constraints show.
- **Say "keep what you have" is an allowed answer**, explicitly, or you will get a
  recommendation to adopt something every time.
- **Ask for the trigger that changes the decision later.** A recommendation with no revisit
  condition becomes permanent by default.
- **Never let an agent certify its own load-bearing finding.** Re-verify it directly, or send a
  second agent with an adversarial mandate. **One did claim something structural today that was
  true — and it was still re-checked before being recorded, which is the only reason it counts.**
- **A finding that changes the shape of the work outranks the question asked.** Say so in the
  brief, or the agent will bury it under the numbered answers.
