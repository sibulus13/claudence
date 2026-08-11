export const meta = {
  name: 'adversarial-research',
  description: 'Fan out research on a topic, refute every finding independently, emit a two-layer document with per-section provenance',
  whenToUse: 'When you need to understand a topic fast and the output must survive being quoted — a spike question, a technology survey, an unblocking analysis. Every surviving claim has been attacked by agents that did not produce it.',
  phases: [
    { title: 'Decompose', detail: 'split the topic into independent dimensions, each naming what it would unblock' },
    { title: 'Find', detail: 'one researcher per dimension, provenance required per claim' },
    { title: 'Refute', detail: 'independent skeptics per load-bearing claim, distinct lenses' },
    { title: 'Synthesize', detail: 'two-layer output — summary and detail, backlinked' },
    { title: 'Critique', detail: 'what is still missing: modality not run, claim unverified' },
  ],
}

/* ---------------------------------------------------------------- schemas */

const DECOMPOSITION = {
  type: 'object',
  required: ['dimensions'],
  properties: {
    dimensions: {
      type: 'array', minItems: 2, maxItems: 6,
      items: {
        type: 'object',
        required: ['key', 'question', 'unblocks', 'where_to_look'],
        properties: {
          key: { type: 'string', description: 'short kebab-case slug' },
          question: { type: 'string', description: 'the one question this dimension answers' },
          unblocks: { type: 'string', description: 'what downstream decision or gate this would unblock' },
          where_to_look: { type: 'string', description: 'concrete sources: files, tables, docs, external' },
          load_bearing: { type: 'boolean', description: 'true if a wrong answer here changes a decision' },
        },
      },
    },
    excluded: { type: 'array', items: { type: 'string' }, description: 'dimensions deliberately out of scope, and why' },
  },
}

// Provenance is mandatory per claim. A claim without it is dropped in synthesis
// rather than published unsourced — the whole point of the workflow.
const FINDINGS = {
  type: 'object',
  required: ['dimension', 'findings'],
  properties: {
    dimension: { type: 'string' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['claim', 'grade', 'provenance', 'load_bearing'],
        properties: {
          claim: { type: 'string', description: 'one sentence, falsifiable' },
          grade: { type: 'string', enum: ['measured', 'stated', 'inference', 'assumed'] },
          provenance: {
            type: 'object',
            required: ['how', 'source'],
            properties: {
              how: { type: 'string', description: 'HOW this was obtained: the query run, the file read, the page fetched' },
              source: { type: 'string', description: 'file:line, table.column, URL, or who stated it' },
              environment: { type: 'string', description: 'alpha | production | external | n/a — required for any number' },
            },
          },
          load_bearing: { type: 'boolean' },
          would_falsify: { type: 'string', description: 'what observation would prove this wrong' },
        },
      },
    },
    dead_ends: { type: 'array', items: { type: 'string' }, description: 'what was checked and found empty — saves the next run' },
  },
}

const VERDICT = {
  type: 'object',
  required: ['refuted', 'reasoning'],
  properties: {
    refuted: { type: 'boolean', description: 'true if the claim does not hold. Default true when uncertain.' },
    reasoning: { type: 'string' },
    correction: { type: 'string', description: 'if refuted but a weaker version holds, state that version' },
  },
}

const TWO_LAYER = {
  type: 'object',
  required: ['headline', 'summary_sections', 'detail_sections'],
  properties: {
    headline: { type: 'string', description: 'BLUF — the answer in one sentence' },
    summary_sections: {
      type: 'array',
      items: {
        type: 'object',
        required: ['heading', 'body', 'detail_anchor'],
        properties: {
          heading: { type: 'string' },
          body: { type: 'string', description: 'at most 3 sentences — this layer is scanned, not read' },
          detail_anchor: { type: 'string', description: 'kebab-case anchor of the matching detail section' },
          confidence: { type: 'string', enum: ['measured', 'stated', 'inference', 'assumed', 'mixed'] },
        },
      },
    },
    detail_sections: {
      type: 'array',
      items: {
        type: 'object',
        required: ['anchor', 'heading', 'body', 'provenance'],
        properties: {
          anchor: { type: 'string' },
          heading: { type: 'string' },
          body: { type: 'string' },
          provenance: { type: 'string', description: 'HOW every data point in this section was obtained. Per section, not per document.' },
          open_questions: { type: 'array', items: { type: 'string' } },
        },
      },
    },
  },
}

const CRITIQUE = {
  type: 'object',
  required: ['gaps'],
  properties: {
    gaps: {
      type: 'array',
      items: {
        type: 'object',
        required: ['what', 'why_it_matters'],
        properties: {
          what: { type: 'string' },
          why_it_matters: { type: 'string' },
          kind: { type: 'string', enum: ['modality-not-run', 'claim-unverified', 'source-unread', 'dimension-missed'] },
        },
      },
    },
    verdict: { type: 'string', description: 'is the output safe to quote yet, and if not what closes the gap' },
  },
}

/* ------------------------------------------------------------------ script */

const topic = (args && args.topic) || args
if (!topic || typeof topic !== 'string') {
  throw new Error('adversarial-research needs a topic: Workflow({name:"adversarial-research", args:{topic:"..."}})')
}
const context = (args && args.context) || ''
const constraints = (args && args.constraints) || ''

// Scale with the turn's budget when one was set; otherwise stay inside the
// default 15-agent guideline: 1 decompose + 3 finders + 8 refuters + 2 = 14.
const big = Boolean(budget.total && budget.total > 400000)
const MAX_DIM = big ? 6 : 3
const REFUTERS = big ? 3 : 2
const MAX_VERIFY = big ? 8 : 4

phase('Decompose')
log(`Topic: ${topic}`)
const plan = await agent(
  `Decompose this research topic into INDEPENDENT dimensions that can be researched in parallel.

TOPIC: ${topic}
${context ? `CONTEXT: ${context}` : ''}
${constraints ? `CONSTRAINTS: ${constraints}` : ''}

Rules:
- Dimensions must be MECE — no two should return the same finding.
- Each must name what downstream decision or gate it would unblock. A dimension that unblocks nothing is not worth a dimension.
- Name CONCRETE places to look: file paths, database tables, specific documents. "Research the literature" is not a place.
- At most ${MAX_DIM} dimensions. Fewer is fine. Mark the ones where a wrong answer changes a decision as load_bearing.
- Also list what you are deliberately excluding and why — scope exclusions are findings too.

Read before deciding: any state/spec documents in the working directory that describe what is already known, so you do not commission research that has already been done.`,
  { schema: DECOMPOSITION, label: 'decompose' }
)

const dims = (plan.dimensions || []).slice(0, MAX_DIM)
log(`${dims.length} dimensions · ${dims.filter(d => d.load_bearing).length} load-bearing`)
if (plan.excluded && plan.excluded.length) log(`excluded: ${plan.excluded.join(' · ')}`)

// Find and refute as a pipeline: a dimension's findings start being attacked as
// soon as that dimension returns, rather than waiting for the slowest finder.
const LENSES = [
  'CORRECTNESS — is the claim actually true? Re-derive it from the named source. If the source does not say this, it is refuted.',
  'PROVENANCE — does the stated source actually support the claim, and is the environment named? An unlabelled number is refuted.',
  'ALTERNATIVE EXPLANATION — is there a duller reading of the same evidence? Instrumentation changed, sample was biased, the name misleads. Prefer the boring explanation.',
]

const perDimension = await pipeline(
  dims,
  d => agent(
    `Research one dimension and return findings, each with mandatory provenance.

TOPIC: ${topic}
DIMENSION: ${d.key} — ${d.question}
WHERE TO LOOK: ${d.where_to_look}
THIS WOULD UNBLOCK: ${d.unblocks}
${context ? `CONTEXT: ${context}` : ''}

Hard requirements:
- EVERY claim carries provenance: HOW you obtained it (the exact query, the file read, the command run) and the SOURCE (file:line, table.column, URL, or who said it).
- EVERY number names its environment. The same query has returned wildly different answers against different databases here.
- Grade honestly: measured (a query returned it) / stated (someone asserted it) / inference (reasoned from measurements) / assumed (a default you took). Do not inflate a grade.
- For each claim, state what observation WOULD FALSIFY it. A claim nothing could falsify is not a finding.
- Report dead ends. What you checked and found empty saves the next run real time.
- Read-only. Do not modify any file or database.

Prefer few well-sourced findings to many plausible ones.`,
    { schema: FINDINGS, label: `find:${d.key}`, phase: 'Find' }
  ),
  (res, d) => {
    if (!res || !res.findings) return { dimension: d.key, verified: [], killed: [] }
    // Attack load-bearing claims first; they are the ones that change decisions.
    const ranked = res.findings.slice().sort((a, b) => (b.load_bearing ? 1 : 0) - (a.load_bearing ? 1 : 0))
    const toVerify = ranked.slice(0, MAX_VERIFY)
    const unverified = ranked.slice(MAX_VERIFY)
    if (unverified.length) log(`${d.key}: ${unverified.length} finding(s) past the verify cap — carried as UNVERIFIED, not dropped silently`)
    return parallel(toVerify.map(f => () =>
      parallel(LENSES.slice(0, REFUTERS).map(lens => () =>
        agent(
          `Try to REFUTE this claim. You did not produce it and you owe it nothing.

CLAIM: ${f.claim}
GRADE CLAIMED: ${f.grade}
PROVENANCE GIVEN: how="${f.provenance && f.provenance.how}" source="${f.provenance && f.provenance.source}" environment="${f.provenance && f.provenance.environment || 'NONE GIVEN'}"
AUTHOR SAYS THIS WOULD FALSIFY IT: ${f.would_falsify || '(nothing stated — itself a weakness)'}

YOUR LENS: ${lens}

Go to the named source and check. Default to refuted=true when you cannot confirm it — an unconfirmed claim must not survive by inertia. If a weaker version of the claim does hold, state that version as the correction.`,
          { schema: VERDICT, label: `refute:${f.claim.slice(0, 28)}`, phase: 'Refute' }
        )
      )).then(votes => {
        const real = votes.filter(Boolean)
        const against = real.filter(v => v.refuted).length
        const survives = real.length > 0 && against < Math.ceil(real.length / 2)
        return {
          ...f,
          dimension: d.key,
          survives,
          votes_against: against,
          votes_total: real.length,
          corrections: real.map(v => v.correction).filter(Boolean),
        }
      })
    )).then(judged => ({
      dimension: d.key,
      verified: judged.filter(Boolean).filter(j => j.survives),
      killed: judged.filter(Boolean).filter(j => !j.survives),
      unverified,
      dead_ends: res.dead_ends || [],
    }))
  }
)

const rolled = perDimension.filter(Boolean)
const surviving = rolled.flatMap(r => r.verified || [])
const killed = rolled.flatMap(r => r.killed || [])
const carried = rolled.flatMap(r => (r.unverified || []).map(f => ({ ...f, survives: null })))
log(`${surviving.length} survived · ${killed.length} refuted · ${carried.length} unverified`)

if (!surviving.length) {
  log('Nothing survived refutation. Emitting the graveyard rather than a document — that IS the finding.')
  return { topic, headline: 'No claim survived independent refutation.', surviving: [], killed, carried, plan }
}

phase('Synthesize')
const doc = await agent(
  `Write a TWO-LAYER document from claims that have already survived independent refutation.

TOPIC: ${topic}

SURVIVING CLAIMS (use these):
${JSON.stringify(surviving.map(s => ({ claim: s.claim, grade: s.grade, provenance: s.provenance, dimension: s.dimension, corrections: s.corrections })), null, 1)}

REFUTED — do NOT reinstate these, and where one is interesting say it was refuted and why:
${JSON.stringify(killed.map(k => ({ claim: k.claim, votes_against: k.votes_against })), null, 1)}

${carried.length ? `CARRIED UNVERIFIED — include only if labelled UNVERIFIED inline:\n${JSON.stringify(carried.map(c => c.claim), null, 1)}` : ''}

Structure, and it is not negotiable:
- headline: BLUF. The answer in one sentence, not a description of the investigation.
- summary_sections: scannable. At most 3 sentences each. Each names the detail_anchor it opens into and its overall confidence. This layer is for someone deciding whether to read further.
- detail_sections: the argument in full. Each carries a provenance field stating HOW every data point in THAT section was obtained — the query, the file, the command. Provenance lives per section, so a reader checking one claim does not have to audit the whole document.
- Never state an inference as a measurement. Where a claim is graded assumed, say so in the sentence itself, not in a footnote.
- Where the refuters produced corrections, use the corrected weaker version, not the original.`,
  { schema: TWO_LAYER, label: 'synthesize' }
)

phase('Critique')
const critique = await agent(
  `You are the completeness critic. Find what this research MISSED.

TOPIC: ${topic}
DIMENSIONS RESEARCHED: ${dims.map(d => d.key).join(', ')}
DELIBERATELY EXCLUDED: ${(plan.excluded || []).join(' · ') || 'nothing was declared out of scope — itself suspicious'}
HEADLINE PRODUCED: ${doc.headline}
CLAIMS SURVIVING: ${surviving.length} · REFUTED: ${killed.length} · UNVERIFIED: ${carried.length}
DEAD ENDS REPORTED: ${rolled.flatMap(r => r.dead_ends || []).join(' · ') || 'none'}

Ask specifically:
- Which modality was never run? (the database was queried but the code never read; the docs were read but nothing was measured)
- Which surviving claim is load-bearing but thinly sourced?
- Which dimension should have existed and does not?
- Does the headline overreach what the claims support?

Then state whether the output is safe to quote yet, and if not, exactly what closes the gap. Being unhelpful here is the failure mode — find something real.`,
  { schema: CRITIQUE, label: 'critique' }
)

return {
  topic,
  headline: doc.headline,
  summary_sections: doc.summary_sections,
  detail_sections: doc.detail_sections,
  gaps: critique.gaps,
  safe_to_quote: critique.verdict,
  refuted: killed.map(k => ({ claim: k.claim, votes_against: k.votes_against, votes_total: k.votes_total })),
  unverified: carried.map(c => c.claim),
  dimensions: dims,
  excluded: plan.excluded || [],
}
