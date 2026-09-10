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

| Date | Project(s) | What happened | Category | Occurrence # | Manual fix applied |
|---|---|---|---|---|---|
| 2026-09-09 | nuwa | D109 claimed twice (D102-fix vs D103-fix branches); D110 claimed twice (concurrent-render note vs FR-13 closure) | id-collision | 1-2 | Renumbered the less-referenced entry, merge-time |
| 2026-09-09 | catwalk | D-22..25 (infra-status vs review-queue) + FR-26..30/NFR-8/9, same range, same day | id-collision | 3 | Renumbered review-queue's block to D-26..29/FR-31..35/NFR-10..11, docs + source/test files |
| 2026-09-09 | foreman | D35 + FR-22..25 (memory-observability vs notable-checkin), same range, same day | id-collision | 4 | Renumbered notable-checkin's block to D36/FR-26..28, docs + `core/notable.js`/its test file |
| 2026-09-09 | foreman | `repos add <path>` printed "Added: undefined" — `pick()` checked `key in opts` (true even for an explicit `undefined`), not `opts[key] !== undefined` | actor-completeness (opts-object) | 1 | Fixed `pick()`, regression test added (`D32`) |
| 2026-09-09 | catwalk | `vitest` had no `.git/**` exclusion — `pnpm test` from the main checkout also ran (and failed on) whatever unrelated, in-progress state existed in OTHER issues' worktrees | test-scope-leak | 1 | Added `**/.git/**` to `vitest.config.mts`'s exclude list |
| 2026-09-09 | catwalk | `#8`'s GitHub issue body was `foreman#8`'s entire spec, not its own — wrong from the very first `gh issue create` call (confirmed via `userContentEdits`: no edit history) | cross-repo-content-mixup | 1 | Restored the correct body from the original in-session diagnosis |
| 2026-09-09 | catwalk | `#16`'s dispatched PR said "closes #16" in its own progress narration but the actual PR body had no closing keyword — Foreman's `prClosesIssue` correctly flagged it; not a harness bug, a build-agent-output gap | pr-closing-keyword-narration-drift | 1 | Added `Closes #16` to the PR body directly; work itself was already verified complete |

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
