# Spec-Gap Ledger

> Cross-project. Every row is a category of thing a spec should have caught the first time but
> didn't — discovered either (a) after a post-ship follow-up pointed it out, or (b) recurring
> across multiple Phase 2.5 review rounds on the same or different projects (broadened 2026-09-08:
> the underlying failure is the same either way — Phase 2 not asking the right question upfront —
> a post-ship miss and a review-time recurrence are just two different discovery moments for it).
> Read by `/dark-factory` phase 2 (Requirements) on every future run, before that run's own FR/NFR
> pass is called complete. Append-only — a category is marked resolved-by-convention only after 3+
> consecutive specs checked it with no repeat miss, never deleted outright. See
> `~/.claude/skills/dark-factory/SKILL.md` ("Spec-Gap Ledger" section) and `DARK-FACTORY-DESIGN.md`
> for how this fits the pipeline.

| Date | Project | What was missed | Category | Now checked in Phase 2 as | Resolved-by-convention |
|---|---|---|---|---|---|
| 2026-09-07 | nuwa-m3 | Reasoner (LLM) calls passed unit/integration/E2E tests but still failed on first real interactive use — a markdown-fence-wrapped response the tests never exercised | probabilistic-call-reliability | NFR: every LLM/probabilistic call names a real-E2E-with-the-real-model test (never fake-only), a bounded retry, and failure tracing — see dark-factory SKILL.md's NFR table | |
| 2026-09-07 | nuwa-m3 | A schema-valid, 200-OK LLM output was semantically wrong ('speeder' resolved to speedcubing, not motorcycle racing) because the prompt never stated the account's actual content domain | creative-domain-anchoring | NFR: every prompt generating creative/subjective output states the concrete domain/audience explicitly, and the spec names a judged example the reasoner must resolve correctly — see dark-factory SKILL.md's NFR table | |
| 2026-09-08 | nuwa-m3 (Design Variants FR-21..26) | The SAME failure recurred 4 times across rounds 1/4/4→5 of one feature's review: a technical claim (a "registry" is extensible, `_store` persists to disk, a field list is exhaustive, N calls run "in parallel") stated as fact in the FR/NFR text without ever being checked against the real function signature/schema/execution model it described | asserted-not-verified-claim | NFR/FR authoring rule: any claim about a DEPENDENCY's behavior (persistence, concurrency safety, exhaustiveness of a field/case list, extensibility of an existing mechanism) must name the specific line/function it was verified against, or be stated as unverified — a claim with no verification pointer is the smell | |
