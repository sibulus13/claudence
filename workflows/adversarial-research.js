export const meta = {
  name: 'adversarial-research',
  description: 'Ask one question of every source of truth independently, then rank, consolidate and refute into one report',
  whenToUse: 'When you have one question and several places that might answer it, and the answer must survive being quoted. Each channel — code, database, Datadog, Productboard, Slack, other MCP, external — answers the same question blind to the others, so agreement is corroboration rather than echo, and disagreement between two channels is surfaced as the most valuable output rather than averaged away.',
  phases: [
    { title: 'Sweep', detail: 'every channel answers the SAME core question independently — code, database, Datadog, Productboard, Slack, other MCP, external' },
    { title: 'Rank', detail: 'consolidate across channels: merge agreements, surface contradictions, rank by evidence weight' },
    { title: 'Deepen', detail: 'follow only the threads ranking exposed as load-bearing or contradicted' },
    { title: 'Refute', detail: 'independent skeptics per load-bearing claim, distinct lenses' },
    { title: 'Synthesize', detail: 'two-layer output — summary and detail, backlinked, provenance per section' },
    { title: 'Critique', detail: 'what is still missing: channel not reached, claim unverified' },
  ],
}

/* ---------------------------------------------------------------- schemas */
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

const CHANNEL_FINDINGS = {
  type: 'object',
  required: ['channel', 'reachable', 'findings'],
  properties: {
    channel: { type: 'string' },
    reachable: { type: 'boolean', description: 'false if the tools for this channel were absent or unauthenticated — say so rather than returning nothing' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['claim', 'grade', 'how', 'source'],
        properties: {
          claim: { type: 'string' },
          grade: { type: 'string', enum: ['measured', 'stated', 'inference', 'assumed'] },
          how: { type: 'string', description: 'the exact query, file read, or tool call' },
          source: { type: 'string', description: 'file:line, table.column, dashboard, ticket id, URL' },
          axis: { type: 'string', enum: ['functional', 'non-functional'], description: 'what it does, versus how well it does it' },
        },
      },
    },
    absent: { type: 'array', items: { type: 'string' }, description: 'what you looked for in this channel and did NOT find — absence in a named channel is evidence' },
  },
}

const CONSOLIDATION = {
  type: 'object',
  required: ['ranked', 'contradictions'],
  properties: {
    ranked: {
      type: 'array',
      items: {
        type: 'object',
        required: ['claim', 'weight', 'channels_agreeing', 'grade'],
        properties: {
          claim: { type: 'string', description: 'the merged claim, stated once' },
          weight: { type: 'integer', description: '1-10. Corroboration across INDEPENDENT channels raises it; a single channel caps it low however confident that channel sounded' },
          channels_agreeing: { type: 'array', items: { type: 'string' } },
          channels_silent: { type: 'array', items: { type: 'string' }, description: 'channels that should have seen this and did not — silence is data' },
          grade: { type: 'string', enum: ['measured', 'stated', 'inference', 'assumed'] },
          axis: { type: 'string', enum: ['functional', 'non-functional'] },
          why_it_matters: { type: 'string' },
        },
      },
    },
    contradictions: {
      type: 'array',
      items: {
        type: 'object',
        required: ['subject', 'positions'],
        properties: {
          subject: { type: 'string' },
          positions: { type: 'array', items: { type: 'string' }, description: 'what each channel says, attributed to the channel' },
          how_to_settle: { type: 'string', description: 'the one cheap check that would resolve it' },
        },
      },
    },
    threads_to_deepen: {
      type: 'array', maxItems: 4,
      items: {
        type: 'object',
        required: ['question', 'why'],
        properties: {
          question: { type: 'string' },
          why: { type: 'string', description: 'load-bearing, or contradicted, or a channel was silent where it should not have been' },
          where_to_look: { type: 'string' },
        },
      },
    },
  },
}

/* Context channels. Each is swept by its own agent, blind to the others, because
   a single agent given every tool reaches for the cheapest one and stops. The
   functional/non-functional split is explicit: code and tickets say what the
   system does, observability says how well it does it, and a survey missing
   either half is not an analysis of the suite. */
const CHANNELS = [
  {
    key: 'code',
    label: 'the codebase, and the functions that read and write the data',
    brief: `Read the ACTUAL CODE. For any data this topic touches, find the model, the migration, and every function that reads or writes the column — intent lives in the model, not the column name. Report the association options verbatim (\`optional:\`, \`dependent:\`), the callers, and any service object or job in the path. Cite file:line for everything. A claim about how data behaves that is not backed by the code that handles it is an assumption.`,
  },
  {
    key: 'database',
    label: 'the database itself',
    brief: `Query the database READ-ONLY. Name the environment on every number — the same query has returned wildly different answers against alpha and production here. Prefer aggregates; never select a column holding a person's name or a customer's content. Report distributions and null rates, not just counts: a column that is 4% populated tells a different story from one that is 96% populated.`,
  },
  {
    key: 'observability',
    label: 'Datadog — the non-functional half',
    brief: `This channel owns the NON-FUNCTIONAL analysis. Use the Datadog tools (load the datadog skills first, as its server instructions require). Look for: p50/p95/p99 latency on the endpoints and jobs this topic touches, error and timeout rates, throughput, queue depth and worker saturation, and any monitor or incident that has fired against them. If a service or dashboard does not exist for this area, that absence IS the finding — say so explicitly rather than returning empty.`,
  },
  {
    key: 'product',
    label: 'Productboard — what product has already decided',
    brief: `Search Productboard for features, spikes, decisions and feedback on this topic. What has product already committed to, filed, or rejected? A decision already recorded is not a proposal to re-make. Report ticket ids with their status, and quote the decision language rather than paraphrasing it.`,
  },
  {
    key: 'slack',
    label: 'Slack — what people actually said, in named channels',
    brief: `Search these channels SPECIFICALLY. Slack is where decisions get made informally and then never written down, so a topic with no Slack trace is different from one that was argued over. Channel list verified 2026-08-11 by searching the workspace; if one 404s, report it rather than substituting another.

    | Channel | What to look for in it |
    |---|---|
    | #product-questions | Customers' and CS's real questions, in their own words — the closest thing to a demand signal. Search the topic and read the THREADS, not just the parent messages |
    | #discoverymeetings | Discovery call notes. Who asked for what, and what they were actually trying to do. The richest source for use cases and for golden-set candidates |
    | #engineering | Design arguments, incidents, and \"why is this slow\" threads. The place a non-functional problem surfaces before it reaches a dashboard |
    | #ai | Prior AI work, what was tried, what was abandoned and why. Check before proposing anything — an idea already rejected here is not a new idea |
    | #product-announcements | What actually shipped and when. Reconciles a claim about the product against the record |
    | #zendesk-tickets | Support traffic. Recurring complaints are a non-functional signal that no dashboard captures |
    | #customer-comms | What was promised to customers externally. Constrains what may now be claimed |
    | #dev-sso-support | Auth, SSO and tenancy questions specifically — relevant to any isolation or per-user-visibility topic |

    Use search modifiers: \`in:#channel\`, \`after:YYYY-MM-DD\` to bound recency, \`is:thread\` for discussions. Attribute by ROLE, never by name, and quote decision language verbatim rather than paraphrasing it. Report which channels you searched and found nothing in — a silent channel is evidence.`,
  },
  {
    key: 'org',
    label: 'the other MCP servers — Notion, GitHub, Drive',
    brief: `Sweep the remaining connected MCP servers. Notion FIRST: the daily log there is the primary record of stakeholder conversations and outranks any repo document when the two disagree. Then GitHub — issues, PRs, and **the wikis, which are a SEPARATE git repo invisible to both code search and the contents API**, so a repo can carry a hundred pages no grep will surface. Then Google Drive for decks and specs. Attribute by role rather than by name. If a server is unauthenticated, report it as unreachable rather than silently skipping it.`,
  },
  {
    key: 'external',
    label: 'outside the organisation',
    brief: `Only after the internal channels: vendor documentation, benchmarks, papers, changelogs. Treat vendor claims as \`stated\`, never \`measured\` — a benchmark a vendor published about its own product is marketing until reproduced. Prefer primary sources and note publication dates; a two-year-old benchmark of a fast-moving system is a historical fact, not a current one.`,
  },
]

/* ------------------------------------------------------------------ script */

const topic = (args && args.topic) || args
if (!topic || typeof topic !== 'string') {
  throw new Error('adversarial-research needs a topic: Workflow({name:"adversarial-research", args:{topic:"..."}})')
}
const context = (args && args.context) || ''
const constraints = (args && args.constraints) || ''

// Sizing. The channel sweep adds ~6 agents, which puts a default run around 20 —
// deliberately past the 15-agent guideline, because a multi-source functional and
// non-functional analysis is what this workflow is for and a sweep that skips
// channels produces exactly the false all-clear it exists to prevent. Pass
// args.channels to narrow it.
const big = Boolean(budget.total && budget.total > 400000)
const MAX_DIM = big ? 6 : 3
const REFUTERS = big ? 3 : 2
const MAX_VERIFY = big ? 8 : 4

// CHANNEL-FIRST. Every channel answers the SAME core question independently,
// because the question of interest is "what does each source of truth say about
// this?" — not "how do I subdivide the topic". Subdivision comes later, and only
// where ranking shows it is needed. Each channel is blind to the others so that
// agreement between two of them is real corroboration rather than an echo.
phase('Sweep')
log(`Core question: ${topic}`)
const wanted = (args && args.channels) || CHANNELS.map(c => c.key)
const channels = CHANNELS.filter(c => wanted.includes(c.key))
log(`${channels.length} channels, each answering the same question: ${channels.map(c => c.key).join(' · ')}`)
log('Slack targets: #product-questions #discoverymeetings #engineering #ai #product-announcements #zendesk-tickets #customer-comms #dev-sso-support')

// Each thunk carries its channel key through success AND failure, because
// `parallel` resolves a dead agent to null and `.filter(Boolean)` then erases
// which channel died. That is exactly how this workflow reported
// `channels_unreachable: []` on a run where an agent had been killed by an API
// error mid-response — a false all-clear, produced by the tool built to prevent
// false all-clears.
const sweepAttempts = await parallel(channels.map(ch => () => agent(
  `Answer ONE question from ONE source of truth. You are blind to the other channels by design — if you and another channel agree, that agreement must be earned independently.

THE CORE QUESTION: ${topic}
${context ? `CONTEXT: ${context}` : ''}
${constraints ? `CONSTRAINTS: ${constraints}` : ''}

YOUR CHANNEL: ${ch.label}

${ch.brief}

Answer the core question AS YOUR CHANNEL SEES IT. Do not hedge toward what you imagine other channels would say, and do not broaden into the general topic — stay on the question.

Rules for every channel:
- Provenance is mandatory: HOW you obtained it, and the SOURCE.
- Grade honestly. measured means something returned it; stated means someone asserted it.
- Tag each finding functional (what the system does) or non-functional (how well it does it).
- **Report what you looked for and did NOT find.** A channel that should know about this and does not is one of the most informative results available, and it is lost if you return only hits.
- If your channel's tools are missing or unauthenticated, set reachable=false and name the tool. Do not substitute another channel's sources.
- Read-only throughout. Modify nothing.`,
  { schema: CHANNEL_FINDINGS, label: `sweep:${ch.key}`, phase: 'Sweep' }
).then(r => ({ key: ch.key, ok: Boolean(r), result: r }))
  .catch(e => ({ key: ch.key, ok: false, result: null, error: String(e && e.message || e) }))))

// The agent fills `channel` with the human label, not the key, so anything doing a
// keyed lookup downstream silently matches nothing. Keep both.
const sweeps = sweepAttempts.filter(a => a && a.ok).map(a => ({ ...a.result, channel: a.key, channel_label: a.result.channel || a.key }))
const died = sweepAttempts.filter(a => !a || !a.ok).map(a => (a && a.key) || 'unknown')
const selfReportedDown = sweeps.filter(x => !x.reachable).map(x => x.channel)
const unreachable = [...new Set([...died, ...selfReportedDown])]
if (died.length) log(`AGENT DIED, channel not covered: ${died.join(', ')} — counted as unreachable, not silently dropped`)
if (selfReportedDown.length) log(`TOOLS MISSING: ${selfReportedDown.join(', ')}`)
if (unreachable.length) log(`COVERAGE IS PARTIAL — ${unreachable.length} of ${channels.length} channels unreachable; the report will say so`)
const allChannelFindings = sweeps.flatMap(x => (x.findings || []).map(f => ({ ...f, channel: x.channel })))
const fnCount = allChannelFindings.filter(f => f.axis === 'non-functional').length
log(`${allChannelFindings.length} findings across ${sweeps.length} channels · ${fnCount} non-functional`)

if (!allChannelFindings.length) {
  log('Every channel came back empty. That is the finding — the organisation has no recorded position on this question.')
  return { topic, headline: 'No channel had anything to say. There is no recorded position on this question.', coverage: { channels_swept: channels.map(c => c.key), channels_unreachable: unreachable } }
}

// Rank and consolidate. A barrier is genuinely required: the whole point is to
// compare channels against each other, which cannot be done per-channel.
phase('Rank')
const consolidated = await agent(
  `Consolidate what SEVEN INDEPENDENT CHANNELS said about one question. Merge, rank, and surface disagreement.

THE CORE QUESTION: ${topic}

WHAT EACH CHANNEL RETURNED:
${JSON.stringify(sweeps.map(x => ({ channel: x.channel, reachable: x.reachable, findings: x.findings, absent: x.absent || [] })), null, 1)}

Your job, in this order:

1. MERGE. Where channels say the same thing, state it once. Do not let one claim appear three times because three agents phrased it differently.

2. RANK by evidence weight, 1-10. The ranking rule that matters: **corroboration across INDEPENDENT channels raises weight; a single channel caps it low no matter how confident that channel sounded.** A claim the code proves AND the database confirms outranks a claim someone asserted in Slack, even an emphatic assertion. A vendor's own benchmark is weight 2 whatever it says.

3. SURFACE CONTRADICTIONS explicitly. Two channels disagreeing is the single most valuable output here — it is where the organisation's understanding of itself is wrong. For each, name the positions by channel and **the one cheap check that would settle it**. Never average two contradicting positions into a compromise; that manufactures a claim no channel made.

4. NOTE SILENCE. A channel that should have known about this and returned nothing is evidence — a feature with no Slack trace and no Productboard entry is probably not a real commitment.

5. PROPOSE AT MOST 4 THREADS TO DEEPEN — only what is load-bearing, contradicted, or suspiciously silent. Not a general research agenda.`,
  { schema: CONSOLIDATION, label: 'rank-and-consolidate' }
)

log(`${(consolidated.ranked || []).length} merged claims · ${(consolidated.contradictions || []).length} contradictions · ${(consolidated.threads_to_deepen || []).length} threads to deepen`)
for (const c of (consolidated.contradictions || [])) log(`CONTRADICTION: ${String(c.subject).slice(0, 90)}`)

// Deepen only where ranking earned it, then refute. Pipeline, so a thread starts
// being attacked as soon as it returns.
phase('Deepen')
const dims = (consolidated.threads_to_deepen || []).slice(0, MAX_DIM).map((t, i) => ({
  key: `thread-${i + 1}`,
  question: t.question,
  unblocks: t.why,
  where_to_look: t.where_to_look || 'follow the channels that raised it',
  load_bearing: true,
}))
if (!dims.length) log('Ranking proposed no threads worth deepening — going straight to synthesis on the consolidated claims.')

const sweepDigest = JSON.stringify((consolidated.ranked || []).map(r => ({
  claim: r.claim, weight: r.weight, channels: r.channels_agreeing, grade: r.grade,
})), null, 1)

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

THE RANKED CONSOLIDATION FROM ALL CHANNELS — build on it, do not re-derive it, and CONTRADICT it where you find better evidence:
${sweepDigest}

Hard requirements:
- EVERY claim carries provenance: HOW you obtained it (the exact query, the file read, the command run) and the SOURCE (file:line, table.column, URL, or who said it).
- EVERY number names its environment. The same query has returned wildly different answers against different databases here.
- Grade honestly: measured (a query returned it) / stated (someone asserted it) / inference (reasoned from measurements) / assumed (a default you took). Do not inflate a grade.
- For each claim, state what observation WOULD FALSIFY it. A claim nothing could falsify is not a finding.
- Report dead ends. What you checked and found empty saves the next run real time.
- Read-only. Do not modify any file or database.

Prefer few well-sourced findings to many plausible ones.`,
    { schema: FINDINGS, label: `deepen:${d.key}`, phase: 'Deepen' }
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
- Where the refuters produced corrections, use the corrected weaker version, not the original.
- Cover BOTH AXES explicitly. Functional — what the system does. Non-functional — latency, error rates, throughput, cost, saturation. If the non-functional half is thin, say which channel was unreachable rather than letting the omission pass as a clean bill of health.
- Every identifier you cite carries a short gloss of what it is: SP-6 ("derive a graded set from edit history"), never a bare id. The reader tracks none of the numbering.
${unreachable.length ? `- CHANNELS THAT COULD NOT BE REACHED: ${unreachable.join(', ')}. State this in the document; partial coverage presented as complete is the failure mode here.` : ''}`,
  { schema: TWO_LAYER, label: 'synthesize' }
)

phase('Critique')
const critique = await agent(
  `You are the completeness critic. Find what this research MISSED.

TOPIC: ${topic}
CHANNELS SWEPT: ${channels.map(c => c.key).join(', ')}${unreachable.length ? ` — UNREACHABLE: ${unreachable.join(', ')}` : ''}
NON-FUNCTIONAL FINDINGS RETURNED: ${fnCount}${fnCount === 0 ? ' — ZERO, which for a suite analysis is itself a finding' : ''}
DIMENSIONS RESEARCHED: ${dims.map(d => d.key).join(', ')}
CHANNELS THAT RETURNED NOTHING THEY EXPECTED TO FIND: ${sweeps.flatMap(x => (x.absent || []).map(a => `${x.channel}: ${a}`)).join(' · ') || 'none reported — itself suspicious, since a channel that looked and found nothing should say so'}
CONTRADICTIONS SURFACED: ${(consolidated.contradictions || []).map(c => c.subject).join(' · ') || 'none — suspicious across seven independent channels'}
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
  contradictions: consolidated.contradictions || [],
  ranked: consolidated.ranked || [],
  // The whole sweep, returned. An earlier run produced 154 findings across six
  // channels — 27 of them measured Datadog numbers — and the caller saw only the six
  // claims that survived refutation, because nothing below the synthesis was returned.
  // Every one of those findings was recoverable only by hand-parsing the journal.
  channel_findings: sweeps.map(x => ({
    channel: x.channel, label: x.channel_label, reachable: x.reachable,
    findings: x.findings || [], absent: x.absent || [],
  })),
  coverage: {
    channels_requested: channels.map(c => c.key),
    channels_answered: sweeps.map(x => x.channel),
    channels_unreachable: unreachable,
    channels_agent_died: died,
    channels_tools_missing: selfReportedDown,
    non_functional_findings: fnCount,
  },
}
