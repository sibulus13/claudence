---
name: ledger
description: Keep the fleet ledger (~/.claude/docs/fleet/LEDGER.md) - a terse per-day technical journal of what changed across all repos and the harness, why, and the commit refs, plus the living roadmap. Use at the end of a working session, when asked "update the ledger/roadmap", or "what changed on <date>".
---

# /ledger

1. Draft: `python ~/.claude/scripts/ledger_draft.py [YYYY-MM-DD]` (all commits that day, per repo).
2. Curate into `~/.claude/docs/fleet/LEDGER.md` under `## Days`, newest day first:
   - one row per meaningful change (merge commits that serve one goal), columns `project | change | why | ref | kind`;
   - kinds: feat, fix, move, release, decision, refactor, incident;
   - the why comes from the commit body, the decision log or the conversation; leave it out rather than guess;
   - add `Incidents` (what broke, fix, ref) and `Watch` (what could regress next and when) when there are any.
3. Update `## Roadmap` in place: move finished items out of Now/Next (they live on in the day row), add new ones with
   a spec/backlog link and an exit condition. Keep it high level; detail stays in the linked spec.
4. Commit the fleet repo: `git -C ~/.claude/docs/fleet add LEDGER.md && git -C ~/.claude/docs/fleet commit -m "ledger: <date>"`
   (local private repo; never copy its content into a public repo).
5. To answer "when did X change": grep the Days section, then follow the ref into the repo's history.
