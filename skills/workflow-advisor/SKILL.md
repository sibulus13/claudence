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

## 1 · Open as a consultation session — gather context before analyzing anything

**Frame the opening explicitly as a consultation, not a form.** The goal of this phase is to
leave with enough to build both diagrams (current and proposed) and a real efficiency metric —
not to rush to recommendations. Ask for, in this order:

1. **The objective** — what is this workflow FOR, in one sentence. Not "what does it do" but
   "what outcome does doing it well produce."
2. **The value metric(s)** — what does success actually look like to THIS person? Push past a
   generic answer. Volume? Speed? Quality/accuracy? Cost? A "numbers game" (more attempts at a
   given success rate beats fewer, higher-effort attempts) is a genuinely different optimization
   target than "get each one exactly right." **Ask for a metric at each pipeline stage if the
   person can name one, or at minimum one end-to-end metric** — this is what makes the eventual
   recommendation verifiable later, not just plausible now: without a metric plugged in somewhere,
   there's no way to check afterward whether a lever actually helped.
3. **Current time and resource cost** — how long each stage takes today, and what it costs
   (a person's time, a subscription, a vendor). This is the raw material for the capacity
   calculator (§5) — get it as concretely as the person can give it, and label anything they can't
   pin down as unconfirmed rather than guessing on their behalf.
4. **The exact current workflow, step by step** — "what do you do first, then what, then what" —
   not a summary. Get concrete enough to know, per step, whether it's fully automated, fully
   manual, or tool-assisted-but-still-requires-a-person. This is the raw material for the current
   half of the pipeline diagram (§2–3).
4a. **Explicitly ask, and verify from the transcript independent of how it was narrated: is this
    actually linear, or does it fan out, fan in, loop, or draw from multiple concurrent sources?**
    Do not accept a flat "first, then, then" account as the final shape — ask directly: "does
    anything here run in parallel, get triggered by more than one source, feed back into an
    earlier step, or converge from two paths into one?" A transcript's narrative order reads as
    linear even when the underlying process isn't (found 2026-09-02: a workflow was first modeled
    as a flat step list and only revealed its real fan-in/fan-out on a second, deliberately
    structural re-read, prompted by a direct question, not by anything this elicitation asked).
    Run this check **before** building the §2 pipeline — catching it after the fact means the
    elicitation phase failed to ask the right question the first time.
5. **Explicitly ask which parts are already automated vs. hand-done**, per step. **If a step's
   status is unclear even to them, write it down as unclear — do not guess or invent a plausible
   mechanism.** An honestly-flagged gap is more useful than a confident wrong answer, and it tells
   you exactly what to ask about next.
6. **Ask for existing references or knowledge bases to plug into** — prior meeting notes,
   transcripts, internal docs, a knowledge base, anything already written about this workflow.
   Don't wait for the person to volunteer this; ask directly, then go verify it yourself (below)
   rather than taking their recollection of a document as the document.

**Do not accept a first-pass answer as final if anything sounds like a paraphrase of a summary
someone else gave you, rather than the person's own direct account.** If you're working from
notes taken by someone other than the domain expert, treat them as a lead to verify with the
person directly, not as ground truth — the same discipline as sourcing any other claim.

**Before treating a relayed account as settled, go find and read the source conversation's own
notes or transcript — don't wait to be handed a link.** If the workflow traces back to a named
meeting, search for it and cross-reference every claim against it, rather than building solely on
what was paraphrased secondhand.

**Where a Gemini-generated meeting transcript actually lives, corrected 2026-09-02 after checking
the wrong place first**: at this org, a Gemini transcript is a **Google Doc, one per meeting,
linked from that meeting's own Calendar event** — it is NOT reliably reachable through Notion's
Meeting Notes feature (that tool separately requires a Notion Business-plan workspace, which this
one doesn't have, and even where it's available it may not index a Drive-native doc). Search
**Google Drive first** for the meeting's own title (`search_files`, `fullText contains` or
`title contains` the meeting name) — the doc contains both a Gemini-generated Notes/Summary
section and a full timestamped Transcript section in one file. Only fall back to Notion's general
workspace/semantic search, or a personal daily-log entry written around the same conversation, if
Drive search comes up empty — and label whichever source you actually used: a full transcript is
primary-source strength, a paraphrased note is secondary and should be flagged as such, not
presented with the same confidence.

**Disambiguate candidates by title, attendees, and timeline — never grab the first hit.** A
`search_files`/`list_recent_files` call on "Notes by Gemini" returns every recent meeting, not just
the one being asked about. Narrow to the right one, in this order: (1) **title** — does it name the
right people or subject; (2) **attendees** — the doc's own "Invited" line (or, for a 1:1, the doc
owner) must include the domain expert being interviewed; (3) **timeline** — `createdTime` must land
on the day the meeting is claimed to have happened. **A stated "today" is a lead, not a fact** — a
Calendar/Drive search run before the transcript was shared can correctly find nothing yet
(observed 2026-09-02: a 1:1 owned by the interviewee wasn't shared to the interviewer's Drive until
~7 hours after the meeting ended) — re-search rather than concluding the meeting didn't happen.

**If disambiguation still can't settle it — nothing found, or two candidates tie — stop and ask the
user for the meeting note/transcript URL directly, as a prerequisite, rather than guessing or
drafting from the wrong source.** Owner instruction, 2026-09-02: proceeding on an unconfirmed match
risks building the whole document on someone else's meeting.

**A primary-source transcript is worth re-reading even after a document already exists** — it
routinely contains material corrections a relayed summary smoothed over (a step attributed to the
wrong cause, an open question that was actually answered mid-meeting, a stated team priority that
contradicts the document's own recommended order). Read the whole thing, not just the parts that
seem relevant on a first pass — the "not a huge workflow challenge" aside that reorders two levers
did not appear in this skill's own summary section, only in the raw transcript.

**When the source notes mention something outside the current workflow's scope** (a different
person's process, an unrelated observation), **flag it rather than fold it in** — note it for a
later, separate elicitation pass instead of stretching this document to cover it.

**Ask whether any tool in the current pipeline has a second purpose beyond the one being
discussed.** Found 2026-09-02: a "just a cron job" data source turned out to also be the team's
shared leaderboard for gamification. A lever that would silently remove or bypass a tool's visible
front-end can look like a clean automation win while actually deleting something the team values —
name the tool's full role before proposing to route around it.

## 2 · Reconstruct current → future as ONE pipeline, not separate states

**Restructured 2026-09-02, consultancy-style** — a reviewer reads current-state and proposed-state
side by side, not as three things to click through. Reconstruct:

- **Fully-manual baseline** — what it would take with zero tooling at all. Reference point every
  time-saved estimate is measured against; it never gets its own walkthrough, just a one-line
  caption ("Reference — fully manual: ...").
- **The current pipeline, in actual sequence** — every manual handoff, copy-paste, and "sits until
  reviewed" hold, in the order they happen. **Name manual steps as manual even when they're a
  deliberate quality gate, not just when they're an accident of missing tooling** — a human review
  step that exists on purpose is a different finding than a step that's manual because nobody
  built the integration.
- **For each step a lever touches, what replaces it — attached to that step, not a separate
  section.** A step either passes through unchanged, or the diagram shows inline what replaces it:
  a single swap (one step → one tool) or a consolidation (several steps → one tool). **Never
  present a single "fully automated" target as the obvious answer** — a step manual by deliberate
  choice (quality control, personalization, legal review) trades capacity for something real, and
  automating it away is the domain expert's decision, not a default you apply.

## 3 · One flow, current extending into future

**In the markdown copy**, a single ordered table or list — one row per pipeline step, in sequence,
with a "Becomes (if a lever applies)" column naming what replaces it inline. Keep it scannable — a
table that needs horizontal scrolling has failed its own purpose for a non-technical reader. An
unclear step gets its own row, marked `❓`, rather than being smoothed over or omitted.

**In the Artifact, one linear flow — never two side-by-side current/future panels, and never
Mermaid.** Two reasons, both found the hard way:
- A two-column current/future grid needs pixel-alignment between variable-height cards, which is
  exactly the class of drift bug that has already hit a different Artifact in this account
  (position-synced sections drifting on variable content height). A single linear flow has no
  alignment to keep in sync.
- Found 2026-09-02: the Artifact host's Mermaid conversion is a publish-time pass over the static
  source HTML — a `<pre class="mermaid">` element the page's own `<script>` creates at runtime via
  `document.createElement`/`appendChild` is invisible to that pass and never renders.

`template.html`'s flow is hand-built from a single `pipeline[]` array — each entry is `unchanged`,
`replaced` (one step → one tool), or `consolidated` (several steps → one tool), driven by the same
status-hue tokens as the pain-point cards. Reuse that renderer; fill in `pipeline[]`, do not invent
a new shape and do not reintroduce Mermaid inside an Artifact's script.

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
`pipeline[]` used for the flow), each multiplied by the shared volume-per-cycle input, so the
biggest bar is visible at a glance — not just a lever-level sum. Build both a **Simple** mode (one
input per lever, one total — a fast gut-check) and a **Detailed** mode (one input per stage, a
proportional bar per row) behind a toggle, sharing the same volume input. `template.html`'s
calculator already implements this shape; fill in `calculator.simple` and `calculator.detailed`
rather than inventing a new structure.

**Every assumption declares whether it scales with volume — never assume it does.** Found
2026-09-02 by adversarial review: a one-time-per-cycle cost (copying a whole prospect list in a
single paste, done once per week regardless of how many prospects are in it) was silently treated
as a per-prospect cost and multiplied by volume, overstating that lever's weekly contribution by
roughly 20x in a number that was already live in a published Artifact. Before entering a default,
ask **"if volume doubled, would this actually take about twice as long?"** — a batch action
usually doesn't. `template.html`'s calculator requires `perProspect: true|false` on every
assumption and stage for exactly this reason; `false` means the value is already a per-week total
and must NOT be multiplied by the volume input.

**Prefer a sourced volume default over a round-number guess.** Found 2026-09-02: the source
conversation's own notes ("Replit runs once a week, finds 10 signals") gave a real basis for the
prospects-per-week input, replacing an earlier unsourced round number that had been carrying the
whole calculator. A sourced estimate is still unconfirmed and still gets the same warning label —
but it is a materially better placeholder than an arbitrary one, and § 1's meeting-notes check is
exactly where this kind of number turns up.

## 6 · Recommend alternatives — four phases, not one research pass

**Owner instruction, 2026-09-02, after the first Jamie draft came back too shallow**: tool
research had collapsed into "recap what the domain expert already named in the meeting," which is
not research — it's a transcript summary wearing a tools section. **Four phases, in order, each
with its own deliverable — do not skip from Phase 1 straight to a tools table:**

| Phase | Deliverable | Where it lives |
|---|---|---|
| **1 · Understand** | The current pipeline + named pain points, each tagged by cause | §1–4 above |
| **2 · Research, wide** | Every named gap grouped into capability SEGMENTS, each segment researched independently and broadly — not just the tools the domain expert already mentioned | New requirement below |
| **3 · Consolidate** | A trade-off analysis per segment, THEN filtered against this specific person's context (role, experience, stated capability) — two separate filters, not one | Extends the tiering below |
| **4 · Escalate or self-serve** | One explicit, capability-reasoned verdict per lever: can THIS person self-build/self-discover this, or does it need a technical hand-off | §10, amended |

**Phase 2 — research wide, by segment, independent of what was already said.** Before any tool
list: group the open gaps into capability segments (e.g. "signal-finding/discovery" and
"structured research-note generation" are two different segments, not one "automation" bucket),
then research EACH segment on its own — real web/vendor research, not a recap of whatever tools
the domain expert or a colleague happened to name in conversation. **A tools section built only
from names already in the transcript has not researched anything — it has transcribed.** Cast the
net wide enough that a genuinely better, previously-unmentioned option has a chance to surface;
narrow to a shortlist only in Phase 3, not before.

**Phase 3 — two filters, applied in order, not one.** First, a trade-off analysis per segment
(cost, effort, quality risk, maturity — the tiering below). Second, and separately: **filter
against this specific person's context** — their stated experience level, their role, how they
described their own relationship to the tooling (a self-reported "I haven't touched agentic AI
yet" is load-bearing context, not colour). The same trade-off table can point to a different top
pick for two different people if their capability differs — that's the filter doing its job, not
an inconsistency to resolve away.

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
4. **Map every candidate to the specific named pain point (from step 4) it closes, and classify
   it into exactly one of three tiers, alongside the free-text buildable reasoning from point 1**
   — added 2026-09-02, because a non-technical stakeholder deciding between options needs a
   category to scan first, not a paragraph to parse per row. The tier is the forced choice; the
   free-text field still carries the reasoning behind it:
   - **Build** — a Claude skill/workflow, no new subscription. The default first move for a
     bounded task (see point 1).
   - **Middle ground** — an existing native connector, or a lightweight integration platform
     (Make.com/Power-Automate-class), that needs enabling or a small subscription but isn't a full
     platform. Most "worth adopting" recommendations land here.
   - **Buy** — a full third-party platform. Reserve for when the gap is genuinely platform-sized,
     not just because a vendor sells one — a platform that would also replace parts already working
     fine is a cost, not a convenience.
5. **Tag every candidate `maturity: aspirational | now | done`, independent of its tier** — added
   2026-09-02, extended to three values the same day after a domain expert reported one graduating
   mid-conversation. Tier answers "what kind of thing is this"; maturity answers "how real is it
   right now": `aspirational` depends on something not yet true (a beta, an unconfirmed
   integration, access not yet granted); `now` is feasible today but not yet tried; `done` means
   someone actually reported it deployed and working — never assign `done` on your own inference,
   only on the domain expert's word. A Build candidate can be aspirational and a Middle-ground
   candidate can be `done` (an already-live connector) — the axes are genuinely independent, and
   conflating them is how an idealized bet gets presented with the same confidence as a working
   option. **Re-check this field whenever the domain expert reports back** — a lever marked
   aspirational when the document was written can graduate to `done` within days, and the
   pipeline's own "X becomes Y" framing stays useful even after the swap is live, as the record of
   what changed and when (don't delete the before-state once it's real; that's the changelog).
   **This re-check is not only reactive.** A companion document describing a live,
   independently-editable surface (a colleague's actual process, a vendor's actual product, a
   published form or tool someone else can change without telling you) goes stale silently — don't
   wait for the domain expert to volunteer that something moved. Before resuming work on, or
   citing, a previously-elicited document, re-open the live thing it describes and diff against it
   directly rather than trusting the last elicitation (found 2026-09-02: a companion document
   describing a live Google Form drifted — two questions added, one wording claim removed — with
   zero record anywhere, because nothing prompted a re-check). Carry a `last-verified` date on any
   such document; log found drift in §11's sources table as a correction (`type: secondary` →
   re-verified `primary`), not a silent overwrite of the old claim.
6. **Recommend at MOST TWO "top picks" total, chosen for consolidation impact — not one per
   tier.** Added 2026-09-02: a flat list where every tier reads equally viable leaves the reader to
   guess which one is actually the recommendation. Pick the tool(s) that close the most/biggest
   named gaps, mark them `recommended: true`, and render them as a hero above the tier landscape —
   everything else is "the landscape this was chosen from," not a second-tier recommendation.
   Marking a third tool demotes the hero back into a flat list; don't.

- No jargon. A comparison table beats prose for this.
- **State what each option costs the person, not just what it saves.** "Removes the review step"
  is a cost (quality risk) as often as it's a win. A subscription's dollar cost is not the only
  cost — note implementation effort, a new vendor to manage, or unconfirmed technical feasibility.
- **Recommend a build order, reasoned from the stated objective, as a short numbered sequence —
  not a paragraph.** Free removals of mechanical friction (no quality trade-off) generally come
  before anything that trades a deliberate control away. One card per step (`n`, `lever`, `label`,
  `reason` — one sentence), not prose the reader has to parse for the actual sequence.
- **Land the tool section closed, like everything else in this skill's output.** Top picks first,
  then the tier landscape (one card per tier, its verdict in one line, its candidates listed), then
  the full cost/trade-off/maturity/source table behind a "Show full comparison" toggle. Progressive
  disclosure applies to tool research exactly as it does to the flow diagram: the top level is the
  whole answer at decision altitude, detail is opt-in. `template.html`'s `toppicks` + `tiercards` +
  `tools` table implement this; fill in `tier`, `maturity`, and `recommended` per tool and
  `CONFIG.tierVerdicts` rather than flattening everything back into one table.

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
tag needs to change for a new workflow). **There is no `mermaid` field and no Mermaid dependency
at all** — see § 3: the flow is a single `pipeline[]` array (unchanged/replaced/consolidated
nodes), because a dynamically-inserted `<pre class="mermaid">` never rendered in practice.
(v1.2, 2026-09-02, also dropped the earlier two-tab current/future split and the "Fully manual"
tab in favor of the one-pipeline model — see § 2–3.)

**On React, Tailwind, and shadcn — decided 2026-09-02, after a real frustration report** (editing
a previously-published Artifact was slow because its data was interleaved into its markup and
styling, making an edit hard to locate):

| | Decision | Why |
|---|---|---|
| **shadcn/ui** | **Refused, categorically.** | It's a copy-paste source-component system that assumes a real project with a build pipeline (TypeScript compile, path aliases, bundled Radix primitives). The Artifact sandbox is static HTML plus a small CDN allowlist with no bundler — shadcn cannot run there at all, not just "isn't worth it" |
| **React (CDN UMD build)** | **Conditional, not default.** Use only when a workflow genuinely needs multi-view state that plain event listeners can't hold cleanly | This skill's own content — a linear flow, cards, a table, and a handful of number inputs recomputing a total — is well within vanilla JS. Reaching for React here would be solving a problem this content doesn't have |
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

**This skill IS directly portable to claude.ai/Cowork for non-CLI users — confirmed 2026-09-02,
re-checked against live Anthropic docs, not assumed from the Claude-Code-only mechanism above.**
Two separate distribution paths exist; don't conflate them:

| | Claude Code (`.claude/settings.json` managed push) | claude.ai / Cowork (Organization settings → Skills) |
|---|---|---|
| **Tier gate** | Team/Enterprise | **Team is sufficient — not Enterprise-gated**, corrected 2026-09-02 (this section previously implied otherwise by only naming the Claude Code path) |
| **Mechanism** | Push to `.claude/settings.json` on every seat | Admin uploads a `.zip` of this skill's folder in Organization settings → Skills; it's on by default for every seat, individually toggleable |
| **What a non-technical user needs installed** | The Claude Code CLI | Nothing beyond a claude.ai account — this is the actual answer to "can a sales rep with no CLI use this" |

**What does NOT carry over to claude.ai/Cowork, and the concrete workaround:**
- **`Agent`/`Workflow` parallel dispatch (§6's Phase 2 wide-research fan-out) does not exist
  outside Claude Code.** On claude.ai/Cowork, Phase 2's research still has to happen — cast the
  same wide net per segment — just sequentially within one conversation rather than as parallel
  subagents. The requirement (real research, not a transcript recap) doesn't relax; only the
  mechanism does.
- **`ToolSearch`'s deferred-tool-loading pattern is Claude-Code-specific.** On claude.ai/Cowork, an
  MCP connector (Drive, Calendar, etc.) either is or isn't already connected to that session — there
  is no separate "load the schema" step to write into the skill body.
- **Artifact publishing itself is NOT a gap** — claude.ai has had native Artifacts since before
  Claude Code existed, so `template.html`'s CONFIG/DATA-fill approach works identically there.
- **The `description` field has a HARD 200-character cap on claude.ai** (vs. 1024 on the API/Claude
  Code) — this skill's own frontmatter description is well over that. **Don't shorten the real
  description** (Claude Code's own discovery depends on its fuller detail) — instead, package a
  trimmed description alongside it for the claude.ai upload:
  `"Elicit a colleague's manual workflow, map current→future, name pain points, and recommend
  automation options with trade-offs — for non-technical domain experts."` (160 chars).

**Uploading and enabling org-wide on claude.ai is an account-administration action** — the kind
this session proposes rather than performs (see the global Autonomous Execution Contract's
explicit-permission list: "changing account settings"). An org admin does it via Organization
settings → Skills, not an agent.

**Cowork's own "workflow" capability, checked 2026-09-02 against current docs — two distinct
features, neither is a full match for Claude Code's `Workflow` tool:**
- **Scheduled tasks** — real, named, on all paid plans including Team: a single prompt on a
  recurring cadence (hourly/daily/weekly/on-demand), cloud-executed. The prompt can do multi-step
  work internally — this is sufficient for a recurring single-domain-expert automation (e.g. a
  weekly signal-finding digest), and is the closest non-CLI equivalent when a recommendation in
  this skill's output calls for "something that runs on its own on a schedule."
- **Dispatch** — fans a task into parallel subtasks, but one-shot, not schedulable — the opposite
  trade-off from Scheduled tasks.
- **No unified primitive exists combining both** (schedule + explicit multi-step chaining, "run A,
  wait for it, then run B") — confirmed absent, not just unfound. Don't recommend a Cowork
  substitute for anything this skill's own Phase 2 (§6) parallel research fan-out does; there isn't
  one yet.
- **Org-wide provisioning of a scheduled task is not documented for Team tier**, unlike Skills
  (§9 above) — an admin can enable/disable Cowork org-wide, not push one specific scheduled task to
  every seat.

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

## 10 · Close with a triage verdict — what happens to this next

**Added 2026-09-02, on request — the deliverable isn't finished at the recommendation; it needs a
stated next move.** End every use of this skill with an explicit verdict on what the domain expert
should do with what was just produced. Pick exactly one, and say why:

| Verdict | When it applies | What it means concretely |
|---|---|---|
| **✅ Self-investigate** | Every open lever is 🧩 Build-tier and ✅ feasible-now, or the only remaining step is confirming a number/access the domain expert can check themselves | They can act on this document alone — try the feasibility check, request the beta access, adjust the calculator. No engineering judgment call is pending |
| **🔬 Book a technical consultation** | A lever's feasibility genuinely depends on engineering judgment (does an API expose what's needed, is a schema constraint negotiable, is a workaround safe) that the domain expert cannot resolve by reading or asking around | Name the specific open question the consultation should resolve — not "discuss the workflow," but the exact unresolved technical fact (see `/blocker-meeting` if this repo has it, for the prep-pack discipline) |
| **📤 Share as pre-loaded context with a named technical stakeholder** | Someone is already identified or assigned to work the gap (an engineer already in the source meeting's action items, a named owner) | Say who, and what in this document they need before their own work starts — this document becomes their briefing, not a thing they discover mid-task |

**This is Phase 4 of §6, and the tier alone does not decide it — this specific person's stated
capability does.** Owner instruction, 2026-09-02: a 🧩 Build-tier, ✅ feasible-now lever is not
automatically self-investigate. Ask, concretely, before picking a verdict: has this person said
anything about their own experience with the tooling involved (self-reported novice with agentic
AI, already building their own automations, somewhere between)? **Cite the specific words that
settle it, the same way any other claim in this document is sourced** — "self-investigate" earned
by a domain expert's own "I've been scripting this for years" reads differently than one earned by
silence. Where the transcript gives no signal either way, say that explicitly rather than
defaulting to self-investigate because the tier allows it — an unstated capability is a gap in the
elicitation (§1), not a reason to assume competence.

**These aren't mutually exclusive across levers within one document** — one lever can be
self-investigate while another needs a consultation. State the verdict per lever if they diverge,
not one blanket verdict for the whole workflow. **Never leave it unstated**: a recommendation with
no next-action verdict reads as finished when it's actually still waiting on someone.

## 11 · Backlink every claim — an assumptions & sources table, not a trust-me document

**Added 2026-09-02, same day a primary-source transcript overturned several claims this document
had been carrying at secondhand strength.** Every substantive claim traces to a labeled source, in
one table, folded behind a toggle like the full tool comparison:

- **`type` per row**: `primary` (a transcript/document read in full) · `secondary` (a relayed
  note — weaker, say so) · `vendor` (the tool's own marketing, not independently verified) ·
  `verified` (checked directly against this account/product) · `idealized` (no real data yet —
  a placeholder or an open question, not an assumption to trust).
- **Backlink where a URL exists.** A citation with no link is a claim nobody downstream can
  re-check; the point of primary-sourcing is that it's re-checkable.
- **List every `idealized` item explicitly, don't bury it in a hedge paragraph.** A reader scanning
  the table should immediately see which numbers are real and which are placeholders — this is the
  same principle as labeling `⚠️ UNCONFIRMED` (§5), generalized to every kind of claim, not just
  time estimates.
- `template.html`'s `references[]` + the folded `sec-refs` table implement this; fill it in rather
  than leaving citations only in prose.

## 12 · Audit-status tags — idealized vs. AI-reviewed vs. engineer-reviewed

**Added 2026-09-02, on request, after an engineering-recommendation section shipped a real
contradiction its own prose had already caught** (a proposed schema and the paragraph beneath it
disagreed, and only the schema is what a builder works from). This skill's own Design→adversarial
Review pattern (§6 Phase 2/3, done via two independent agent dispatches) is real and worth
something — but it is not the same thing as a human engineer's sign-off, and conflating the two is
how a reviewed-sounding recommendation gets built without anyone actually checking it.

**Three tags, and every recommendation this skill produces carries exactly one, visibly:**

| Tag | Means | Who checked it |
|---|---|---|
| 💭 **Idealized** | Not yet checked by anyone beyond the author | Nobody |
| 🔍 **AI-reviewed** | Passed through a designer→adversarial-reviewer pass — real research and real refutation, but not a human sign-off | An agent, adversarially |
| 🛠️ **Engineer-reviewed** | A human engineer has read it and signed off | A person, before any build starts |

**A tag is not a formality — it gates what happens next.** 🔍 AI-reviewed is good enough to hand to
a domain expert as a recommendation (§10's verdicts still apply) but is NOT good enough to start
building from, especially for anything touching a schema, an integration, or a stage that overrides
a domain expert's own stated boundary (see the stage-4 example above — the adversarial pass exists
precisely to catch that class of error before a human engineer's time is spent on it, not instead
of their review).

**When this skill's own two-agent pattern finds a blocking issue, fix it in the document, don't
just note it.** A findings list appended below a still-broken table is not corrected. Fold every
fix into the actual recommendation — the design/review agents' names never appear in the output;
only the corrected content and an honest tag do.

**Retroactively apply this to a document's existing content when the tagging convention is adopted
partway through** — don't leave earlier sections untagged while new ones carry the label; an
untagged claim reads as unaudited-and-forgotten, not as audited-before-the-convention-existed.

## 13 · An engineering-recommendation section is a FLOW, cross-linked, never a side-by-side overlay

**Added 2026-09-02, on request, after a first version presented as a data table instead of a
diagram.** When §6's research surfaces a longer-term engineering pipeline (not just a tactical
tool pick), it gets the SAME treatment as the main pipeline in §2–3, not a different one:

- **Render it as one linear flow, top-down, in the same visual grammar as the main pipeline** —
  reuse the `.flow`/`.flownode`/`.flowinto` pattern, not a wide table. A stage-by-stage table is
  fine as the markdown source's working format, but the Artifact reader gets a diagram.
- **Never a literal overlay or side-by-side column against the main pipeline.** §2–3's own
  hard-won lesson (pixel-aligning variable-height cards across two panels is a known drift bug)
  applies here exactly as it does to a current/future split — an engineering flow layered visually
  on top of the tactical flow has the identical failure mode. Instead: **cross-link with a small
  chip at the tactical node** ("🔗 See the engineering-tier path in §N") pointing to the
  corresponding stage in the engineering flow, and open the engineering section with a compact
  three-tier caption — *current (manual) → tactical (today's self-serve recommendation) →
  engineering (this section)* — so the relationship is stated, not spatially implied.
- **Every stage gets a plain-language "try it yourself" prompt, not just a schema.** A non-technical
  reader cannot act on `Signal{signal_id, source_url, signal_type: enum[...], ...}` — but can act on
  "ask a Claude Project to remember a short list of websites, and once a week tell you what changed
  on each one and which site it came from." Translate every stage's schema into one copy-pasteable,
  plain-English prompt a domain expert could try in an existing self-serve surface (a Claude
  Project, a Cowork scheduled task) — **this is a genuinely different tier from both "self-serve"
  and "technical build"**: a lightweight, ungoverned experiment a non-technical person can run
  themselves, distinct from the production/audited version an engineer would build. Label it as
  such — an experiment is not a shipped capability, and don't let the two blur.
- **Say plainly when a stage has no honest DIY version yet.** A validation/scoring stage that
  depends on measuring an earlier stage's error rate genuinely has no "try it yourself" prompt worth
  giving — state that directly ("this one isn't ready to experiment with alone yet — it depends on
  the earlier stage running for a while first") rather than manufacturing a toy version that would
  teach the wrong lesson.

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
- **Does not treat a relayed account as verified without checking for the source conversation's own
  notes or transcript.** See § 1 — and does not claim a transcript was checked when the tool to
  read one was unavailable; it says so.
- **Does not recommend more than two top picks.** See § 6 point 6 — a third "recommended" tool
  turns the hero back into the flat list it was built to replace.
- **Does not end without a triage verdict.** See § 10 — self-investigate, book a technical
  consultation, or share as pre-loaded context with a named stakeholder; never left unstated.
- **Does not cite a claim without a labeled source.** See § 11 — every claim is `primary`,
  `secondary`, `vendor`, `verified`, or `idealized`, backlinked where a URL exists.
