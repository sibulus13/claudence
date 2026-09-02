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

**Ask whether any tool in the current pipeline has a second purpose beyond the one being
discussed.** Found 2026-09-02: a "just a cron job" data source turned out to also be the team's
shared leaderboard for gamification. A lever that would silently remove or bypass a tool's visible
front-end can look like a clean automation win while actually deleting something the team values —
name the tool's full role before proposing to route around it.

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

**In the markdown copy**, Mermaid `flowchart TD` — manual steps visually distinguished (bold
label, a `⚠️`/`❌` marker, or a separate shape) from automated ones. Keep rows short — a diagram
that needs horizontal scrolling to read has failed its own purpose for a non-technical reader. An
unclear step gets its own node, marked `❓`, rather than being smoothed over or omitted.

**In the Artifact, never build the flow as Mermaid text inserted by the page's own JavaScript.**
Found 2026-09-02: the Artifact host's Mermaid conversion is a publish-time pass over the static
source HTML — a `<pre class="mermaid">` element the page's own `<script>` creates at runtime via
`document.createElement`/`appendChild` is invisible to that pass and never renders, so the diagram
silently doesn't show up at all. `template.html`'s flow diagram is hand-built instead (status-tinted
cards + a connector, driven from the same `steps[]` array that feeds the detail table) — reliable,
and it needs no library. Reuse that renderer; do not reintroduce Mermaid inside an Artifact's script.

## 4 · Name pain points, tied to WHERE the manual/automated boundary sits

For each manual or broken step: is it manual because (a) nobody built the connection, (b) the
connection exists but is unreliable, (c) it's a deliberate human checkpoint, or (d) it's genuinely
unclear even to the domain expert? These are four different findings with four different fixes —
collapsing them into one "this step is manual" line loses the information that decides what to do
about it.

## 5 · Time/value saved — estimate honestly, frame to the real objective, then make it cyclical

**Never present an invented number as measured fact.** Label every estimate `⚠️ UNCONFIRMED —
placeholder, pending real timing data` and say so again next to the actual figures, not just once
at the top. If the value metric from step 1 is throughput/capacity ("a numbers game") rather than
per-task time, frame the estimate around CAPACITY — how much more volume becomes sustainable — not
naive minutes-saved-per-task, which understates the real value when the bottleneck is a person's
own review pace rather than task duration.

**Always add a cyclical (weekly, or monthly if the cadence is longer) aggregate on top of the
per-step estimate — this is a standing requirement, not optional polish.** A per-task number
doesn't tell a reviewer what a month actually looks like. Build it as a **parametrized model, not
fixed numbers**: name each input as its own row (volume per cycle, minutes saved per unit for each
lever), state its default as a labeled assumption, give the formula that combines them, then show
the computed total at the defaults. The reviewer or the domain expert should be able to change one
number and get a different, honest total — never a total they can only accept or reject whole.

**Give it two modes, not one — a headline total AND a per-stage breakdown.** A single aggregate
number tells the reviewer THAT time is being lost; it doesn't tell them WHERE. Found 2026-09-02:
"where the actual pain point is happening" needs one input per pipeline stage (from the same
`steps[]` used for the flow diagram), each multiplied by the shared volume-per-cycle input, so the
biggest bar is visible at a glance — not just a lever-level sum. Build both a **Simple** mode (one
input per lever, one total — a fast gut-check) and a **Detailed** mode (one input per stage, a
proportional bar per row) behind a toggle, sharing the same volume input. `template.html`'s
calculator already implements this shape; fill in `calculator.simple` and `calculator.detailed`
rather than inventing a new structure.

## 6 · Recommend alternatives — research first, then compare, then order

**Before recommending, research what actually exists** — this is a required step, not
background colour:
1. **Check whether it's buildable as a Claude skill or workflow FIRST, before pricing anything
   out.** This is the standing default ordering, added 2026-09-02: if the task is bounded (a
   single connection, a single transformation, something an already-connected MCP tool could do
   on a schedule) a reusable skill/workflow is usually cheaper than a subscription and gives the
   domain expert something they own outright. Only fall back to a purchased tool when the task
   needs infrastructure a skill can't reasonably provide — a persistent server, a complex OAuth
   flow, heavy data volume, or a UI the domain expert needs day-to-day that isn't a chat interface.
2. **Check what's already available next**: already-installed/authenticated connectors or
   integrations, an existing subscription that already covers this, a native feature of a tool
   already in use. Free or near-free beats anything requiring a new purchase.
3. **Then research what could be adopted**: real products, with real (dated, sourced) pricing —
   never an invented number. Note when pricing is quote-based or a lead rather than a locked
   figure.
4. **Map every candidate to the specific named pain point (from step 4) it closes, and record
   whether it's buildable** — a tool that would replace the whole pipeline is a different kind of
   recommendation than one that closes a single gap, and a purchased platform that also happens to
   be buildable in-house cheaper is worth flagging even when the vendor still gets listed. The
   comparison table needs a `buildable` column, not just cost/trade-off/status.

- No jargon. A comparison table beats prose for this.
- **State what each option costs the person, not just what it saves.** "Removes the review step"
  is a cost (quality risk) as often as it's a win. A subscription's dollar cost is not the only
  cost — note implementation effort, a new vendor to manage, or unconfirmed technical feasibility.
- **Recommend a build order, reasoned from the stated objective** — not just a list of options.
  Free removals of mechanical friction (no quality trade-off) generally come before anything that
  trades a deliberate control away, so the domain expert can judge the remaining bottleneck with
  the easy wins already banked.

## 7 · Output format — default to a published Artifact for a non-technical audience

**A plain markdown file is not a safe default here.** The whole point of this skill is a
non-technical domain expert; most non-technical readers have no Mermaid-rendering markdown
viewer, so a diagram that renders perfectly in this repo renders as raw fence syntax for the
person it was written for. **Default to publishing an Artifact** (see the `artifact-design`
skill) whenever the intended reader is the domain expert themselves or anyone they'd hand this
to — reserve a markdown-only output for a technical audience (an engineer, a repo) who will read
it in a renderer that already handles Mermaid. **Always also keep the markdown version in the
repo** — it's the durable, diffable record and the source the Artifact's content is drawn from;
the Artifact is the reading copy, not a replacement for it.

## 8 · Artifact architecture — reuse the existing template, don't reach for a framework

**`template.html` in this skill's own folder is the reusable base — copy it, fill in its `CONFIG`
and `DATA` objects with this workflow's real content, and publish that.** It follows the same
zero-dependency, hue-driven-token pattern as `skills/depth-tree/template.html`: one file, no
build step, data and presentation cleanly separated by construction (nothing above its `<script>`
tag needs to change for a new workflow). Mermaid diagrams render natively in the Artifact host —
write plain Mermaid syntax into the `mermaid` field, do not load a Mermaid library.

**On React, Tailwind, and shadcn — decided 2026-09-02, after a real frustration report** (editing
a previously-published Artifact was slow because its data was interleaved into its markup and
styling, making an edit hard to locate):

| | Decision | Why |
|---|---|---|
| **shadcn/ui** | **Refused, categorically.** | It's a copy-paste source-component system that assumes a real project with a build pipeline (TypeScript compile, path aliases, bundled Radix primitives). The Artifact sandbox is static HTML plus a small CDN allowlist with no bundler — shadcn cannot run there at all, not just "isn't worth it" |
| **React (CDN UMD build)** | **Conditional, not default.** Use only when a workflow genuinely needs multi-view state that plain event listeners can't hold cleanly | This skill's own content — a few Mermaid diagrams, cards, a table, and a handful of number inputs recomputing a total — is well within vanilla JS. Reaching for React here would be solving a problem this content doesn't have |
| **Tailwind (Play CDN)** | **Not needed here.** | The token-based CSS custom-property system already in `template.html` gives theme-aware styling with zero extra load; Tailwind adds a class-authoring convenience this template doesn't need |
| **The actual fix for the original frustration** | **Structural separation, already solved by the template pattern** — `CONFIG`/`DATA` at the bottom, rendering engine above, exactly like `depth-tree` | The slow-edit problem was never "we need a framework" — it was "the data lived inside the styling." A template with the two cleanly separated fixes that without adding a dependency |

## 9 · Packaging and measuring, once a workflow proves out

**Researched 2026-09-02 against current Anthropic documentation — verify again before relying on
this, since platform capabilities change.**

**Org-wide distribution is possible, but never automatic.** If a workflow built for one person
should become a standard, shared capability:
- Any tier: a private plugin marketplace (a `marketplace.json` git repo) or a direct GitHub-repo
  reference — each team member still adds it once to their own `.claude/settings.json`.
- Team/Enterprise only: **managed settings** push a skill/plugin to every seat with no per-user
  step — this is the actual "standardized package" mechanism, not a copy-paste.
- **Published claude.ai Artifacts do NOT auto-share to an org, at any tier.** Team/Enterprise adds
  "everyone in org" as a possible recipient in the share menu, but every artifact still needs a
  human to open that menu and choose it — there is no bulk API and no default-visible setting. Say
  this plainly rather than implying a toggle exists.

**Usage telemetry exists at the adoption level, not the effectiveness level — say what's missing,
don't imply more than what's there.** An Enterprise-tier Analytics API reports per-skill adoption
(sessions, user counts, ~1-day lag) and per-user activity (sessions, cost) — Team gets a coarser
usage/cost dashboard, no skill-level breakdown. **Neither tier exposes conversation content or a
repeated-task signal** (e.g. detecting that a user re-opened work on a similarly-named task,
which would suggest the first attempt didn't fully land) — that gap is real, not a configuration
you're missing. Local `~/.claude/telemetry/` is per-user only and never visible to an org. When a
domain expert or their manager asks for this, report the adoption-count capability honestly and
name the effectiveness-tracking gap rather than proposing a workaround that reads conversation
transcripts — no such access exists at any tier.

## What this skill does not do

- **Does not implement the automation.** This produces the map and the recommendation; building
  the fix is separate, follow-on work.
- **Does not assume full automation is the answer.** Some manual steps are deliberate controls.
- **Does not fabricate numbers.** An unconfirmed estimate stays labeled unconfirmed everywhere it
  appears, not just where it's first introduced — including every input in the cyclical model.
- **Does not reach for React/shadcn by default.** See § 8 — the template pattern is the default
  and a framework is the exception, not the other way around.
- **Does not claim org-wide artifact sharing or conversation-history-based effectiveness tracking
  exist.** See § 9 — both are real gaps in the current platform, not this skill's oversight.
