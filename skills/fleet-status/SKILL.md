---
name: fleet-status
description: Real status check across every Foreman-managed dark-factory repo — what's done, what's actively dispatching, what's genuinely blocked vs. just queued, and a duplicate sweep. Use whenever the user asks for a status check, "what's blocked", "what's coming up", or anything about Foreman's queue/fleet state.
version: 1.0.0
---

# /fleet-status

Codified from a real session (2026-09-09/10) that manually reconstructed this exact
procedure 6+ times — always the same steps, always found real, non-obvious things
(usage-limit false failures, duplicate re-opened issues, stale `backlogItems`
entries). Skill-worthy per the global "recurs ≥2-3 times" rule.

## What this answers, precisely

1. **What's been done** — recently merged work.
2. **What's coming up** — actively dispatching or queued (`factory:approved`), will
   resolve on its own without input.
3. **What's a genuine hard blocker** — requires the user specifically, nothing an
   agent can resolve (a missing credential, a physical device, an explicit
   decision only they can make) — distinct from "queued," which is NOT a blocker.
4. **What's stale/duplicate** — an open `needs-human` item whose underlying work is
   already merged elsewhere, caught before it wastes another dispatch.

**Never just report GitHub labels at face value.** A label is a claim; the run
ledger and the issue body are the evidence. This skill exists because label-only
reporting missed real things twice in one session (a "needs-human: The claude CLI
exited 1" that was actually a usage-limit-transient failure with a real merged PR
sitting behind it; two duplicate issues re-opened for already-shipped work).

## Procedure

### 1. Foreman's own state

```bash
cd <foreman repo path>   # find it: it's wherever ~/.foreman/repos.json's own entry points, or ask the user once and remember
node core/cli.js status
```

Note: daemon running/stopped, concurrency, memory capacity (a low worker count
here explains why queued items aren't dispatching yet — not a blocker, just
pacing), active runs, recent finished.

### 2. Enumerate every managed repo — don't hardcode a repo list

```bash
node core/cli.js repos
```

For EACH repo returned (not a fixed list from a prior session — repos get added),
in parallel where possible:

```bash
gh issue list --state open --label "factory:approved" --json number,title -R <owner>/<repo>
gh issue list --state open --label "factory:needs-human" --json number,title -R <owner>/<repo>
```

### 3. For every `needs-human` item, pull the REAL reason — never trust the label alone

From Foreman's repo, per item:

```js
const { listRuns } = await import('./core/state.js');
const r = listRuns().filter(x => x.repo === '<name>' && x.issue === <n>).slice(-1)[0];
// r.reason, r.code, r.branch, (r.progress||[]).slice(-2)
```

Classify each into exactly one bucket:

- **Transient, safe to re-approve** — `reason` is a generic subprocess failure
  (`"The claude CLI exited 1"`) AND the last progress line shows a usage-limit
  message (`"You've hit your session limit"`) or similar external interruption,
  not a real code/logic failure. Also: `"No PR found for the branch"` where the
  progress log's own summary claims a PR was opened — check `gh pr view <n>`
  directly; if the PR is real, this is a run-ledger branch-tracking gap, not a
  real failure. Re-approve (`gh issue edit <n> --remove-label factory:needs-human
  --add-label factory:approved`) after confirming, don't just relabel blindly.
- **Genuine needs-human** — a real ambiguity, contradiction, or design decision the
  run correctly stopped on (read the actual `progress` text — a well-behaved
  dispatched session explains WHY it stopped in its own words).
- **Likely duplicate** — see step 4 before deciding this one.

### 4. Duplicate sweep — check every open item's `Backlog-ID` against its source decision

Self-scheduling discovery (`backlog.js`) opens an issue per `docs/STATE.md`
`backlogItems` entry. A stale entry (one whose `opened`/removal flag didn't
survive a later merge — a real, observed bug class) can cause the SAME already-
shipped work to be re-opened as a new issue.

```bash
gh issue view <n> --json body -q '.body'   # read the "Backlog-ID: <id>" line
```

Then check that id's actual status in `docs/DECISIONS.md`/`docs/STATE.md`'s
`backlogItems` on the CURRENT default branch — if the decision entry says
`superseded`/`resolved`/is referenced as already-built by a later, merged PR,
this issue is a duplicate. Close it with a comment naming what it duplicates and
why (the stale-entry mechanism, so a human reading it later understands this
wasn't random):

```bash
gh issue edit <n> --remove-label "factory:needs-human"   # or factory:approved
gh issue close <n> --comment "Duplicate — <id> already <resolved/superseded by X>. Same stale-backlogItems-entry root cause as <precedent, if any>."
```

**If you find 2+ duplicates in one sweep**, say so explicitly rather than silently
closing each — it's a signal the stale-entry root cause itself deserves a look,
not just per-instance patching.

### 5. Hard-blocker scan — separate from "queued"

For each repo, check `docs/STATE.md`'s `blockers` field (YAML frontmatter) for
anything explicitly requiring the user (a credential, an external account, a
decision). Also recall (don't re-derive) any standing "needs the user physically"
items already known from prior sessions (a physical device pairing, an in-person
step) — these don't show up in `blockers` necessarily, they're just known context.

**The test for "hard blocker": would this resolve on its own if left alone?** If
yes (queued work, pacing, a re-approval you can do yourself) — it is NOT a
blocker, don't report it as one. If no (only the user can supply it) — it is.

### 6. Report

Terse-Output Contract ledger, four buckets:

- ✅ **Done** — real merges since the last check (title + repo + issue/PR#).
- 🔜 **Coming up** — actively dispatching now, or queued `factory:approved`
  (name what's pacing it — memory capacity, concurrency — if relevant).
- ⛔ **Needs you** — ONLY genuine hard blockers (step 5) and genuine needs-human
  decisions (step 3's second bucket). Never list queued/transient items here.
- 🗺️ **Roadmap** — named but not actively moving (a spec'd-but-undispatched
  feature, a design agreed but not built).

Note any duplicates closed and any stale-entry pattern flagged, even though
they're not part of the four buckets — they're a process finding, say so plainly.
