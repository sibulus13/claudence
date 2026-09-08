---
name: tldr
description: Produce a scannable three-part summary — what was accomplished, what is outstanding and who it waits on, and the one named next action for each. Use when asked for a TL;DR, a status summary, a recap, "where are we", or a handoff. Distinct from the per-turn reply close, which stays two-part.
---

# TL;DR

**Three sections, and the third is the one people actually need.** `Accomplished` says what changed.
`Outstanding` says what has not, **and who it waits on**. `Next` names **one action per outstanding
item** — not a menu.

**Written for someone deciding what to pick up**, not for someone checking what a turn did. That is
the whole difference from a per-turn close, and it is why the three sections stay separate here.

## The one rule that makes it a TL;DR rather than a summary

**Cap it.** Three bullets a section, five at the absolute limit. **A twenty-bullet TL;DR is a status
report wearing a shorter name**, and the reader will skim it exactly as badly as they would have
skimmed the original.

**What gets cut when the cap bites**: anything the reader already knows, anything with no
consequence, and anything that is process rather than outcome. **What never gets cut**: a blocker on
a person, and a claim that turned out to be wrong.

## Shape

Open with **one line of verdict** — the single sentence someone could repeat in a meeting. Then:

```
**TL;DR** — <one-line verdict>

**Accomplished**
- <emoji> **<headline under 110 chars>**
  - <short nested line, only if it changes a decision>

**Outstanding**
- <emoji> **<headline>** — ⛔ you · 🔄 us · 📅 dated · ⬜ nobody
  - <what it blocks, in one short line>

**Next**
- <emoji> **<one named action>** → <the outstanding item it clears>
```

## Rules per section

### Accomplished — outcomes, never activity

| Do | Don't |
|---|---|
| **State what is now true** that was not before | Narrate what was done to make it true |
| **Carry the consequence.** "450k updates, 59% on work nobody touched in a year" | Report the measurement alone — that is inventory, not a finding |
| **Say which epistemic tier**: measured · stated · modelled · assumed | Let a model and a measurement read identically |
| **Name a claim that was WRONG and is now corrected** — this is the highest-value row | Quietly drop a withdrawn claim so the summary reads cleaner |

### Outstanding — every row names its owner

**A blocker with no owner is a complaint.** Tag every row:

| Tag | Meaning | The test |
|---|---|---|
| **⛔ you** | Waiting on the reader — a decision, an access grant, a review | Nothing an agent can do moves it |
| **🔄 us** | Unblocked work not yet done | It could start today |
| **📅 dated** | Waiting on a scheduled event | Name the date, and whether the slot is long enough |
| **⬜ nobody** | Known, deferred deliberately | Say why it waits, or it reads as forgotten |

**A blocker on a person is an unbooked conversation, not a status.** If a row is `⛔ you` and could
be a meeting, say so.

### Next — one action per outstanding row, and it must be an action

| Do | Don't |
|---|---|
| **One named action, and say which outstanding item it clears** | Offer three options and ask which |
| **Order by what unblocks the most**, not chronologically | Order by what is easiest |
| **Say what done looks like** if it is not obvious from the verb | End on "let me know if you want me to continue" |

**A `Next` longer than `Outstanding` means actions were invented.** Every next traces to something
outstanding.

## Style, inherited and non-negotiable

- **A topic emoji leads every bullet** — the summary is scanned, not read. No legend; the emoji
  relates to that bullet's own subject.
- **Headline under 110 characters.** Detail nests as short lines, **never a paragraph wearing a dash**.
- **Lead with the finding, not the label.** The subject of the sentence is what is true and why it
  matters; an identifier trails as a citation.
- **Never a bare identifier.** Say what the thing IS, in three to ten words, on every citation —
  not just the first.
- **Detail belongs in a file. Give the path, not the paragraph.**
- **A caveat appears only if it changes a decision, and it carries its fix on the same line.**

## What never goes in

| Excluded | Why |
|---|---|
| **Tool calls, file counts, "I then read…"** | Process is not outcome. Nobody is deciding based on how it was done |
| **Restating the ask** | They wrote it |
| **Self-assessment** — "comprehensive", "robust", "significant" | Let the finding carry its own weight |
| **Anything with no consequence** | If a bullet has no *so what*, it is inventory |
| **A second version of a point already made** | The cap exists to force this choice |

## The relationship to the per-turn close — they are different surfaces

**Do not merge them, and do not let this skill's shape leak into every reply.**

| | Per-turn close | This skill |
|---|---|---|
| **When** | Every substantive turn, automatically | On request, or at a handoff |
| **Sections** | **Two** — accomplished · remains, where **remains doubles as next** | **Three** — accomplished · outstanding · next |
| **Why the difference** | The reader is checking a turn's result; splitting remains from next would duplicate every row | The reader is choosing what to pick up, so **the thing waiting and the move that clears it are different facts** |
| **Scope** | The turn | The session, the programme, or whatever was asked for |

**If the two ever conflict, the per-turn contract wins for a turn's close and this skill wins when
invoked.** Naming both surfaces is what stops one silently overwriting the other.

## Worked example

**TL;DR** — the commercial case is arguable but not yet a business; one persona choice unblocks the
rest.

**Accomplished**
- 🪜 **The capability is tiered: answer → propose → volunteer**, which restored a cost model a scope
  change had voided
- 👔 **The persona resolved from the sales organisation's own model** — no marketing officer exists in
  it, and the target splits into a champion and an economic buyer
- 📈 **Readiness moved 4 → 6 answered of twenty components** — persona and cost-to-serve both closed

**Outstanding**
- ⛔ **Which of two documented personas the demo and the ROI model are built for** — you
  - Blocks the ROI model, which blocks the price point, which blocks the forecast
- 🔄 **The buyer-side saving is uncomputed** — us
  - Hours per reporting cycle × loaded rate × cycles per year; nothing in the corpus has it
- 📅 **How this gets sold** — 25 August, 25 minutes, and the slot is short for the question set

**Next**
- 🎯 **Name the persona in one line** → clears the persona choice and unblocks the ROI model
- 🧮 **Build the ROI model against that persona's reporting cycle** → clears the buyer-side saving

**Why this example works**: three and three and two, every outstanding row owned, every next traces
to an outstanding row, and the accomplished rows say what is *now true* rather than what was done.

## Scope

**Global.** A three-part summary with owned blockers is desirable in any project, so this lives in
`~/.claude/skills/` rather than in one repo. Project-specific reply contracts still bind their own
repos, and where a project's contract is stricter, it wins inside that project.
