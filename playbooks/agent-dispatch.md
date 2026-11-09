# Agent dispatch playbook (cue: Agent, Workflow, /orchestrate)
- Order: named skill > role flow (`/orchestrate`) > `cycle` workflow (`~/.claude/workflows/cycle.js`) > named agent (researcher, designer, implementer, reviewer, each in the mode the brief names: `agents/README.md`) > general-purpose (say why).
- Name a persona instead of `general-purpose`: it starts about 38k tokens lighter (`D:/repo/docs/reports/2026-11-07-context-and-reply-minimisation.md`).
- Hand off only when the workflow is approved and the spec is well laid out. Work that is ambiguous but told to start stays in the main session until it is clear. A reviewer still verifies either way (owner 2026-11-06).
- A hand-off is a unit, not one agent: research and implementation each get an independent reviewer, and the unit ends in one named ending (`done`, `needs-guidance`, `needs-approval`, `blocked`, `exhausted`, `dropped`). Until `docs/work/workflow-units` is built, run it by hand: at most 2 fix rounds, then a verify review.
- Every unit closes with a docs step: the author updates what the work made stale, and the reviewer checks it (owner 2026-11-06).
- Before giving an agent a new rule, check it against the rules it touches; a conflict found in review costs a round.
- Set a work item's risk flags at draft, before any build; the builder never decides its own tier.
- Estimate a run from a small sample before starting it. Over 30 minutes, or crossing the owner's 22:00 sleep window, it must be resumable from saved results, and it moves to a detached worker once one exists: the agent ends and a fresh one picks up the result (`$FLEET_DOCS/SAFE_RESUME_POLICY.md`).
- Before any fan-out, pin per stage: persona (its frontmatter sets model and effort), input/output contract, the exact gate command (interpreter included), worktree isolation, and an independent reviewer. One verdict set everywhere: `pass` / `fix-first` / `block` (a shared enum in `Lib/contracts` lands with work item `review-records`); one rating scale: R / F / H (`~/.claude/GLOSSARY.md`). The author never verifies their own work.
- Tag every dispatch description with its stage and work item, e.g. `[design-review review-records]`, so per-stage cost can be totalled from transcripts.
- A missing hand-back (an agent that finished without a report) gets one request to resend; never assume its result.
- Subagent proposals to change governance (CLAUDE.md, personas, rules) come back as proposals; the parent decides as its own decision, never as the agent's instruction.
- `isolation: worktree` cuts from the session's repo. For another repo, `git -C <repo> worktree add` first and dispatch without isolation.
- Give every agent a deliverable and a stop condition. Subagents never edit governance or land on main (enforced: hooks/guard.py); the parent reviews and commits.
- Tell reviewers to flag only gaps that affect correctness or the stated requirements (they over-report otherwise).
- Separate repos need no worktree; same-repo parallel writers each get one.

## Models, effort and sub-delegation (owner 2026-11-03, D52)
- Personas and their models live in one registry, `~/.claude/agents/README.md`. Researcher, designer and
  reviewer run on opus (D64, D65), the implementer on sonnet (owner 2026-11-08); set `effort` on every dispatch, medium by
  default, high for enforcement, security or contract T2 design reviews, decision mode and security mode on
  `revenue`, low for docs-only verifies.
- Every persona may spawn subagents for research and context, up to its own model; read-only personas spawn only
  read-only types (`researcher`, `Explore`, `claude-code-guide`).

## Design closes before lock (owner, 2026-11-02; ADR `~/.claude/docs/adr/0001-review-records-gate-lock-and-ship.md`)
- **v3 items (`standard: 3`) scale by tier** (`~/.claude/skills/dark-factory/SPEC-STANDARD-V3.md` § Tiers, D38-D40):
  - T1 feature or unflagged bugfix: draft -> red tests -> build -> code review. No adversary, no design review.
    The drafter still reads the existing specs and the code for the area first and cites them in the draft.
  - T2 feature or flagged bugfix: probe first (existing specs, the code and a dated web survey of industry practice,
    then the reviewer in adversary mode on the problem and a real-input run, saved to `evidence/probe.md`; it reads every state machine the change touches and runs each new parser on its real
    corpus), then draft -> one design review -> red tests -> build -> code review. With 2+ flags, add
    the security reviewer (the reviewer in security mode) in parallel.
  - Each tier has an agent-stage cap (T1 and bugfix 4, flagged bugfix 5, T2 9). Hitting it stops the item as
    `repair-budget-exhausted`; it is never extended.
- v2 items: designer draft (with its Outcome inventory) -> adversary pass (the reviewer in adversary mode) -> the designer
  adds or rejects each row with a reason -> reviewer in design mode. No exemption for small work.
- **Who locks:** the parent session, and only by committing the `draft` → `spec-locked` move while a fresh `pass`
  design (or verify) record sits in `reviews/`. The designer never locks; the parent never locks content changed
  after its last review. A dark-factory pre-traffic GO is that record, not an automatic lock.
- Freshness is checked at exactly two moves: the lock (a design or verify `pass`) and `building` → `shipped` (a code
  or verify `pass`). Between them, spec edits are free; nobody re-checks freshness at rest or before a dispatch.

## Review records (ADR `~/.claude/docs/adr/0001-review-records-gate-lock-and-ship.md`)
- The format, the hash and the freshness rule have ONE definition: `~/.claude/docs/work/review-records/components.md`
  (FR-1 hash, FR-4 report, FR-6 file name `reviews/<YYYY-MM-DD>-<kind>-<hash8>.md` and keys, FR-8 freshness). Never
  restate them here.
- **Every review brief carries the item's hash**, from `python ~/.claude/scripts/review_record.py hash --item
  docs/work/<id>` after staging the item, and for a code review the commit under review. `review_record.py hash` and
  review-records FR-1 are the only hash rule; never compute or restate it elsewhere. The reviewer's report must echo
  it as a line `REVIEWED: sha256:<hex>` (and `REVIEWED-COMMIT: <sha>`); the record is refused otherwise.
- **Write the review record the moment a report lands, before any fix**: save the report as a UTF-8 file and run
  `python ~/.claude/scripts/review_record.py write --item docs/work/<id> --kind <design|code|verify> --reviewer
  "<agent run>" --report <file> [--verifies <record>]`. The commit gate then enforces freshness at lock and ship.

## Lock before build; scope changes are new work items (owner, 2026-10-31)
- Dispatch an implementer only against a work item at `spec-locked` or `building` (the implementer persona refuses
  otherwise). Never build while its spec is still under review.
- A new requirement that arrives mid-build becomes a NEW work item queued behind the current one. It is never an
  edit to the running build, because each edit invalidates work already done and resets review.
- Split by the nesting rule before dispatch (more than 15 ACs means children). One implementer gets one child's
  context pack, not the whole tree.
- **Design: one shot** (owner 2026-11-03, D60). Probe and adversary, then one draft; a design check only for flagged
  T2 items or `public`/`revenue` repos (one parallel pass, one fix, no verify); then build. Design findings that do not
  block implementation are build amendments, never another design round.
- **Only breaking findings loop** (owner rule 2026-11-02, D36; on the design side superseded by D60). A review blocks only on what breaks the application
  (code review) or makes the build impossible or wrong-headed (design review); every other finding is recorded and
  goes to the backlog or a build-time spec amendment (D37). A breaking finding is a **stage miss**: classify its cause
  (context not loaded, spec quality, test strength, approach), fix that cause upstream (a probe, a checker rule or a
  persona line, logged in `$FLEET_DOCS/RETRO-QUEUE.md`), then the stage gets one re-attempt; a second miss goes to the
  designer in decision mode. The tracked metric is first-attempt pass rate per stage.
- Review budget, every size (GLOSSARY.md: Review budget), counted **per work item per review kind** (the design
  review and the code review each have their own): one review, up to the unit's limit of fix rounds (default 2, D68), then one verify review of only
  the fix diff. A `fix-first` from that verify review is the second one: a stop that goes to the designer in decision
  mode (`agents/designer.md`), who decides between redesign at another layer and cutting scope. This replaces the
  size-scaled 1/2/3 budget in `CYCLE.md`.
- Why: the spec-gate checker took 6+ review rounds on 2026-10-31. The spec grew during the build (v2 merge, work
  breakdown, context packs, off-the-shelf validators, exemption policy) inside one 46-rule work item.

## Feed review findings back into design (owner, 2026-10-31)
- Every review (in the cycle workflow or a direct reviewer agent) returns findings tagged with a gap category and a class.
  The parent appends the design- and spec-class ones to `~/.claude/docs/SPEC-GAP-LEDGER.md`: a new category gets a new row, and a
  repeat adds evidence to the existing row.
- Escape = a design-class finding in a category the item's `## Gap-ledger check` claimed. The goal is zero escapes:
  review finds only implementation slips, never design gaps.
- A category with 2+ escapes changes the designer persona or the standard (a checklist row or a checker rule), via
  `/retrospect`.

## Design briefs carry the survey verbatim (owner, 2026-10-31)
- A design brief includes the fleet survey's file:line findings for the role, and the web research sources,
  copied verbatim, never paraphrased. The Spindle specs missed Foreman's working worktree code because the
  brief summarized it away.
