# Spec-Diff Ledger — consolidation record

> Cross-project. Every row is one run of `/dark-factory consolidate` — what range it diffed,
> where it started from (the `Spec-Baseline`-tagged commit, or an honest "none" if the range
> predates that convention, 2026-09-08), and what it produced. This is the high-water mark: a
> repeat run on the same project/range starts from its own `Consolidated through commit`, not
> from the original baseline again. See `~/.claude/skills/dark-factory/SKILL.md`'s
> "`consolidate` mode" section for the full procedure, and `docs/SPEC-GAP-LEDGER.md` for where
> recurring-category findings actually land.

| Date | Project | FR/NFR range | Baseline commit | Consolidated through commit | Rounds covered | Ledger rows produced | Notes |
|---|---|---|---|---|---|---|---|
| 2026-09-08 | nuwa-m3 | FR-21..FR-26 (Design Variants & Composition) | none — pre-convention, approximated (earliest commit touching the range, `14cac41`, already bundles the original FR-21..26 text with round-4's fixes — no real pre-review state survives in git) | `eea44ba` | 4, 5 | `asserted-not-verified-claim` (Spec-Gap Ledger) + a matching Phase 2 commit-message/verification-pointer rule (this skill file) | First real run of this mode. Confirms the skill's own warning: every feature slice built the same session this convention was written predates it, so no clean baseline exists for any of them (Stage 2/3, Correction Layer, Audio/Rhythm, Design Variants all bundle spec+review in one commit). Approximated from the earliest touching commit instead of fabricating one. Round 6 (in flight) will be the first pass that lands as its own separate, cleanly-diffable commit going forward, per the new Phase 2 rule. |
