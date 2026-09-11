# Harness Incident Log

Cross-project, not per-repo — mirrors `SPEC-GAP-LEDGER.md`'s placement/purpose, but for a
different failure class. The Spec-Gap Ledger tracks what a *spec* missed; this tracks what the
*harness/tooling* got wrong badly enough that a human had to manually revise Foreman-dispatched
work to complete or unblock it.

**Convention, adopted 2026-09-09 (direct user instruction):** every time a manual revision is
needed to complete or unblock Foreman/dark-factory-dispatched work, log it here — a lightweight
row, in the moment, not batched up. When the SAME CATEGORY (not the same literal instance) has
now happened **2-3+ times**, it graduates from a row to a full entry below with root cause,
frequency, severity, risk, and — required, not optional — **the patch applied at the source**,
not just a description of the workaround. Documenting without patching the source is an
incomplete entry.

**Tightened 2026-09-10 (direct user instruction):** the 2-3× threshold above governs when a row
graduates to a full RCA writeup (frequency/severity/risk analysis) — it does NOT gate whether a
manual fix gets a deterministic check. **Every manual intervention gets its own deterministic
gate at the time it's fixed, first occurrence, no threshold**, whenever one is feasible (a pure
function's behavior is checkable; "verify by eye" is not a gate). Only the depth of the RCA
scales with recurrence — the gate itself never waits for a pattern to repeat. If no gate is
feasible for a given fix (truly one-off, no generalizable check), say so explicitly in the row
rather than silently skipping it.

| Date | Project(s) | What happened | Category | Occurrence # | Manual fix applied |
|---|---|---|---|---|---|
| 2026-09-09 | nuwa | D109 claimed twice (D102-fix vs D103-fix branches); D110 claimed twice (concurrent-render note vs FR-13 closure) | id-collision | 1-2 | Renumbered the less-referenced entry, merge-time |
| 2026-09-09 | catwalk | D-22..25 (infra-status vs review-queue) + FR-26..30/NFR-8/9, same range, same day | id-collision | 3 | Renumbered review-queue's block to D-26..29/FR-31..35/NFR-10..11, docs + source/test files |
| 2026-09-09 | foreman | D35 + FR-22..25 (memory-observability vs notable-checkin), same range, same day | id-collision | 4 | Renumbered notable-checkin's block to D36/FR-26..28, docs + `core/notable.js`/its test file |
| 2026-09-09 | foreman | `repos add <path>` printed "Added: undefined" — `pick()` checked `key in opts` (true even for an explicit `undefined`), not `opts[key] !== undefined` | actor-completeness (opts-object) | 1 | Fixed `pick()`, regression test added (`D32`) |
| 2026-09-09 | catwalk | `vitest` had no `.git/**` exclusion — `pnpm test` from the main checkout also ran (and failed on) whatever unrelated, in-progress state existed in OTHER issues' worktrees | test-scope-leak | 1 | Added `**/.git/**` to `vitest.config.mts`'s exclude list |
| 2026-09-09 | catwalk | `#8`'s GitHub issue body was `foreman#8`'s entire spec, not its own — wrong from the very first `gh issue create` call (confirmed via `userContentEdits`: no edit history) | cross-repo-content-mixup | 1 | Restored the correct body from the original in-session diagnosis |
| 2026-09-09 | catwalk | `#16`'s dispatched PR said "closes #16" in its own progress narration but the actual PR body had no closing keyword — Foreman's `prClosesIssue` correctly flagged it; not a harness bug, a build-agent-output gap | pr-closing-keyword-narration-drift | 1 | Added `Closes #16` to the PR body directly; work itself was already verified complete |
| 2026-09-10 | nuwa, catwalk, foreman | A `backlogItems` entry already resolved (opened:true or removed) reappeared as `opened:false` in `docs/STATE.md` after a later, unrelated merge — self-scheduling discovery re-opened a duplicate GitHub issue for already-shipped work (nuwa#30 dup of #19, catwalk#25 dup of D-30/#23, foreman#31/#32 dup of #33/#36) | stale-backlogitems-resurrection | 3 | Closed each duplicate with an explanatory comment; root cause not yet patched at the source (see RCA-2) |
| 2026-09-10 | catwalk | `featureHistory[].specWrittenAt` (unquoted YAML timestamp, auto-cast to a native `Date`) crashed Catwalk's OWN STATE.md schema validation live on its own status page — the same bug class `updatedAt` already hit once, fixed via a dual-shape `isoString` parser, but never generalized to this sibling field | ungated-yaml-timestamp-field | 1 | Fixed the field; per the tightened convention above, ALSO added `schema-date-fields.ts`'s gate immediately (first occurrence, no threshold wait) — scans every YAML-parsed schema for any future `*At`/`*Date` field on a bare `z.string()`, not just this one instance |

---

## RCA-1: Same-day, same-repo D-number / FR-NFR-ID collisions (4 occurrences, 3 repos, 2026-09-09)

**Frequency:** 4 confirmed occurrences across nuwa, catwalk, and foreman in a single session,
spanning at least 12 individual colliding IDs total. Crosses the 2-3× threshold clearly — this is
a systemic pattern, not a one-off typo.

**Severity:** Medium. Never silently wrong — every occurrence was caught at merge time (git's own
3-way merge surfaces the textual collision, or a careful read catches the semantic one) and fixed
before landing. But each occurrence costs real manual time (renumbering across docs AND, twice,
actual source/test files) and the cost scales with concurrency: raising Foreman's `concurrency`
from 2→4 this same session directly increased how often two builds land on the same repo the same
day, which is exactly the precondition for this collision.

**Risk if unaddressed:** Grows worse, not better, as concurrency increases (which is the explicit
direction this session pushed tonight) and as more repos accumulate dispatch history. A future
occurrence that ISN'T caught at merge time (e.g. two builds that never actually conflict on the
same lines, so git auto-merges cleanly and a human doesn't happen to notice the ID reuse) would
leave `docs/TRACE.md` silently wrong — two different requirements under one ID, breaking exactly
the traceability spine the ID convention exists to provide.

**Root cause, traced not guessed:** Every dark-factory build-only session assigns its next
D-number/FR-NFR-ID by reading the CURRENT highest number already in the target doc, within its
own git worktree, at branch time. Two builds dispatched the same day against the same repo (now
routine at `concurrency: 4`) each see the SAME pre-dispatch high-water-mark, independently compute
the SAME "next" number, and never know about each other's allocation until their branches merge.
This is a classic check-then-act race — **structurally identical in shape to `D28`** (the
`docs/STATE.md` write race between a discovery tick and a dispatched build, already found and
partially fixed earlier this session), just manifesting on a second surface (ID assignment
instead of a field write) that hadn't been looked at through the same lens until now.

**Patch applied at the source:** `dark-factory/SKILL.md`'s Phase 3 ID-assignment convention
changed — see the skill edit in the same commit as this log entry. New D-numbers/FR-NFR-IDs
assigned during a `build-only` dispatch (the concurrency-prone path) are now **namespaced by
issue number** (`D<issue>-<n>`, e.g. `D16-1`), not drawn from a flat, cross-feature sequence —
eliminating the race by construction, the same way GitHub's own issue numbers never collide
without needing coordination, because the namespace itself (the issue number) is already
collision-free. Existing flat-numbered IDs are left as historical, not mass-renumbered — this
governs new IDs going forward only.

**Revisit-when:** After the new namespaced scheme has covered 5+ real `build-only` dispatches
across 2+ repos with zero collisions, consider it validated and drop this RCA's "still monitoring"
status to "resolved by convention," mirroring the Spec-Gap Ledger's own 3-consecutive-clean bar.

---

## RCA-2: stale `backlogItems` entries resurrected after merge, causing duplicate GitHub issues (3 occurrences, 3 repos, 2026-09-10)

**Frequency:** 3 confirmed occurrences (nuwa `#30` dup of `#19`, catwalk `#25` dup of `D-30`/`#23`,
foreman `#31`/`#32` dup of `#33`/`#36`) — the last one is actually 2 duplicate entries in a single
incident, so 4 individual duplicate issues total. Crosses the 2-3× threshold.

**Severity:** Low-medium. Each duplicate wastes one dispatch cycle (a real `claude -p` session
re-doing already-shipped work) and one human glance to notice + close it — never silently wrong,
always caught at the `needs-human`/status-check stage, but costs real time per occurrence and
recurs faster as backlog-discovery + concurrency both increase (the same growth dynamic as RCA-1).

**Risk if unaddressed:** Same shape as RCA-1's risk — grows with concurrency/discovery frequency,
not shrinks. A duplicate that happens to auto-merge cleanly (a `pre-traffic` repo, `full` autonomy,
no real conflict) would land REAL, redundant work on `master` with nobody noticing until a status
check happens to catch it, unlike a merge-conflict-shaped duplicate which announces itself.

**Root cause, traced not guessed:** All 3 occurrences trace to the SAME mechanism — a
`docs/STATE.md`-merge-conflict resolution (mine, this same session, resolving unrelated PRs) that
took one side's full `backlogItems` block as the base (`git show origin/master:docs/STATE.md >
docs/STATE.md`, the exact technique used throughout tonight's merge-resolution work) without
verifying every individual entry's `opened`/removed status was still the MOST CURRENT one across
BOTH sides. When the branch being merged had already correctly resolved an entry (marked
`opened:true` or removed it outright) but the chosen base's snapshot predated that fix, the stale,
still-`opened:false` version silently came back — exactly the same class of "whole-file replacement
without per-entry reconciliation" mistake as RCA-1's ID collisions, but on a different field
(`backlogItems`' `opened` flag instead of a D-number/FR-number). Self-scheduling discovery
(`backlog.js`) then did exactly what it's designed to do — opened a fresh issue for an
`opened:false` entry — correctly, given what it read; the data it read was wrong, not its logic.

**This RCA's root cause is MY OWN merge-resolution technique from this same session, not a
pre-existing bug in Foreman/dark-factory** — worth stating plainly rather than attributing it to
"the harness" in the abstract. Every whole-file `docs/STATE.md`/`docs/DECISIONS.md` conflict
resolved tonight used "take one side's full snapshot, append the other side's genuinely-new
content" — which is correct for append-only sections (`featureHistory`, `PHASE-LOG.jsonl`) but
WRONG for `backlogItems`, a section that gets mutated in place (`opened: false → true`, or removed
entirely), not just appended to.

**Patch applied at the source:** none yet — this entry is filed with root cause established but the
fix not yet built, per this log's own standing rule that documentation without a patch is
incomplete; treat that rule as still open against this entry, not satisfied by it. Proposed fix,
for whoever picks this up: a merge-conflict resolution touching `docs/STATE.md`'s `backlogItems`
must reconcile PER-ENTRY (by `id`), preferring whichever side has the more-resolved state
(`opened:true` or removed beats `opened:false`) rather than picking one side's whole block — the
same per-entry-reconciliation principle RCA-1's ID-namespacing fix applies to ID assignment, applied
here to entry status instead. A deterministic gate is harder for this one than RCA-1's (would need
to cross-reference live GitHub issue state, not just parse the file in isolation) — likely a
`fleet-status` skill responsibility (its duplicate-sweep step, added the same session) rather than
a per-repo test, since detecting "this backlogItems entry's real-world issue is already closed"
inherently needs live `gh` state, not just the file.

**Revisit-when:** The next time a `docs/STATE.md` merge conflict touches `backlogItems`, apply the
per-entry reconciliation manually and note whether it would have caught this; after 2-3 clean
manual applications, consider whether the pattern is regular enough to script directly into the
merge-resolution step.
