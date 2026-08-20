---
name: end-of-day
description: Close a working session properly — drain the day log into the registers, update the state documents, reconcile the task list, verify nothing is stale, and sync the day's Next items to the Notion work log. Invoke whenever the user signals end of day, wrapping up, or leaving off for tomorrow.
---

# End of day

**Closing a session is part of the work, not tidying.** It is the step that gets skipped, and
skipping it is what makes the next session expensive — a cold start re-derives what was already
decided.

**Run the phases in order.** Later phases depend on earlier ones being true.

## 1 · Drain the day log

**A day file that grows without shrinking is the signal that draining is being skipped.**

- Find today's day log — typically `docs/journal/DAY-<date>.md`.
- **Every open finding gets a permanent home**: a decision row, a register, a trace, or the
  journal. **Never leave a finding only in the day file.**
- Rewrite the day file to record *where each finding went*, not what it said. **It should get
  shorter.**
- If a finding has no home, that is the finding: it means no register owns that concern.

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

**Notion is the day-to-day source of truth; the repo is the durable analysis.** Reconcile toward
Notion when they disagree.

**The Notion log is PUBLISHABLE, and agent-written content is marked as such.** Two rules,
both stated by the owner 2026-08-18:

| Rule | Why |
|---|---|
| **No PII in `Accomplished`** — no person names, no customer organisation names | **It is publicly publishable.** This is stricter than the working tier, where colleagues may be named. Describe the person's ROLE or the shape of the finding, never the individual |
| **Agent-written bullets go under a `## Claude-generated · <programme> — detail: <path>` heading** | The owner writes their own entries in the same sections. **Unseparated, nobody can tell which decisions were theirs** — and an agent's summary read as a person's commitment is the failure. **Same heading in every section and at both ends of the day** — `/start-of-day` defers to this one |
| **Touch `.dayflow/<YYYY-MM-DD>.end` before finishing** | The reminder to close a day cannot be a memory, because memory is what kept skipping it. **`freshness.py`'s `F8` reports a day that opened and never closed after 16:00** — the marker is what makes that visible, and it proves the skill ran, nothing more |
| **Re-align the three registers before writing `Next`** | Notion's top goal, the task list's top item and `TODO.md`'s first `Now` row **name the same thing**, or the priority is not decided. Everything below the top two or three is written to `TODO.md` and **deleted from the task list** — see `/start-of-day` § 3a, which owns this rule |
| **`Next` is HIGH-LEVEL, nested, and short** | Three top-level items at most. **Nesting is permission to omit, not permission to add** — a nested item is one short line or it does not belong |
| **Every section BACKLINKS to the local file that holds the detail** — `` `docs/TODO.md` § Now `` | **The repo is the durable record; Notion is the summary.** A session must be able to restart from local context alone, so anything repeated in both lives locally and is *pointed at* from Notion |
| **Separate *what only the owner can decide* from *what is ready to build*** | A decision waiting on a person and a task waiting on effort read identically in a flat list, so the blocked ones silently become the excuse |

- Find today's entry in the work-log database named in `CLAUDE.local.md`.
- **Update its `Next` section** from the repo's `TODO.md` `Now` — the two must agree.
- Add anything from today that belongs in the record: stakeholder conversations, decisions taken,
  blockers raised.
- **Ask before writing to Notion** if the entry already has content that would be overwritten.

## 6 · Report

**Terse nested bullets, one line each** — what closed, what is blocked on a person, where
tomorrow starts. **The detail lives in `TODO.md`; the terminal gets the summary.**

## What this skill will not do

- **Publish anything.** Tracking is publishing; promotion is a human act.
- **Commit or push** unless the repo's own conventions say to, and never to a shared branch
  without saying so.
- **Invent a Notion entry** that does not exist — if today has no log entry, say so.
