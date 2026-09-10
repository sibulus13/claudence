---
name: end-of-day
description: Close a working session properly — drain the day log into the registers, update the state documents, reconcile the task list, verify nothing is stale, and sync the day's Next items to the Notion work log. Invoke whenever the user signals end of day, wrapping up, or leaving off for tomorrow.
---

# End of day

**Closing a session is part of the work, not tidying.** It is the step that gets skipped, and
skipping it is what makes the next session expensive — a cold start re-derives what was already
decided.

**Run the phases in order.** Later phases depend on earlier ones being true.

## 0 · Check peer sessions before finalizing anything

**Owner instruction, 2026-09-01 — the mirror of `/start-of-day` §1a, at the other end of the
day.** A peer session's work does not stop when yours does, and a `TODO.md`/`DECISIONS.md` read
taken before checking is a read that misses whatever they landed in the last hour.

- Call `ListAgents` before touching `Now`/`Next`. For any peer whose track overlaps today's work,
  send a short, non-blocking end-of-day check: what they closed that isn't reflected in the
  shared registers yet, what they're carrying into tomorrow, anything blocked on the owner, and
  any lane/file they're still actively holding.
- **Do not block on the reply.** Finalize with what you have; fold in anything that arrives after
  — a peer's reply is itself new information to fold into `Now`/`Next`, not a formality.
- A peer's reply naming a real finding (a stale register, a convention violated) is surfaced back
  to them directly, not silently fixed — they have context you don't on their own recent work.

## 1 · Keep a day file DURING the day, not just at close

**Owner instruction, 2026-09-01: write to `docs/journal/DAY-<date>.md` at each major task
completion or pivot point AS IT HAPPENS, not compose one retroactively when closing.** A day file
built only at close is a memory exercise; one kept live is a running ledger that makes closing
cheap. If no day file exists for today when this phase runs, that absence is itself a finding —
the practice lapsed — not something to backfill by inventing one now.

**A day file that grows without shrinking is the signal that draining is being skipped.**

- Find today's day log — typically `docs/journal/DAY-<date>.md`.
- **Every open finding gets a permanent home**: a decision row, a register, a trace, or the
  journal. **Never leave a finding only in the day file.**
- Rewrite the day file to record *where each finding went*, not what it said. **It should get
  shorter.**
- If a finding has no home, that is the finding: it means no register owns that concern.
- **Once everything in it has a home, remove the day file** — its content now lives in the
  registers it was drained into; keeping it around duplicates what those registers already say.

## 2 · Update the state documents

| Document | What it owes at close |
|---|---|
| **`FACTS.md`** | **Every load-bearing figure produced today, with the query behind it.** A figure that lives only in a decision row is one nobody can re-derive |
| **`JOURNAL.md`** | An entry **only if direction changed** or tribal context surfaced. Tag entries `PIVOT` · `MEASURED` · `TRIBAL`. **Bump `last-verified`** — adding an entry without bumping the stamp is the drift this catches |
| **`TODO.md`** | Rewrite **`Now`** for a cold start: what is in flight, what is unblocked, what is blocked *on a person*. Add a state table — remote, tracked paths, counts |
| **`STATE.md`** | Where the project stands, what is blocked on whom |
| **`DECISIONS.md`** | Anything decided today that is not yet a row |

**Do not restate.** If a finding is in a decision row, the journal cites it rather than repeating
it.

**Owner instruction, 2026-09-02 — cross-check today's actual work against every register that
mentions it, before writing anything new.** Closing is not just adding a fresh row; it is
checking whether today's work made an EXISTING row wrong. Concretely: for each thing accomplished
today, grep `TODO.md`'s `Now`/`Next`/`Backlog` and today's Notion `Accomplished`/`Next` for any
row describing it in its PRE-today state (still-open, not-yet-built, shortened-to-N, etc.) and
either prune it (if the file's own convention prunes done rows) or rewrite it to the current
state — never leave both the old row and a new one standing, silently disagreeing. **Found
2026-09-02**: `TODO.md`'s Next section still read "AI Fluency Pulse... not yet built in any
tool" the same night the form was built AND published — the stale row would have sat there
indefinitely if nobody had thought to check it, because adding the new accomplishment row was the
easy half and pruning the outdated one is the half that gets skipped.

## 2a · Run the friction retrospective

**Every close runs it — not gated on the score threshold.** The Stop-hook suggestion
(`analyze-session.py`'s `sessions_since_review >= 3 AND total_score >= 6`) is a mid-session nudge;
it can go unmet for days on a quiet session while real friction — including a sustained,
multi-prompt frustration streak — sits unreviewed in `~/.claude/telemetry/reports/`. Invoke the
`retrospect` skill directly as part of closing the day, whether or not the threshold has fired.
If there is nothing to review (empty `reports/`, or every report scores 0), it says so and there
is nothing further to do — that is a valid, cheap outcome, not a wasted step.

**Read `frustration_streaks[]` specifically, not just the flat score.** A streak means the same
expectation went unmet across consecutive turns, not once — check whether it is already captured
as a memory or `CLAUDE.md` rule before writing a new one. A correction that recurred without ever
being captured is the clearest sign a rule is missing, and it is exactly the kind of finding a
flat per-session score buries.

## 3 · Reconcile the task list

**Every task that closes goes into today's Notion `Accomplished` — at the moment it closes, not
at day end.** A completed task recorded only in the task list is invisible to the record the
organisation actually reads. **Write the outcome, not the task title**: *what changed*, not
*what was worked on*.


- **Close tasks against their stated definition of done** — never against effort spent.
- **The task list holds the CRITICAL PATH ONLY — ideally one or two items.** Anything not being
  worked now lives in `TODO.md`'s backlog **with the blocker that put it there**, and is deleted
  from the list. **A backlogged task left pending is indistinguishable from an active one**, which
  is how a two-item critical path reads as six.
- **Then DELETE the closed ones.** Marking a task `completed` leaves it in the list; **"cleared"
  means removed.** A done column that accumulates is a list nobody scans. **Delete only once the
  outcome is recorded** in the decision register and today's `Accomplished` — the record lives
  there, not in the task.
- **A task whose premise disappeared is closed NOT-DONE with the reason**, not left pending.
- **A task that drifted from its original intention is rewritten**, and the drift recorded — a
  task read as outstanding when it was actually superseded invites redoing work under an
  obsolete design.
- Create tasks for anything discovered today and not yet captured.

## 4 · Verify, do not assume

Run every check and **read the exit code, never the absence of output**:

```
python3 scripts/gates.py          # bare — a filter replaces the exit code with its own
python3 scripts/freshness.py      # stale or orphaned documents
git status --porcelain            # nothing unintended staged — and see below
```

**A tracked path in `git status` is a finding, not noise.** Tracking is publishing, so an
uncommitted edit to a shared document is a change nobody reading the shared copy can see, and it
survives silently for as long as nobody runs this. **Found 2026-08-18: a rewritten claim had been
sitting uncommitted in the published proposal since a previous session.**

| What `git status` shows | What to do |
|---|---|
| **A path in the published/tracked tier** | **Surface it with its diff and STOP.** Promotion is a human act — never commit, never revert, never leave it unmentioned |
| A working-tier path | Normal. It is gitignored and going nowhere |
| **Nothing, and you expected something** | Check you are in the right repo before believing it |

**A check that cannot see its subject reports nothing, which looks exactly like a pass.** If a
gate script errors, that is a failure, not silence.

## 5 · Sync the Notion work log

**The repo's `TODO.md` and task registers are the GROUNDING source of truth; Notion is a
minimized reference — reversed 2026-08-27, on the owner's instruction, from the earlier
direction (Notion primary, repo durable). Reconcile toward the repo when they disagree, and say
where they did.** Consolidated with `/start-of-day`, which now cites this section rather than
carrying its own copy of the cap.

**Standing rule, owner 2026-09-09: check Notion's own current-day entry for outstanding tasks
as PART of this sync, not only push repo state INTO it.** The sync above is one-directional
(repo → Notion); this closes the other direction. Read today's Notion entry's own `Goals`/
`Next` for anything the owner marked as intended for today that never got picked up in the
session (an item added directly in Notion, not routed through the repo). **Anything outstanding
for today is queued explicitly into tomorrow's `TODO.md` `Now`, under a "first thing" heading**
— never left to be silently rediscovered when tomorrow's session reads `Now` cold. This is a
genuine two-way reconciliation, not a formality: an item that exists only in Notion and never
reaches `TODO.md` is invisible to the next session, which reads the repo, not Notion, per this
section's own grounding-source rule above.

**The Notion log is PUBLISHABLE, and agent-written content is marked as such.**

| Rule | Why |
|---|---|
| **ONE SENTENCE OR LESS PER THEME — the hard cap, added 2026-08-27** | Notion carries a high-level architectural overview of what was found, never the finding itself. A theme is the project's own faculty (business · technical · programme), not a per-decision bullet — **if it takes a second sentence, it is detail, and detail belongs in `TODO.md`/`DECISIONS.md` with Notion pointing at it.** This applies to every section an agent writes into: `Goals`, `Accomplished`, `Next` alike |
| **No PII in `Accomplished`** — no person names, no customer organisation names | **It is publicly publishable.** This is stricter than the working tier, where colleagues may be named. Describe the person's ROLE or the shape of the finding, never the individual |
| **Agent-written bullets go under a `## Claude-generated · <programme> — detail: <path>` heading** | The owner writes their own entries in the same sections. **Unseparated, nobody can tell which decisions were theirs** — and an agent's summary read as a person's commitment is the failure. **Same heading in every section and at both ends of the day** — `/start-of-day` defers to this one |
| **Touch `.dayflow/<YYYY-MM-DD>.end` before finishing** | The reminder to close a day cannot be a memory, because memory is what kept skipping it. **`freshness.py`'s `F8` reports a day that opened and never closed after 16:00** — the marker is what makes that visible, and it proves the skill ran, nothing more |
| **Re-align the three registers before writing `Next`** | Notion's top goal, the task list's top item and `TODO.md`'s first `Now` row **name the same thing**, or the priority is not decided. Everything below the top two or three is written to `TODO.md` and **deleted from the task list** — see `/start-of-day` § 3a, which owns this rule |
| **`Next` is HIGH-LEVEL, nested, and short** | Three top-level items at most, one sentence each. **Nesting is permission to omit, not permission to add** — a nested item is one short line or it does not belong |
| **Every section BACKLINKS to the local file that holds the detail** — `` `docs/TODO.md` § Now `` | **The repo is the grounding record; Notion is the pointer.** A session must be able to restart from local context alone, so anything repeated in both lives locally and Notion links to it rather than restating it |
| **Separate *what only the owner can decide* from *what is ready to build*** | A decision waiting on a person and a task waiting on effort read identically in a flat list, so the blocked ones silently become the excuse |

- **Fetch today's entry FIRST and read it in full** — the owner may have added Goals/Notes/Next
  content directly during the day. Reconcile against what is actually there, not against what you
  expect to be there; a repo-side `Now`/`Next` write that ignores an owner-added Notion item is a
  consolidation that missed half its inputs.
- **Found live, 2026-09-09/10 — the heading rule above was applied to `Accomplished` but skipped
  on `Next` in the SAME close.** `Accomplished` got its `## Claude-generated · ...` wrapper;
  `Next`'s three bullets were written bare, indistinguishable from a human addition to the same
  block. No content was confirmed lost this time, but the risk is real and the rule already
  existed — this was an execution gap, not a missing rule. **The fix is a verification step, not
  a reminder to remember harder**: before declaring the close finished, re-fetch the page and
  confirm EVERY section this close touched (`Goals`, `Notes`, `Accomplished`, `Next` — all of
  them, not just the ones that feel agent-heavy) has its bullets under the heading. A section
  with agent content and no heading is not "fine because it's short" — it is unrecoverable
  ambiguity the moment a human adds one line beside it.
- **When using `notion-update-page`'s `update_content`, scope `old_str` to ONLY the agent's own
  prior heading block** (e.g. `## Claude-generated · ... \n- <old bullets>`), never to the whole
  `# Next`/`# Notes` section from its header to the next `#`. A section-wide `old_str` silently
  matches and discards any human line sitting in the same block that isn't part of the quoted
  string — the heading convention only protects content it actually wraps at the replace
  boundary, not the section as a whole.
- **Update its `Next` section** from the repo's `TODO.md` `Now` — the two must agree, and `TODO.md`
  wins on conflict.
- **Owner instruction, 2026-09-02 — ANY edit to a register during this close re-triggers this
  reconciliation, not just the first pass.** Found live: `TODO.md`'s Next section got pruned and
  a new row added mid-close (in response to the owner's own consolidation feedback), but Notion's
  `Next` was never re-diffed against it — it sat stale until the owner asked why. **The fix isn't
  "remember to sync Notion once" — it's treating every subsequent register edit in the same
  closing conversation as reopening this step.** Concretely: before declaring the close finished,
  re-read whichever register was touched last and confirm every OTHER register describing the same
  fact (Notion `Next`, `TODO.md`, a theme's own README, wherever else the fact is mirrored) says
  the same thing. An edit made reactively, after the first report went out, is not exempt.
- Add anything from today that belongs in the record, **one sentence per theme**: stakeholder
  conversations, decisions taken, blockers raised. Not a list of what happened — the architectural
  headline, with the local file carrying the rest.
- **Any session with something to add writes it in directly** — routing an already-agreed
  accomplishment through another session first is a round trip the entry does not need.
- **Ask before writing to Notion** if the entry already has content that would be overwritten.

## 6 · Report

**Terse nested bullets, one line each** — what closed, what is blocked on a person, where
tomorrow starts. **The detail lives in `TODO.md`; the terminal gets the summary.**

**Owner instruction, 2026-09-02 — every close also reports two things the terse bullets above
don't carry on their own:**

- **Accomplished vs. set-out.** Line up what today's Goals (this morning's `/start-of-day`
  carry, or the session's own stated objective if no `/start-of-day` ran today) actually
  resolved to: done as stated, done differently, dropped, or added mid-day and done instead.
  **Say which is which** — a goal quietly swapped for a different one is a finding, not a wash.
  If no goal was ever stated today, say that plainly rather than reconstructing one after the
  fact.
- **A session focus score (the "ADHD score")** — light-touch, not clinical, not a comment on the
  person. Start at 10 and subtract one point per **topic pivot** (a switch to a materially
  different task, not a sub-step of the current one) and one point per **mid-turn interruption**
  (the user cutting in before a reply finished), floor of 1. State the raw counts alongside the
  number so it's checkable, not vibes: e.g. "Focus 6/10 — 2 topic pivots, 2 mid-turn
  interruptions." A low score is informational, not a verdict — some days are legitimately
  multi-threaded.

## What this skill will not do

- **Publish anything.** Tracking is publishing; promotion is a human act.
- **Commit or push** unless the repo's own conventions say to, and never to a shared branch
  without saying so.
- **Invent a Notion entry** that does not exist — if today has no log entry, say so.
