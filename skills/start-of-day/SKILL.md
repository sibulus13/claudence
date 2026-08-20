---
name: start-of-day
description: Open a working session — create today's Notion work-log entry, carry yesterday's Next into today's Goals, reconcile against the repo's task list and TODO, and report what is actually in flight. Invoke whenever the user signals start of day, beginning a session, or picking up where they left off.
---

# Start of day

**Today's Goals are yesterday's Next.** That is the whole mechanism, and it only works if the
carry is done deliberately — a Goals section written from memory drifts from what was actually
agreed the night before.

**Run in order.** Each phase supplies the next.

## 1 · Find yesterday, not "the most recent"

- Search the work-log database named in `CLAUDE.local.md` for the entry whose date is
  the **previous working day**, not simply the newest entry.
- **A weekend or a gap is normal** — carry from the last day that has content, and say which day
  you carried from.
- **If today's entry already exists, do not recreate it.** Read it, and reconcile rather than
  overwrite.

## 2 · Carry the Next into today's Goals

- **The carry is a DISTILLATION, not a copy — every `Next` item is accounted for, and only two
  or three become `Goals`.** The rest is classified, never dropped: blocked-on-a-person and
  stretch items go to `Notes` (see § 2b), and steps belong to the task register. **Nothing
  vanishes silently; nothing arrives as a goal it was not.**
- **A checked `Next` item carries with its tick intact.** A goal arriving already ticked is the
  record of what was finished ahead of time, and **the day-to-day cadence is only legible if
  that survives the carry.**
- **Preserve wording and state.** Rephrasing an agreed item is how intent quietly changes
  overnight; **unchecking a finished one re-opens work that is already done.**
- **`Goals` is the ONLY section that carries.** `Notes` never does — **copying a note forward
  duplicates it, and a duplicated future-dated reminder is worse than a lost one**: Notion shows
  both, and neither is authoritative. Observed 2026-08-19, when a reminder for the next day was
  copied into a new entry and both were then marked duplicate.
- **A future-dated item in yesterday's `Notes` is surfaced in the REPORT, not reproduced in the
  page.** It already lives on the day it was written, and that day is still in the database.

## 2a · Two failures the template will hand you

**Observed on the first live run, 2026-08-18.**

| Failure | What to do |
|---|---|
| **Notion auto-links anything resembling a filename** — `ARCHITECTURE.md` becomes a markdown link, which breaks an exact-match edit | **Re-read the live content before editing.** An anchor copied from what you wrote is not what the page now holds |
| **A completed item carried as OPEN** — the template copies a checked `Next` item into `Goals` unchecked | **Re-check it.** The carry was correct; **the lost state is the bug.** Never delete it — a finished goal in today's list is the cadence working |
| **Two entries created for the same day**, seconds apart, one blank | **Report it; do not delete.** Notion pages are the user's data — say which is populated and let them remove the other |

## 2b · `Goals` are objectives, not a task list

**A goal is what the day is FOR. A task is a step toward one.** The log is a record of intent at
day scale, and **a Goals section that mirrors the task list one-for-one has stopped being a
record and become a duplicate.**

| | |
|---|---|
| **Roll tasks up** | Several tasks serving one end become **one goal named for that end** |
| **ONE, and at most two** | **Instructed twice on 2026-08-19, tightening each time: the log carries the highest-value, most-critical-timeline item and nothing else.** Even three reads as a list; **a day with one named goal is a day with a direction**, and the steps are in the task register where they belong |
| **A goal survives a day** | If it can only be true or false by tonight, it is probably a task |
| **The task list stays the source of truth** | It holds the steps, the definitions of done, and the blockers — **the log does not repeat them** |

**Nest a step only when it changes what the goal means** — a blocker that must clear first, or a
half already finished. **Not to show progress.**

**What is NOT a goal, and where it goes instead.** This is the mechanism that keeps the list at
two or three; without it, everything true about today becomes a bullet.

| | |
|---|---|
| **Blocked on a person** — a restart, a review, an unmade decision | **`Notes`.** It cannot be worked, so as a goal it is a standing reproach |
| **A stretch item** | **`Notes`.** Marking it *stretch* already concedes it is not the direction |
| **A step of a goal already listed** | Nowhere — it is in the task register, which owns steps |

## 2c · Rehydrate the task register, and reprioritise only when told

**The session task register does not survive a session** — observed 2026-08-19, when six task
ids cited across a repo's registers resolved to nothing while still reading as live. **The
repo's `TODO.md` is the durable register; the task tool is a convenience.** So recreate the
tasks from `Now` and `Next` as part of opening, each with the definition of done the document
already states, and set the blocking relations the document implies.

**Reprioritising is not part of the carry.** The carry preserves yesterday's order, because
that order was agreed. **Re-order only on an explicit instruction**, and when one comes:

| | |
|---|---|
| **Say what moved and why** | A silent re-order is indistinguishable from a misread carry |
| **Record it where it binds** | The new order goes in the repo's decision register, not only in the log — a priority held only in Notion is invisible to the next agent |
| **Re-block what the new order implies** | If measurement now precedes construction, the construction task is *blocked by* it. **Order without dependency is a preference; order with dependency is a contract** |

## 3 · Reconcile against the repo

**Notion is the day-to-day record; the repo holds the durable analysis. Reconcile toward Notion
when they disagree, and say where they did.**

- Read the repo's `docs/TODO.md` **`Now`** and the task list.
- **Three checks, and each disagreement is a finding:**

| Check | What a mismatch means |
|---|---|
| A Notion `Next` item with no task | **Work agreed and untracked** — create the task |
| A task in flight with no Notion counterpart | Either it is invisible to the record, or it is not really in flight |
| A task whose premise changed overnight | **Rewrite it before working it** — a task read as current when it is superseded invites redoing work under an obsolete design |

## 3a · Align the two lists, reprioritise the rest, and carry the roadmap forward

**Three registers describe the same work and they drift apart daily**: Notion's `Goals`, the
in-session task list, and the repo's `TODO.md`. **Alignment is a phase, not a courtesy** — a
plan held in three places that disagree is three plans.

| Step | What it means |
|---|---|
| **1 · One top item, three places** | Notion's single `Goals` line, the task list's top item, and `TODO.md`'s first `Now` row **name the same thing**. If they cannot, the priority is not decided |
| **2 · Keep the task list to the top two or three** | Everything else is **written into `TODO.md` first**, then **deleted** from the task list. A list of ten is a list nobody reads, and the durable register is the file |
| **3 · Reprioritise the remainder deliberately** | Each demoted item lands in `Next` (agreed, unblocked) or `Backlog` (**with the reason it waits**) — never dropped, never left in both places |
| **4 · Two charts, two clocks — one is redrawn, one only ever grows** | The `Now` **dependency flowchart** shows today's stages and is redrawn daily. The **cumulative roadmap** (a `gantt` in the project's state document) is **EXTENDED: a completed bar is never removed or reworded, a slipped bar moves its date and keeps its id, and new work is appended in its section.** Instructed 2026-08-19 after two wholesale rewrites in one day — **a roadmap redrawn from today's priorities is a to-do list with a timeline, and it cannot show whether you are ahead or behind.** Where a project checks it (e-studio's `freshness.py` `F9`), the completed-bar count is a high-water mark that may not drop |
| **5 · State the continuity in one line** | What carried, and what changed direction. **That sentence is the whole point of the phase** — it is what makes yesterday's work legible today |

**Every stage in the diagram carries two things or it is decoration: what it NEEDS before it can
start, and what DONE means.** A stage with no prerequisite named cannot be sequenced, and a
stage with no definition of done closes on effort.

## 3b · The day has two ends, and both are mechanical

**`/start-of-day` in the morning, `/end-of-day` before leaving — and the reminder is a file, not
a memory.** Each skill writes a marker (`.dayflow/<YYYY-MM-DD>.start` / `.end`) in the project,
and the Stop-hook freshness check reports a missing one late in the day. **A discipline that
depends on remembering is the discipline that lapsed** — which is why the close kept getting
skipped, and skipping it is what makes the next session expensive.

## 4 · Create or update today's entry

Sections, in the order the existing entries use: **`Goals` · `Notes` · `Accomplished` · `Next`**.

- `Goals` — **two or three**, distilled from yesterday's `Next` per § 2b, plus anything the user
  adds.
- `Notes` · `Accomplished` — **left empty by default.** They are filled as the day happens, not
  predicted. **Anything an agent does write into ANY section is nested under the
  `## Claude-generated · <programme> — detail: <path>` heading that `/end-of-day` defines** —
  one convention across both ends of the day, not two. **The owner writes their own bullets in
  the same sections, and unseparated nobody can tell which commitments were theirs.**
- `Next` — **left empty.** It is written at close, by `/end-of-day`.

**Ask before writing if today's entry already has content.**

## 5 · Report

**Terse nested bullets, one line each**: what carried, what did not and why, where Notion and the
repo disagreed, and the single thing worth starting with.

**Name the one thing to start with.** A list of six is a list nobody starts.

## What this skill will not do

- **Invent Goals.** If yesterday's `Next` was empty, say so — that is a finding about yesterday's
  close, not a gap to fill with plausible work.
- **Close or complete anything.** Opening a session records intent; it does not resolve work.
- **Overwrite a curated section** without asking.
