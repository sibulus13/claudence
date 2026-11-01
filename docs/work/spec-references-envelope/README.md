---
id: spec-references-envelope
type: feature
status: draft
touches: [harness]
layers:
  architecture: none
  component: modified
  functional: added
  data: none
created: "2026-10-31"
owner: harness
lifecycle: false
---
# Work-Item Standard: every spec cites prior art (References) and states its Operating envelope

```mermaid
flowchart TD
  D[Designer or owner] --> R[README: References and Operating envelope]
  R --> K[spec_check.py CK-4, CK-47..49]
  G[gen_heading_config.py] --> J[work-item.headings.v2.json]
  J --> K
  S[WORK-ITEM-STANDARD.md heading table] --> G
  C[spec_gate.py: every staged work-item README at spec-locked, building or shipped] -->|--require-sections| K
  RV[reviewer: rates findings against the envelope] --> R
```

## References

Owner decision 2026-10-31: this item dogfoods the rule it introduces, so it starts with References and then Operating envelope. The Foreman line numbers were verified against the files on 2026-10-31 (`createWorktree` at worktrees.js:129, `removeWorktree` at :151, `checkpointWorktree` at checkpoint.js:116, `recoverInterruptedRun` at :174, the `--squash` args at merge.js:135). The two quoted sentences in the first two rows are the owner's wording from the brief, kept verbatim; the 2026-10-31 ledger rows nearest to them are 40 and 41 (branch-conventions and Spindle escapes), which do not contain those sentences literally (see OQ-7).

### Local

| Source (file:line) | Status (working / partial / broken) | What it shows | Decision (extract / wrap / replace / ignore) + reason |
|---|---|---|---|
| C:/Users/Michael/.claude/docs/SPEC-GAP-LEDGER.md:29-41 | working | Today's escapes, the rows dated 2026-10-31. Branch-conventions reviews kept finding cases outside the real setup. | extract: the escape categories feed the Gap-ledger check table and the review rule; there is no code to lift |
| D:/repo/Factory/foreman/core/worktrees.js:129 D:/repo/Factory/foreman/core/worktrees.js:151 D:/repo/Factory/foreman/core/checkpoint.js:116 D:/repo/Factory/foreman/core/checkpoint.js:174 D:/repo/Factory/foreman/core/merge.js:135 | working | The Spindle specs never cited Foreman's working worktree code at D:/repo/Factory/foreman/core/worktrees.js (createWorktree :129, removeWorktree :151), checkpoint.js :116/:174, and merge.js :135 (`gh pr merge --squash`). | ignore: it is the evidence for why References is needed; this item does not touch worktrees |
| C:/Users/Michael/.claude/skills/dark-factory/WORK-ITEM-STANDARD.md:62-86 | working | The CK-4 heading table and the L0 heading lists. CK-19 (placeholders) is at :352 and CK-4 at :337; the checker count CK-1..CK-46 is at :23 and the tier lists at :326. | wrap: add the two headings, the leading/optional notation, CK-47..49, the migration rule and the reviewer rating section; update :23 and :326 |
| C:/Users/Michael/.claude/contracts/work-item.headings.v2.json:3-21 | working | The generated heading config (l0 full and lite lists), built by scripts/gen_heading_config.py:31-39 (readme_entry, which already extracts the conditional notation) and scripts/gen_heading_config.py:55-71 (generate). | wrap: new keys leading and per-type optional, produced by the same generator, no second heading config |
| C:/Users/Michael/.claude/scripts/spec_check.py:361-381 | working | required_headings (CK-4 input), ck4 at :429, ck5 at :440 (the table-row check pattern), ck19 at :610, the tier sets at :51-56, the RULES list at :711. | wrap: new rules ck47, ck48, ck49 follow ck5's shape; required_headings gains the optional filter; STATIC gains CK-47, CK-48 and CK-49 |
| C:/Users/Michael/.claude/scripts/work_item_md.py:138-239 | working | The pydantic Row base, CapRow/NfrRow/AcRow models with per-field rule ids, and parse_rows (exact-header check, one finding per bad cell). EVIDENCE_TOKEN is defined at scripts/work_item_md.py:18. | wrap: three new Row subclasses, parse_rows unchanged; EVIDENCE_TOKEN imported for the observed-pointer rule, not re-spelled |
| C:/Users/Michael/.claude/contracts/work-item.v2.json:31 | partial | The frontmatter schema, the source of the CK-1 rules; `created` is checked by a pattern only, so `2026-13-45` passes (the check lives in scripts/work_item_schema.py:31-34, which maps schema errors to rule ids). | wrap: add a real-date check at this layer, reported as CK-1 |
| C:/Users/Michael/.claude/scripts/fleet_paths.py:13 | working | REPO_ROOT, the one owner of the fleet tree root (env FLEET_ROOT, else D:/repo). | extract: the AC-9 walk roots derive from it; no path is spelled twice |
| C:/Users/Michael/.claude/scripts/spec_gate.py:1 | working | The commit-msg gate reads the staged index (IndexTree) for the cited work item; reading the HEAD version of a README is new. | extend: check every staged work-item README by the invariant below, before its branch and merge early returns |
| D:/repo/Factory/catwalk/src/lib/work-items.ts:107-137 | working | Catwalk reads only the experiment headings Hypothesis, Metric, Verdict or Result, Promoted to; every other H2 is ignored, case-insensitive. | ignore: no Catwalk change needed; References and Operating envelope collide with none of its aliases |
| C:/Users/Michael/.claude/agents/reviewer.md:53-55 | partial | The rating rule (and the citation-opening sentence at reviewer.md:50-52) already exists in the reviewer and designer agent text (agents/designer.md:30-34), with no standard, template or checker behind it. Searched C:/Users/Michael/.claude/scripts, contracts, skills and tests for `Operating envelope` and `## References` (case-sensitive): no match. | extract: the standard becomes the source of the wording; the agent text gets one added sentence (citation spot-check) and a test keeps both consistent |

### Web

| Source (URL) | Date checked | What it shows | Decision |
|---|---|---|---|
| https://docs.arc42.org/section-2/ | 2026-10-31 | arc42 section 2 Constraints: a plain table of constraints with explanations (technical, organizational, conventions). No assumption, observation or fail-safe column. | ignore: constraints are imposed from outside; an assumption here is observed and can break. Only the plain-table form is reused |
| https://docs.arc42.org/section-3/ | 2026-10-31 | arc42 section 3 Context and Scope. 0 matches for "assum" on the page; no references section. | ignore: nothing to borrow |
| https://docs.arc42.org/section-11/ | 2026-10-31 | arc42 section 11 Risks and Technical Debt. 0 matches for "assum"; risks are listed, not tied to an observation or a fail-safe outcome. | ignore: closest in intent, but has no observed-not-hoped column or closed outcome vocabulary |
| https://raw.githubusercontent.com/adr/madr/main/template/adr-template.md | 2026-10-31 | MADR template: Decision Drivers, Considered Options, Pros and Cons. 0 matches for "assum" and for "references". | ignore: options are already covered by Trade-offs |
| https://www.rfc-editor.org/rfc/rfc7322 | 2026-10-31 | RFC Style Guide: a References section is a citation list. 0 matches for "assum". | ignore: a bare citation list has no status or decision column |
| https://raw.githubusercontent.com/DavidAnson/markdownlint/main/doc/md043.md | 2026-10-31 | MD043 headings can use the wildcards star, plus and question mark, and count headings of every level. | wrap: keep MD043 for presence (already used); order is checked in Python over level-2 headings because H3s under References break adjacency |

## Operating envelope

| Assumption | How it is observed (not hoped) | If violated |
|---|---|---|
| Tables are read by markdown-it-py with tables enabled, so the new tables are real tables in the token stream | AC-3: a References section whose tables do not parse yields zero tables and a named CK-48 finding | refuse: the checker reports CK-48 or CK-49 and exits 1; it never treats an unparsed table as a pass |
| The standard's heading table is the only source of the required headings | AC-1 and the gate command `python scripts/gen_heading_config.py --check` compare the committed JSON with a fresh generation | refuse: the gate fails on a stale config; the committed JSON is never hand-edited to pass |
| `created` is a real date (a schema pattern alone accepts 2026-13-45) | AC-8: the schema layer `contracts/work-item.v2.json:31` plus a `date.fromisoformat` check report CK-1 before any other rule runs | refuse: CK-1 stops the run |
| The staged state is the authoritative fact: every staged work-item README whose status (read with the yaml Item loader) is spec-locked, building or shipped must carry valid References and Operating envelope sections, on every branch and during merges and rebases; the one exception is a README whose HEAD version has the same status and neither section (an untouched historical spec), which only warns; a status outside the enum, or an unreadable staged README, rejects | AC-8: real commits in a temp repo, on main and on a feature branch, including amend, creation at shipped, quoted status, and an untouched historical README | refuse: the commit is rejected; the historical exception only warns |
| The node helper (markdownlint) is available for CK-4 | existing FR-5 of spec-gate-checker at docs/work/spec-gate-checker/components.md:29: a missing or timed-out helper is a ToolError | refuse: exit 2, the gate rejects; CK-4 is never skipped |
| A cited local path:line resolves to a file with at least that many lines | AC-5: CK-48 resolves every cited token at check time (Windows and POSIX forms) | refuse: CK-48 error at spec-locked and building, exit 1 |
| A shipped item's cited lines may later drift or vanish as the cited code changes | AC-5: the same resolution runs at shipped and is downgraded to a warning | flag: a warn line names the token; no block on a shipped item |
| A cited line says what its row claims (resolution proves only that the line exists) | the reviewer sentence at agents/reviewer.md:50-52, asserted in AC-10 | refuse: the reviewer rates it R (asserted-not-verified-claim), which blocks the lock |

## Purpose
Specs keep escaping review because the author never looked at working code that already exists and never said which conditions the design relies on. Today's ledger rows show it: the Spindle specs rebuilt worktree handling without citing Foreman's working code, and branch-conventions reviews kept finding cases outside the real setup. This item makes two README sections required and machine-checked: References (prior art in the fleet and on the web, each with a decision, local citations resolved) and Operating envelope (each assumption, a typed pointer to how it is observed, and a fail-safe outcome if it breaks). The rule binds on the commit, the authoritative fact: every staged work-item README at spec-locked, building or shipped must carry valid sections, on every branch, or the spec gate rejects the commit. An untouched historical spec (HEAD has the same status and neither section) only warns, so nothing finished has to be rewritten; once a spec has the sections it can never lose them. The Spindle drafts (branch-conventions, claim-registry, worktree-reaper) therefore add both sections when they lock.

## Non-goals
- Judging whether a decision or an observation is a good one (design review does); the `If violated` cell is checked syntactically only (its first word and a non-empty detail), never for whether the outcome is really safe.
- Verifying that a cited line says what its row claims (the reviewer spot-checks; AC-10).
- Verifying web citations (the reviewer spot-checks a sample).
- Rules CK-27 and later (multi-package; reserved by the standard).
- Rewriting the existing work items.
- Changing Catwalk (it ignores unknown headings).

## Capabilities
| CAP | Statement |
|---|---|
| CAP-1 | The service must require a `## References` section in the README of every work item type |
| CAP-2 | The service must require a `## Operating envelope` section in feature, integration, data-collection and refactor items, and accept it as optional in bugfix, research and experiment items |
| CAP-3 | The service must reject a README whose References and Operating envelope sections are not the first sections after Overview, in that order |
| CAP-4 | The service must reject a References or Operating envelope table whose header, row count or row cells break the rules, naming the rule and the cell |
| CAP-5 | The service must reject any commit, on any branch and docs-only included, in which a staged work-item README at spec-locked, building or shipped lacks valid References and Operating envelope sections, unless its HEAD version has the same status and neither section |
| CAP-6 | The service must tell the reviewer to rate a finding that needs an envelope assumption broken as F, unless the assumption can break silently, in which case a cheap detector is required, and to open each cited local line |
| CAP-7 | The user can start a new item from the README templates and get both sections with the exact table headers |
| CAP-8 | The service must reject a cited local path:line that does not resolve to an existing file with at least that many lines |
| CAP-9 | The service must not turn any existing work item under D:/repo and ~/.claude from passing to failing when it is checked standalone |

## Non-functional requirements
None.

## Trade-offs
| Option | Latency | Cost | Maintenance | Extensibility | Refactorability | Verdict |
|---|---|---|---|---|---|---|
| Extend the existing pipeline: heading table, generated config, Row models, three new rules, bound on the staged state of every work-item README | low: same parse, under 50 ms extra | low | low: one source for headings, one model per table | high: a new section is a table row plus a Row model | high | chosen |
| A separate References/envelope linter script | low | medium | high: a second parser, a second config, a second place to drift | low | low | rejected: a parallel mechanism, which the owner ruled out |
| Keep it as agent instruction text only (status quo in the reviewer and designer agents) | none | low | medium | low | medium | rejected: nothing fails when a section is missing, which is how today's escapes happened |
| Legacy by the `created` date or a `legacy-l0: true` flag in the item | low | low | high: the author edits the fact that grants the exemption | low | low | rejected: back-dating or setting the flag on a new item dodges the rule |
| A frozen, generated list of grandfathered items | low | low | high: regenerating the list silently re-grandfathers new items (review round 2, NEW-2) | low | low | rejected: still an editable proxy; the staged README itself is the authoritative fact |

## Patterns applied
| Pattern | Where | Why |
|---|---|---|
| single source, generated config | heading table to work-item.headings.v2.json to spec_check | a hand-copied heading list drifts (hand-copied-enum) |
| closed vocabulary validated by a model | LocalRefRow, WebRefRow, EnvelopeRow | a free-text cell cannot be checked |
| enforce an invariant on the staged state (observe, never predict a delta) | spec_gate.py checks every staged work-item README | a delta rule had bypasses (entry at shipped, amend, branches, quoted status); a state invariant has none of them |

## Components chosen
| Need | Chosen (off the shelf) | Rejected | Why rejected |
|---|---|---|---|
| table row validation | the existing pydantic Row models and parse_rows | a new regex linter | a second mechanism |
| heading presence | markdownlint MD043 through the existing spec_lint.mjs | a hand-rolled scan | cannot tell a heading from a code fence |
| heading order | a Python check over the existing Doc.headings (built in-house: MD043 wildcards cannot express adjacency when H3s sit under References) | MD043 sequence with wildcards | a star between the two headings would also accept an unrelated H2 there |
| date validity | the standard library `datetime.date.fromisoformat` behind the existing JSON Schema pattern | JSON Schema `format: date` alone | needs a format checker switched on in the validator, and the pattern already exists |
| spec section wording | none off the shelf: arc42 sections 2, 3, 11, the MADR template and RFC 7322 were checked on 2026-10-31 and none has an assumptions or observed-not-hoped section | borrowing arc42 Constraints | constraints are fixed from outside, assumptions are observed and can break |

## Gate plan
| Risk | Kind (deterministic / qualitative) | Check | Blocking / advisory |
|---|---|---|---|
| a new rule misjudges a fixture | deterministic | python -m pytest tests/test_spec_references_envelope.py: every row of every AC fixtures table in functional.md is one parametrized case, asserting its message substring | blocking |
| the committed heading config is stale | deterministic | python scripts/gen_heading_config.py --check | blocking |
| the change breaks an existing item | deterministic | AC-9, a one-shot build-time gate: spec_check over every README under D:/repo/*/*/docs/work, D:/repo/*/docs/work and ~/.claude/docs/work, before and after the change; no item moves from exit 0 to exit 1 | blocking |
| a rule survives a mutation | qualitative | the reviewer flips each regex, vocabulary word, comparison operator and tier set in the new code and one test must fail. Allowed survivors, named: the wording of message text, the order of findings in the output, and the numeric value of MAX_CITED_BYTES. Any other survivor is a finding | blocking |
| this item breaks its own rule | deterministic | python scripts/spec_check.py on this README at draft and on a temp copy at spec-locked | blocking |

## Gap-ledger check
| Category | Handled by |
|---|---|
| probabilistic-call-reliability | n/a: no LLM call |
| creative-domain-anchoring | n/a: no generated creative output |
| asserted-not-verified-claim | AC-4 and AC-6 (a claim needs a file:line or a dated URL), AC-5 (a local line must resolve), AC-10 (the reviewer opens each cited line); web citations are spot-checked by the reviewer only |
| concurrent-actor-incomplete | n/a: the checker reads one file per run and no external resource |
| runtime-schema-drift | AC-1 (regenerate-and-diff of the config) and AC-3 to AC-7 (one Row model per table) |
| invariant-checked-on-one-path-only | AC-2 and AC-3 run on every type and on a nested spec; AC-10 runs the same Row models over both templates; the required-or-warning decision is read from one function used by CK-47, CK-48 and CK-49 |
| signal-consumer-enumeration | AC-1: the consumers of the config are spec_check.py, gen_heading_config.py, tests/test_gen_heading_config.py (hard-coded 8 headings, updated) and the spec-gate-checker components.md text; the readers of the tier sets are spec_check.py:51-56 and the standard's :326 |
| cross-platform-path-identity | AC-5: one canonical form (forward slashes, case-folded drive letter, `~` expanded, repo-relative resolved against `--root`) and Windows-shaped fixtures; AC-9 walk roots derive from fleet_paths.REPO_ROOT |
| authoritative-source | the rule binds on the staged state of each README, read with the yaml Item loader from the index (HEAD only for the historical exception), never from an editable field or list (AC-8); headings, order and optional come from the heading table (AC-1); `created` validity from the schema layer (AC-8); a cited line's existence from the file itself (AC-5) |
| fail-closed-on-unknown | AC-3 to AC-7 (an unparsed table or unknown word is an error); AC-8 (a staged README at a gated status without valid sections, an out-of-enum status, or a bad date is never lenient); AC-5 (a missing or oversize file is an error) |
| destructive-op-proof | n/a: read-only checker; the heading generator only rewrites its own config |
| liveness-and-time | n/a: no locks or leases; the future-date check uses the date only (AC-6 uses a far-future fixture) |
| concurrency-granularity | n/a: stateless, one file per run |
| external-contract-unverified | the Local and Web tables of this item (Foreman lines read on 2026-10-31); AC-5 and AC-6 for later items |
| split-state | n/a: no mutable state and no exemption list |
| untestable-ac | one fault per fixture row with a specific message substring (every AC fixtures table); named mutation survivors in the Gate plan |
| scope-drift-oversize | 10 ACs; Non-goals name the deferred pieces |
| enforcement-allowlist | AC-2 (envelope optional for bugfix, research, experiment), AC-8 (every staged README at spec-locked, building or shipped; the untouched-historical exception) and AC-9 (no existing item turns from passing to failing); killed and promoted items run only the ALWAYS tier |
| hand-copied-enum | AC-10: the vocabularies in the standard equal the constants in work_item_md.py; the gated statuses come from the spec_check tier sets, not re-spelled |
| escape-record | n/a: a record row, not a spec category |

## Open questions
- OQ-1: Resolved by the owner-approved scope cut of 2026-10-31: no exemption list and no delta rule. Every staged work-item README at spec-locked, building or shipped must carry valid sections, except an untouched historical one (HEAD has the same status and neither section), which warns.
- OQ-2: Citation resolution depends on the cited machine's files. An item citing D:/repo paths fails CK-48 on a machine without them. Default: acceptable, the fleet is one machine; shipped items only warn.
- OQ-3: Assumed defaults for types the owner did not name: data-collection requires both sections (through L0 lite); experiment requires References and treats the envelope as optional. Revisit if experiments start hiding real assumptions.
- OQ-4: The order rule is Python over level-2 headings, not MD043. Revisit if MD043 gains an adjacency form.
- OQ-5: `flag` is a weaker outcome than keep, refuse or defer. It is defined as "take no action on the affected item and raise a visible alert", so no outcome in the vocabulary allows a destructive action. The owner may drop it.
- OQ-7: The brief's two sentences about today's escapes are cited verbatim but are not literal text in SPEC-GAP-LEDGER.md rows 29-41. The nearest rows are 40 and 41. The owner may want those sentences added to the ledger.
- OQ-8: The reviewer agent text is governance; the sentence this item adds to agents/reviewer.md must be applied by the parent session, not by a subagent.
