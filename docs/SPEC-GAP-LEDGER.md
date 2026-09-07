# Spec-Gap Ledger

> Cross-project. Every row is a category of thing a spec should have caught but didn't, discovered
> only after a post-ship follow-up pointed it out. Read by `/dark-factory` phase 2 (Requirements)
> on every future run, before that run's own FR/NFR pass is called complete. Append-only — a category
> is marked resolved-by-convention only after 3+ consecutive specs checked it with no repeat miss,
> never deleted outright. See `~/.claude/skills/dark-factory/SKILL.md` ("Spec-Gap Ledger" section)
> and `DARK-FACTORY-DESIGN.md` for how this fits the pipeline.

| Date | Project | What was missed | Category | Now checked in Phase 2 as | Resolved-by-convention |
|---|---|---|---|---|---|
| 2026-09-07 | nuwa-m3 | Reasoner (LLM) calls passed unit/integration/E2E tests but still failed on first real interactive use — a markdown-fence-wrapped response the tests never exercised | probabilistic-call-reliability | NFR: every LLM/probabilistic call names a real-E2E-with-the-real-model test (never fake-only), a bounded retry, and failure tracing — see dark-factory SKILL.md's NFR table | |
| 2026-09-07 | nuwa-m3 | A schema-valid, 200-OK LLM output was semantically wrong ('speeder' resolved to speedcubing, not motorcycle racing) because the prompt never stated the account's actual content domain | creative-domain-anchoring | NFR: every prompt generating creative/subjective output states the concrete domain/audience explicitly, and the spec names a judged example the reasoner must resolve correctly — see dark-factory SKILL.md's NFR table | |
