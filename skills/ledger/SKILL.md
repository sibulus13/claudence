---
name: ledger
description: Keep the fleet ledger ($FLEET_DOCS/LEDGER.md; FLEET_DOCS defaults to D:/repo/docs) - a terse per-day technical journal of what changed across all repos and the harness, why, and the commit refs, plus the living roadmap. Use at the end of a working session, when asked "update the ledger/roadmap", or "what changed on <date>".
---

# /ledger

1. Draft: a nightly job leaves `$FLEET_DOCS/drafts/<date>.md` for each unledgered day (SessionStart says "ledger draft for <date> pending"); otherwise run `python ~/.claude/scripts/ledger_draft.py [YYYY-MM-DD]` (all commits that day, per repo). Delete a draft file once its day is in the ledger.
2. Curate into `$FLEET_DOCS/LEDGER.md` under `## Days`, newest day first:
   - one row per meaningful change (merge commits that serve one goal), columns `project | change | why | ref | kind`;
   - kinds: feat, fix, move, release, decision, refactor, incident;
   - the why comes from the commit body, the decision log or the conversation; leave it out rather than guess;
   - add `Incidents` (what broke, fix, ref) and `Watch` (what could regress next and when) when there are any.
3. Update `## Roadmap` in place: move finished items out of Now/Next (they live on in the day row), add new ones with
   a spec/backlog link and an exit condition. Keep it high level; detail stays in the linked spec.
3a. Reconcile the session task list (Claude Code keeps it in `~/.claude/tasks/<session-id>/*.json`; nothing else
   reads it, so open tasks die with the session). Every `pending` or `in_progress` task ends as `completed`, or is
   carried: name its durable home (a `docs/work/<id>` item, a Roadmap row, or `docs/capabilities/INDEX.md`'s build
   order), add that home if missing, then delete the task. A task that exists only in the list is a defect: the list
   is a view of this session's work, never the record (owner, 2026-11-03).
4. Commit the fleet repo: `git -C "$FLEET_DOCS" add LEDGER.md && git -C "$FLEET_DOCS" commit -m "ledger: <date>"`
   (local private repo; never copy its content into a public repo).
5. To answer "when did X change": grep the Days section, then follow the ref into the repo's history.
