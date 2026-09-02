---
name: workflow-advisor
description: Help a non-technical domain expert document their own (or a colleague's) manual or semi-manual workflow, then produce a before/after flowchart, name the real pain points, and recommend automation options with plain-language trade-offs. Use when someone describes a process they do by hand or with loosely-connected tools and wants to understand where it could improve — no engineering background assumed on their end.
---

# Workflow advisor

**The person being interviewed is the domain expert; you are not.** Your job is to extract an
accurate picture of what they actually do, not to assume what a "typical" version of their
workflow looks like. A workflow reconstructed from a vague summary is wrong in the details that
matter most — which step is the real bottleneck is almost never obvious from the outside.

**Built 2026-09-02 after documenting an outbound-prospecting workflow twice** — the first pass,
built from secondhand notes, got the automation boundaries wrong (attributed a broken step to the
wrong tool). The second pass, from the person's own direct account, corrected it substantially.
That gap is the reason this skill exists: elicit directly, don't reconstruct from a summary.

## 1 · Elicit — ask, don't assume

Ask for, in this order:

1. **The objective** — what is this workflow FOR, in one sentence. Not "what does it do" but
   "what outcome does doing it well produce."
2. **The value metric** — what does success actually look like to THIS person? Push past a
   generic answer. Volume? Speed? Quality/accuracy? Cost? A "numbers game" (more attempts at a
   given success rate beats fewer, higher-effort attempts) is a genuinely different optimization
   target than "get each one exactly right" — ask which one fits before recommending anything,
   because the right lever to pull depends on it.
3. **The step-by-step walkthrough** — "what do you do first, then what, then what" — not a
   summary. Get concrete enough to know, per step, whether it's fully automated, fully manual, or
   tool-assisted-but-still-requires-a-person.
4. **Explicitly ask which parts are already automated vs. hand-done**, per step. **If a step's
   status is unclear even to them, write it down as unclear — do not guess or invent a plausible
   mechanism.** An honestly-flagged gap is more useful than a confident wrong answer, and it tells
   you exactly what to ask about next.

**Do not accept a first-pass answer as final if anything sounds like a paraphrase of a summary
someone else gave you, rather than the person's own direct account.** If you're working from
notes taken by someone other than the domain expert, treat them as a lead to verify with the
person directly, not as ground truth — the same discipline as sourcing any other claim.

## 2 · Reconstruct three states, not one

- **Fully-manual baseline** — what it would take with zero tooling at all. This is the reference
  point every time-saved estimate is measured against; it does not need its own diagram, just a
  one-line description of the floor.
- **Current state** — what's actually happening today, including every manual handoff, copy-paste,
  and "sits until reviewed" hold. **Name manual steps as manual even when they're a deliberate
  quality gate, not just when they're an accident of missing tooling** — a human review step that
  exists on purpose is a different kind of finding than a step that's manual because nobody built
  the integration.
- **Potential future state(s)** — one or more independent LEVERS, each naming what specific gap it
  closes and its trade-off. **Never present a single "fully automated" target as the obvious
  answer.** A step that's manual by deliberate choice (quality control, personalization, legal
  review) trades capacity for something real — automating it away is a decision for the domain
  expert to make, not a default you apply.

## 3 · Flowchart each state

Mermaid `flowchart TD`, manual steps visually distinguished (bold label, a `⚠️`/`❌` marker, or a
separate shape) from automated ones. Keep rows short — a diagram that needs horizontal scrolling
to read has failed its own purpose for a non-technical reader. An unclear step gets its own node,
marked `❓`, rather than being smoothed over or omitted.

## 4 · Name pain points, tied to WHERE the manual/automated boundary sits

For each manual or broken step: is it manual because (a) nobody built the connection, (b) the
connection exists but is unreliable, (c) it's a deliberate human checkpoint, or (d) it's genuinely
unclear even to the domain expert? These are four different findings with four different fixes —
collapsing them into one "this step is manual" line loses the information that decides what to do
about it.

## 5 · Time/value saved — estimate honestly, frame to the real objective

**Never present an invented number as measured fact.** Label every estimate `⚠️ UNCONFIRMED —
placeholder, pending real timing data` and say so again next to the actual figures, not just once
at the top. If the value metric from step 1 is throughput/capacity ("a numbers game") rather than
per-task time, frame the estimate around CAPACITY — how much more volume becomes sustainable — not
naive minutes-saved-per-task, which understates the real value when the bottleneck is a person's
own review pace rather than task duration.

## 6 · Recommend alternatives, with honest trade-offs, in plain language

- No jargon. A comparison table beats prose for this.
- **State what each option costs the person, not just what it saves.** "Removes the review step"
  is a cost (quality risk) as often as it's a win.
- **Recommend a build order, reasoned from the stated objective** — not just a list of options.
  Free removals of mechanical friction (no quality trade-off) generally come before anything that
  trades a deliberate control away, so the domain expert can judge the remaining bottleneck with
  the easy wins already banked.

## 7 · Output format — default to a document, publish only if asked

Default: a markdown document the person can keep, hand to an engineer, or revisit. **Offer a
published Artifact only when the person wants something shareable or interactive** — check
whether it passes the SHARED-and-VISUAL bar before publishing (see the `artifact-design` skill);
a wall of text does not become an artifact just because it has a diagram in it.

## What this skill does not do

- **Does not implement the automation.** This produces the map and the recommendation; building
  the fix is separate, follow-on work.
- **Does not assume full automation is the answer.** Some manual steps are deliberate controls.
- **Does not fabricate numbers.** An unconfirmed estimate stays labeled unconfirmed everywhere it
  appears, not just where it's first introduced.
