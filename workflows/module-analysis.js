export const meta = {
  name: 'module-analysis',
  description: 'Analyse one module end to end — schema, relations, code path, UI, and every assumption spot-checked against production',
  whenToUse: 'When a module or subsystem needs to be understood well enough that claims about it can be quoted. Fans out one agent per lens, then forces every load-bearing claim through a data spot-check before it is allowed into the report. Derived from the analytics pass that took a full session by hand.',
  phases: [
    { title: 'Scope', model: 'haiku', detail: 'enumerate the module — tables, row counts, code paths, wiki pages' },
    { title: 'Lenses', model: 'haiku + sonnet by lens', detail: 'one per lens: schema, relations, code, UI, intent, crosscutting, observability' },
    { title: 'Spotcheck', model: 'opus', detail: 'every load-bearing claim re-measured, dull explanation tested first' },
    { title: 'Report', model: 'opus', detail: 'two-layer output, provenance per section, unverified claims labelled' },
  ],
}

/* ---------------------------------------------------------------- schemas */

const SCOPE = {
  type: 'object',
  required: ['tables', 'entry_points'],
  properties: {
    tables: { type: 'array', items: { type: 'object', required: ['name'], properties: {
      name: { type: 'string' }, rows: { type: 'integer' }, why: { type: 'string' } } } },
    entry_points: { type: 'array', items: { type: 'string' }, description: 'controllers, services, jobs' },
    wiki_pages: { type: 'array', items: { type: 'string' } },
    excluded: { type: 'array', items: { type: 'string' }, description: 'tables deliberately out of scope, and why' },
  },
}

const FINDING = {
  type: 'object',
  required: ['claim', 'grade', 'how', 'source', 'load_bearing'],
  properties: {
    claim: { type: 'string', description: 'one falsifiable sentence' },
    grade: { type: 'string', enum: ['measured', 'stated', 'inference', 'assumed'] },
    how: { type: 'string', description: 'the exact query, file:line, or tool call' },
    source: { type: 'string' },
    environment: { type: 'string', description: 'production | alpha | code | external — required for any number' },
    load_bearing: { type: 'boolean', description: 'true if a wrong answer changes a design decision' },
    dull_explanation: { type: 'string', description: 'the boring reading that would also fit this evidence' },
  },
}

const LENS_OUT = {
  type: 'object',
  required: ['lens', 'findings'],
  properties: {
    lens: { type: 'string' },
    findings: { type: 'array', items: FINDING },
    absent: { type: 'array', items: { type: 'string' }, description: 'what you looked for and did not find' },
    locations: { type: 'array', items: { type: 'object', required: ['looking_for', 'found_in'], properties: {
      looking_for: { type: 'string' }, found_in: { type: 'string' },
      not_in: { type: 'string', description: 'the obvious place it was NOT' } } },
      description: 'non-obvious storage locations, for the where-to-look register' },
  },
}

const SPOT = {
  type: 'object',
  required: ['verdict', 'reasoning'],
  properties: {
    verdict: { type: 'string', enum: ['confirmed', 'narrowed', 'refuted', 'unresolved'] },
    reasoning: { type: 'string' },
    corrected_claim: { type: 'string', description: 'if narrowed or refuted, the version that survives' },
    queries_run: { type: 'array', items: { type: 'string' } },
    next_check: { type: 'string', description: 'if unresolved, the one cheapest check that would settle it' },
  },
}

const REPORT = {
  type: 'object',
  required: ['headline', 'summary_sections', 'detail_sections'],
  properties: {
    headline: { type: 'string' },
    summary_sections: { type: 'array', items: { type: 'object',
      required: ['heading', 'body', 'confidence'], properties: {
        heading: { type: 'string' }, body: { type: 'string' },
        confidence: { type: 'string', enum: ['measured', 'stated', 'inference', 'assumed', 'mixed'] } } } },
    detail_sections: { type: 'array', items: { type: 'object',
      required: ['heading', 'body', 'provenance'], properties: {
        heading: { type: 'string' }, body: { type: 'string' }, provenance: { type: 'string' } } } },
    caveats: { type: 'array', items: { type: 'string' }, description: 'what this analysis does NOT establish' },
  },
}

/* The six lenses. Each is blind to the others so agreement is corroboration.
   They exist because the analytics pass needed all six and discovered that no
   single one was sufficient: the schema alone missed that formulas live in an
   EAV table, the code alone missed that 92% of grids are tall, and only the UI
   showed that a correctly-built chart can still be illegible. */

// ---------------------------------------------------------------------------
// PERSONAS — who runs each stage, and at what tier.
//
// Canonical assignment and the reasoning for every row:
//   ~/repo/claudence/docs/WORKFLOW-PERSONAS.md
// Persona -> model tier authority:
//   ~/.claude/CLAUDE.md, "Agent Personas — Model Tier Allocation"
//
// Before 2026-08-13 every agent here inherited the main-loop model, so a
// 51-agent run executed 51 Opus agents — including the one whose job was a
// table listing. Two runs that day burned ~4.5M subagent tokens each and ended
// on a session limit.
//
// The shape of the rule: MANY agents at the gathering edge run cheap; the FEW
// whose output every later stage depends on run expensive. The saving is spent
// where it changes the answer, not banked.
//
// NOTE: workflow scripts are self-contained — no imports, no filesystem — so
// this literal is duplicated in adversarial-research.js. Change a tier in BOTH
// and in the doc. A single source of truth the scripts cannot read is not one.
// ---------------------------------------------------------------------------
const PERSONAS = {
  // Gathering. Bounded judgement, many instances.
  researcher:      { model: 'haiku',  effort: 'low'    },  // enumerate, retrieve
  researcher_mid:  { model: 'haiku',  effort: 'medium' },  // retrieve + summarise
  researcher_deep: { model: 'sonnet', effort: 'high'   },  // read code, write SQL
  designer:        { model: 'sonnet', effort: 'high'   },  // shape and contract questions
  surveyor:        { model: 'sonnet', effort: 'medium' },  // UI, telemetry, structure

  // Judgement. Few instances, and every later stage depends on them.
  // Deliberately raised ABOVE the gathering tier so no agent certifies its own
  // finding — the author and the refuter are never the same tier.
  reviewer_adversarial: { model: 'opus', effort: 'high' },  // the gate
  architect:            { model: 'opus', effort: 'high' },  // the document

  // A cheap stage reporting ABSENCE is the dangerous case: a script reading one
  // directory once reported 58 modelless tables when 43 had models. Absence
  // claims belong here or above.
  absence_safe: { model: 'sonnet', effort: 'high' },
}

const LENSES = [
  { persona: 'surveyor', key: 'schema', brief: `The tables, columns and REAL Postgres types. Dump every column with its type and nullability. Report populated rates, not just counts — a 4%-populated column tells a different story from a 96% one. Name every place a type is DECLARED somewhere other than where the value is stored, because that is where a consumer will get it wrong.` },
  { persona: 'researcher_deep', key: 'relations', brief: `How these tables actually connect. Distinguish DECLARED foreign keys from relations that exist only as id overlap in the data, and give the match rate and orphan count for each. For anything below 100%, do not assume deletion without cascade — check whether the model declares \`dependent:\`, whether the table soft-deletes, and whether the orphan rate varies by creation year. Report cross-boundary relations separately from internal ones.` },
  { persona: 'researcher_deep', key: 'code', brief: `Read the code that WRITES and READS these columns. Intent lives in the model, not the column name. Report association options verbatim — \`optional:\`, \`dependent:\`, \`through:\` — and note where a \`has_many\` has NO \`dependent:\` while siblings do, because that is a decision. Find every service, job and concern in the path. Cite file:line. Flag any place a value is computed rather than stored.` },
  { persona: 'surveyor', key: 'ui', brief: `Open the running application and look. Map each visible element to the table and column behind it. **What the user sees is frequently not what is stored** — a formatted value, a rounded number, a computed indicator. Count the interactions needed to reach each piece of data. Report anything that is correctly built and still hard to read, which no schema inspection can reveal. Use a demo or training tenant, never customer data.` },
  { persona: 'researcher_mid', key: 'intent', brief: `Find who asked for this and why. Search the wikis first — note that a GitHub wiki is a SEPARATE repo invisible to code search, and its diagrams are usually raster images invisible to grep. Then Productboard for filed decisions, then Slack for the argument that produced them. Quote decision language verbatim. A requirement with no recorded intent is OUR inference and must be labelled as such.` },
  { persona: 'designer', key: 'crosscutting', brief: `What this module SHARES with others rather than owns. Find the mixins, concerns and base classes its models include — those are the codebase's own cross-module themes and they cut the schema differently from ownership. Report which behaviours are shared (taggable, orderable, favouritable, reportable) and which tables outside this module share them, because a change to a shared concern changes every one of them. Also find the tables this module reaches that belong to another, and say whether the relationship is enforced.` },
  { persona: 'surveyor', key: 'observability', brief: `The non-functional half. Latency percentiles on the endpoints and jobs this module touches, error rates, throughput, queue depth, saturation. **Scope every figure to production** — unscoped spans have overstated a tail by 6.7x. If a metric does not exist for this area, that ABSENCE is the finding: say which search you ran and what came back, because an unmeasurable requirement cannot be verified by anyone.` },
]

/* ------------------------------------------------------------------ script */

const target = (args && args.module) || args
if (!target || typeof target !== 'string') {
  throw new Error('module-analysis needs a module: Workflow({name:"module-analysis", args:{module:"report"}})')
}
const context = (args && args.context) || ''
const constraints = (args && args.constraints) || 'READ-ONLY everywhere. Never select a column holding a person name, email, or customer content. Label every number with its environment.'

// Seven lenses plus scope plus report is 9 agents before spot-checks; a default run
// lands near 16. The spot-check cap is the lever — raising it buys confidence, not
// coverage, because every claim it checks was already found.
const big = Boolean(budget.total && budget.total > 400000)
const SPOT_CAP = big ? 10 : 6

phase('Scope')
log(`Module under analysis: ${target}`)
const scope = await agent(
  `Enumerate the scope of one module before anyone analyses it.

MODULE: ${target}
${context ? `CONTEXT: ${context}` : ''}
CONSTRAINTS: ${constraints}

Produce: every table that belongs to this module with its production row count and one line on why it belongs; the controllers, services and jobs that are its entry points; the wiki pages that document it; and the tables you are deliberately EXCLUDING with the reason.

Before you enumerate anything, **read the project's lookup register if one exists** (research/WHERE-TO-LOOK.md or similar). It records where information actually lives and which assumptions have already produced wrong published claims. Re-deriving what it already answers is the most common waste in this work.

Four warnings from prior passes, each of which produced a wrong published number:
- **A table-name prefix is not a module boundary.** One prefix in this system spans two unrelated products, and a prefix-scoped filter leaked HR records into analytics answers.
- **A module's tables extend well beyond the obvious set.** A four-module map covered 26 tables where those modules actually span 100+.
- **Model files are not all in app/models/.** 82 of 225 live in namespaced subdirectories, and a script reading only the top level reported 58 tables as having no model when 43 did.
- **Row counts that exclude dynamically-named tables are wrong by an order of magnitude.** One module read 1.77M rows until 12,540 per-source cell tables were counted, at which point it read 31.5M.`,
  { schema: SCOPE, label: `scope:${target}`, ...PERSONAS.researcher }
)
const tableList = (scope.tables || []).map(t => t.name).join(', ')
log(`${(scope.tables || []).length} tables · ${(scope.entry_points || []).length} entry points · ${(scope.wiki_pages || []).length} wiki pages`)
if (scope.excluded && scope.excluded.length) log(`excluded: ${scope.excluded.join(' · ')}`)

// Lenses fan out, then every load-bearing claim is spot-checked as soon as its
// lens returns — pipeline, so a slow lens does not hold up verification of a fast one.
phase('Lenses')
const perLens = await pipeline(
  LENSES,
  L => agent(
    `Analyse ONE module through ONE lens. You are blind to the other lenses by design.

MODULE: ${target}
TABLES IN SCOPE: ${tableList}
ENTRY POINTS: ${(scope.entry_points || []).join(', ')}
WIKI PAGES: ${(scope.wiki_pages || []).join(', ')}
${context ? `CONTEXT: ${context}` : ''}
CONSTRAINTS: ${constraints}

YOUR LENS — ${L.key}: ${L.brief}

For every finding: state it as one falsifiable sentence, grade it (measured / stated / inference / assumed), give the exact query or file:line, name the environment for any number, and mark whether it is load-bearing.

**And for every load-bearing finding, state the DULL EXPLANATION** — the boring reading that would also fit your evidence. Prior passes published three striking claims that turned out to be instrumentation changes, sampling artefacts, or one table mistaken for a whole module.

Also report **non-obvious locations**: anything you found somewhere other than the obvious place. Those feed a lookup register so the next analysis does not repeat the search.`,
    { schema: LENS_OUT, label: `lens:${L.key}`, phase: 'Lenses',
      ...(PERSONAS[L.persona] || PERSONAS.surveyor) }
  ),
  (out, L) => {
    if (!out || !out.findings) return { lens: L.key, confirmed: [], corrected: [], unresolved: [] }
    const heavy = out.findings.filter(f => f.load_bearing).slice(0, SPOT_CAP)
    const light = out.findings.filter(f => !f.load_bearing)
    if (out.findings.length > heavy.length + light.length) log(`${L.key}: spot-check cap reached`)
    return parallel(heavy.map(f => () =>
      agent(
        `SPOT-CHECK one load-bearing claim against the data. Do not take it on trust.

CLAIM: ${f.claim}
GRADE CLAIMED: ${f.grade} · ENVIRONMENT: ${f.environment || 'NOT STATED — itself a defect'}
HOW IT WAS OBTAINED: ${f.how}
SOURCE: ${f.source}
THE DULL EXPLANATION THE AUTHOR OFFERED: ${f.dull_explanation || '(none — test one yourself)'}

Your job, in this order:
1. **Test the dull explanation FIRST.** If instrumentation changed, if a sample was unordered, if one table was mistaken for a population, if a soft-delete flag was ignored — that is usually the answer.
2. Re-measure the claim yourself with your own query. Do not reuse theirs.
3. If it survives but narrower, return the narrowed version — a claim that shrinks under measurement is still a finding.
4. If you cannot settle it, say **unresolved** and name the ONE cheapest check that would. Do not guess a mechanism.

${constraints}`,
        { schema: SPOT, label: `spot:${String(f.claim).slice(0, 30)}`, phase: 'Spotcheck',
          ...PERSONAS.reviewer_adversarial }
      ).then(v => ({ ...f, spot: v }))
    )).then(checked => ({
      lens: L.key,
      confirmed: checked.filter(Boolean).filter(c => c.spot?.verdict === 'confirmed'),
      corrected: checked.filter(Boolean).filter(c => ['narrowed', 'refuted'].includes(c.spot?.verdict)),
      unresolved: checked.filter(Boolean).filter(c => c.spot?.verdict === 'unresolved'),
      unchecked: light,
      absent: out.absent || [],
      locations: out.locations || [],
    }))
  }
)

const rolled = perLens.filter(Boolean)
const confirmed = rolled.flatMap(r => r.confirmed || [])
const corrected = rolled.flatMap(r => r.corrected || [])
const unresolved = rolled.flatMap(r => r.unresolved || [])
const unchecked = rolled.flatMap(r => r.unchecked || [])
const locations = rolled.flatMap(r => r.locations || [])
const absent = rolled.flatMap(r => r.absent || [])
log(`${confirmed.length} confirmed · ${corrected.length} corrected by spot-check · ${unresolved.length} unresolved · ${unchecked.length} not load-bearing`)
for (const c of corrected) log(`CORRECTED: ${String(c.claim).slice(0, 80)}`)

phase('Report')
const report = await agent(
  `Write the module analysis. Every claim here has already been spot-checked or is labelled as not.

MODULE: ${target}

CONFIRMED (survived an independent re-measurement):
${JSON.stringify(confirmed.map(c => ({ claim: c.claim, grade: c.grade, how: c.how, env: c.environment })), null, 1)}

CORRECTED BY SPOT-CHECK — **use the corrected version, never the original**:
${JSON.stringify(corrected.map(c => ({ original: c.claim, verdict: c.spot?.verdict, corrected: c.spot?.corrected_claim, why: c.spot?.reasoning })), null, 1)}

UNRESOLVED — include, labelled unresolved, with the next check named:
${JSON.stringify(unresolved.map(c => ({ claim: c.claim, next_check: c.spot?.next_check })), null, 1)}

NOT LOAD-BEARING, unchecked — include only if labelled:
${JSON.stringify(unchecked.map(c => c.claim), null, 1)}

WHAT WAS LOOKED FOR AND NOT FOUND:
${JSON.stringify(absent, null, 1)}

Rules. Lead every section with the finding, not with an identifier. State the consequence, not just the fact. Put provenance per detail section — the exact query or file:line — so one claim can be checked without auditing the document. Say plainly in the caveats what this analysis does NOT establish, and name any lens that returned nothing.

**A corrected claim is more valuable than a confirmed one.** Where a spot-check narrowed something, show the chain — it teaches the next reader where the trap was.

Two things this report must not do, both observed in a prior pass:
- **Do not present a count without saying what population it covers.** A binding table measured at 86% turned out to describe one third of the visual estate while being reported as describing the module.
- **Do not let an absent lens read as a clean result.** If observability returned nothing, say the area is unmeasured rather than implying it is healthy.`,
  { schema: REPORT, label: 'report', ...PERSONAS.architect }
)

// The report agent returns null when it dies on a session limit. Everything above
// it — the lens sweep and every spot-check — is already done and paid for, so a
// failed synthesis must degrade rather than discard it.
return {
  module: target,
  headline: report ? report.headline : 'SYNTHESIS FAILED — the lens findings and spot-checks below are complete and unsynthesised',
  synthesis_failed: !report,
  summary_sections: report ? report.summary_sections : [],
  detail_sections: report ? report.detail_sections : [],
  lens_findings: rolled.map(r => ({ lens: r.lens, findings: r.findings || [], absent: r.absent || [] })),
  caveats: report ? (report.caveats || []) : [],
  corrected: corrected.map(c => ({ original: c.claim, corrected: c.spot?.corrected_claim, verdict: c.spot?.verdict })),
  unresolved: unresolved.map(c => ({ claim: c.claim, next_check: c.spot?.next_check })),
  // Feeds the project's lookup register directly. Shaped as rows so it can be pasted
  // rather than re-read: what was sought, where it was found, the obvious place it was not.
  locations,
  lookup_rows: locations.map(l => `| ${l.looking_for} | ${l.not_in || '—'} | ${l.found_in} | this analysis |`),
  scope: { tables: (scope.tables || []).map(t => t.name), excluded: scope.excluded || [] },
  coverage: { lenses_run: rolled.map(r => r.lens), lenses_expected: LENSES.map(l => l.key) },
}
