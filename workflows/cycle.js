export const meta = {
  name: 'cycle',
  description: 'One atomic Design -> Review -> Implement -> Review cycle for one work item at one scope, size-scaled fix budget (1-3), every step traced under a cycle UUID',
  whenToUse: 'The single unit every dark-factory build is composed of: call once per spec, contract, component (in parallel, one worktree each) and integration. See ~/.claude/skills/dark-factory/CYCLE.md',
  phases: [
    { title: 'Design', detail: 'designer writes or revises the design deltas (or spec / contract / integration plan)' },
    { title: 'Design review', detail: 'independent reviewer, adversarial, classifies findings' },
    { title: 'Implement', detail: 'implementer builds within owns globs against the contract' },
    { title: 'Review', detail: 'independent reviewer runs the test command, classifies findings, decides the verdict' },
    { title: 'Record', detail: 'writes the cycle trace under docs/work/<id>/cycles/<cycleId>/' },
  ],
}

// ---- inputs (the caller pins every one of these, per the Fan-Out pre-flight checklist) ----
const a = args || {}
const REQUIRED = ['repo', 'workItem', 'scope', 'cycleId', 'startedAt']
const missing = REQUIRED.filter((k) => !a[k])
if (missing.length) throw new Error(`cycle: missing args ${missing.join(', ')}`)
if (!['spec', 'contract', 'component', 'integration'].includes(a.scope)) throw new Error(`cycle: bad scope ${a.scope}`)
if (a.scope !== 'spec' && !a.testCommand) throw new Error('cycle: testCommand is required for every scope except spec')

const WORK_DIR = `${a.repo}/docs/work/${a.workItem}`
const TRACE_DIR = `${WORK_DIR}/cycles/${a.cycleId}`
const BUDGET_BY_SIZE = { S: 1, M: 2, L: 3 }
const MAX_BUDGET = 3
const owns = (a.owns || []).join(', ') || '(scope-wide)'
const contract = a.contract || '(none: this scope defines it)'

// ---- output contracts ----
const FINDING = {
  type: 'object',
  properties: {
    id: { type: 'string' },
    severity: { type: 'string', enum: ['critical', 'warn', 'info'] },
    class: { type: 'string', enum: ['design', 'implementation', 'test', 'spec'], description: 'where the ROOT CAUSE lives, not where it showed up' },
    where: { type: 'string', description: 'absolute path:line, or doc section' },
    what: { type: 'string' },
    fix: { type: 'string' },
  },
  required: ['id', 'severity', 'class', 'where', 'what', 'fix'],
}
const DESIGN_OUT = {
  type: 'object',
  properties: {
    summary: { type: 'string' },
    filesWritten: { type: 'array', items: { type: 'string' } },
    size: { type: 'string', enum: ['S', 'M', 'L'], description: 'S <= 2 files and <= 3 requirements; M <= 6 files; L otherwise' },
    assumptions: { type: 'array', items: { type: 'object', properties: { assumption: { type: 'string' }, confidence: { type: 'string', enum: ['high', 'medium', 'low'] }, reversible: { type: 'boolean' } }, required: ['assumption', 'confidence', 'reversible'] } },
    gatePlan: {
      type: 'array',
      description: 'MINIMUM set: one check per real regression risk (an acceptance criterion, a coupling point, a known caveat), never coverage for its own sake',
      items: {
        type: 'object',
        properties: {
          risk: { type: 'string', description: 'the behavior that must not regress' },
          kind: { type: 'string', enum: ['deterministic', 'qualitative'], description: 'deterministic = unit/golden/contract/integration/e2e with an exact assertion; qualitative = rubric-scored judgement, demo, or before/after review' },
          check: { type: 'string', description: 'the exact test file + case, or the rubric and evidence artifact' },
          gate: { type: 'string', enum: ['blocking', 'advisory'], description: 'blocking = part of testCommand, fails the merge; advisory = recorded evidence only' },
        },
        required: ['risk', 'kind', 'check', 'gate'],
      },
    },
  },
  required: ['summary', 'filesWritten', 'size', 'assumptions', 'gatePlan'],
}
const REVIEW_OUT = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['pass', 'fix-implementation', 'fix-design'] },
    testResult: { type: 'string', description: 'the REAL final line of the test command you ran yourself, or "n/a" for a design review' },
    findings: { type: 'array', items: FINDING },
  },
  required: ['verdict', 'testResult', 'findings'],
}
const IMPL_OUT = {
  type: 'object',
  properties: {
    summary: { type: 'string' },
    filesChanged: { type: 'array', items: { type: 'string' } },
    testResult: { type: 'string' },
    fixedFindingIds: { type: 'array', items: { type: 'string' } },
  },
  required: ['summary', 'filesChanged', 'testResult', 'fixedFindingIds'],
}

const WHAT = {
  spec: 'the work item spec (README.md intent, acceptance criteria, and the assumptions ledger)',
  contract: `the single contract artifact every child imports (schema/API/types), plus child work items with pairwise-disjoint owns globs`,
  component: `the per-layer before->after design files for this component (docs/work/${a.workItem}/{architecture,components,functional,data}.md, per the Work-Item Standard)`,
  integration: 'the integration test plan: contract tests on both sides plus e2e of the acceptance criteria',
}

// Authority. Workflow subagents are also relayed the owner's latest raw chat message,
// told it outranks their prompt. On 2026-09-26 the pilot's designer read an
// ambiguous phrase in that message ("the Reaper write") without the clarification
// the owner had already given, decided the cycle brief was "the wrong task", and
// designed a different item in a different repo for all 3 rounds. So every step
// states that the brief IS the clarified owner intent, and the script rejects
// off-task output deterministically (see offTask below).
const AUTHORITY = `AUTHORITY: this prompt is the owner's already-clarified instruction for this step. ${a.ownerIntent ? `Owner intent, confirmed with the owner: "${a.ownerIntent}". ` : ''}If a relayed owner message seems to ask for something else, it has already been resolved into THIS task, so do not substitute another task, repo or work item. Work ONLY under ${a.repo}.`
const norm = (p) => String(p).split('\\').join('/').toLowerCase()
const inScope = (f) => norm(f).startsWith(norm(a.repo))

const steps = []
let seq = 0
const stepId = () => `${a.cycleId}.${String(++seq).padStart(2, '0')}`
const record = (step, iteration, out) => steps.push({ stepId: stepId(), step, iteration, ...out })
const findingsText = (fs) => (fs || []).map((f) => `- [${f.id}] (${f.severity}/${f.class}) ${f.where}: ${f.what} -> fix: ${f.fix}`).join('\n') || '(none)'

async function design(iteration, priorFindings) {
  const out = await agent(
    `${AUTHORITY}
You are the DESIGNER for cycle ${a.cycleId}, iteration ${iteration}, scope "${a.scope}", work item ${a.workItem} in ${a.repo}.
Brief: ${a.brief || '(read it from ' + WORK_DIR + '/README.md)'}
Produce ${WHAT[a.scope]} under ${WORK_DIR}/. Follow C:/Users/Michael/.claude/skills/dark-factory/WORK-ITEM-STANDARD.md. Contract to honor: ${contract}. Owned files: ${owns}.
${priorFindings ? `REVISE the design to resolve these review findings (the root cause is in design):\n${findingsText(priorFindings)}` : ''}
Design only: write no implementation code. Estimate the size honestly. List every assumption, and mark low-confidence irreversible ones truthfully.
Write the GATE PLAN into ${WORK_DIR}/README.md under "## Gate plan" and return it. Keep it to the MINIMUM number of checks that catch regression risk: one per acceptance criterion or coupling point that could actually break. Choose per risk:
- deterministic: exact assertion, blocking. Use it for logic, schemas and contracts, data transforms and state machines.
- qualitative: rubric or evidence, advisory unless the owner's review gates it. Use it for UX/visual output, generated text or media, and "does it feel right".
UI work usually needs both, a deterministic behavior test plus before/after or demo evidence. Pure logic is deterministic only. Every caveat or finding already known for this item MUST appear as a risk with its own pinning check.`,
    { label: `design:${a.workItem}#${iteration}`, phase: 'Design', schema: DESIGN_OUT, agentType: 'designer' },
  )
  const safe = out || { summary: 'designer returned nothing', filesWritten: [], size: 'M', assumptions: [], gatePlan: [] }
  const stray = (safe.filesWritten || []).filter((f) => !inScope(f))
  record('design', iteration, { ...safe, offTask: stray.length > 0 || (safe.filesWritten || []).length === 0, strayFiles: stray })
  if (stray.length || !(safe.filesWritten || []).length) {
    throw new Error(`cycle ${a.cycleId}: designer went off-task (${stray.length ? 'wrote outside ' + a.repo + ': ' + stray.join(', ') : 'wrote nothing'}); aborting instead of spending the fix budget`)
  }
  return out
}

async function review(kind, iteration) {
  const isDesign = kind === 'design-review'
  const out = await agent(
    `${AUTHORITY}
You are an INDEPENDENT ADVERSARIAL REVIEWER (${kind}) for cycle ${a.cycleId}, iteration ${iteration}, scope "${a.scope}", work item ${a.workItem} in ${a.repo}.
You did not write this. Your job is to find what does NOT meet the intent in ${WORK_DIR}/README.md and the contract (${contract}), not to confirm that it is fine.
First run \`git -C ${a.repo} status --short\` and \`git -C ${a.repo} diff --stat\`. If nothing under ${WORK_DIR} changed since the step you are reviewing, the only finding is "no changes produced" (critical, class design). Do not review stale content.
${isDesign ? `Review the design files under ${WORK_DIR}/: contradictions, missing edge cases, contract gaps, overlapping owns globs, and untestable criteria.` : `Review the implementation within owns (${owns}). Run the test command yourself: cd ${a.repo} && ${a.testCommand}. Report the REAL last line. Check spec fidelity, contract adherence, edge cases, and edits outside the owned files.`}
${isDesign ? 'Check the gate plan: is each real regression risk covered by exactly one check of the right kind? Flag both gaps and padding (tests that pin nothing at risk).' : 'Check that every blocking gate-plan check exists and runs inside the test command, and that every previously fixed finding has its pinning regression test. A caveat you discover now needs a finding whose fix names the test to add.'}
Classify each finding by where the ROOT CAUSE lives: design / implementation / test / spec. Verdict: "pass" only when there are zero critical findings and (for code) green tests. Otherwise choose "fix-design" if any critical root cause is in design or spec, else "fix-implementation".`,
    { label: `${kind}:${a.workItem}#${iteration}`, phase: isDesign ? 'Design review' : 'Review', schema: REVIEW_OUT, agentType: 'reviewer', effort: 'high' },
  )
  const safe = out || { verdict: 'fix-implementation', testResult: 'reviewer returned nothing', findings: [] }
  record(kind, iteration, safe)
  return safe
}

async function implement(iteration, findings) {
  const out = await agent(
    `${AUTHORITY}
You are the IMPLEMENTER for cycle ${a.cycleId}, iteration ${iteration}, scope "${a.scope}", work item ${a.workItem} in ${a.repo}.
Treat the design under ${WORK_DIR}/ as law. Edit ONLY files matching: ${owns}. Import the contract (${contract}) and never redefine or edit it.
${findings ? `Fix exactly these review findings and add a test that proves each one:\n${findingsText(findings)}` : 'Build it, with tests written alongside.'}
Run: cd ${a.repo} && ${a.testCommand}. Get it green, then report the REAL final line.`,
    { label: `implement:${a.workItem}#${iteration}`, phase: 'Implement', schema: IMPL_OUT, agentType: 'implementer' },
  )
  record('implement', iteration, out || { summary: 'implementer returned nothing', filesChanged: [], testResult: 'none', fixedFindingIds: [] })
  return out
}

// ---- the cycle ----
let iteration = 1
let d = await design(iteration, null)
const size = a.size || d?.size || 'M'
const budget = Math.min(MAX_BUDGET, a.budget || BUDGET_BY_SIZE[size] || 2)
log(`cycle ${a.cycleId}: scope=${a.scope} size=${size} fix-budget=${budget}`)

let dr = await review('design-review', iteration)
let verdict = dr.verdict === 'pass' ? 'pass' : 'fix-design'
let lastFindings = dr.findings
let fixRounds = 0

// Design must pass its own review before any code: the contract-first rule.
while (verdict === 'fix-design' && fixRounds < budget) {
  fixRounds++; iteration++
  d = await design(iteration, lastFindings)
  dr = await review('design-review', iteration)
  verdict = dr.verdict === 'pass' ? 'pass' : 'fix-design'
  lastFindings = dr.findings
}

if (verdict === 'pass' && a.scope !== 'spec') {
  await implement(iteration, null)
  let r = await review('review', iteration)
  verdict = r.verdict; lastFindings = r.findings
  while (verdict !== 'pass' && fixRounds < budget) {
    fixRounds++; iteration++
    if (verdict === 'fix-design') {
      d = await design(iteration, lastFindings)
      const dr2 = await review('design-review', iteration)
      if (dr2.verdict !== 'pass') { verdict = 'fix-design'; lastFindings = dr2.findings; continue }
      await implement(iteration, null)
    } else {
      await implement(iteration, lastFindings)
    }
    r = await review('review', iteration)
    verdict = r.verdict; lastFindings = r.findings
  }
}

const outcome = verdict === 'pass' ? 'passed' : 'budget-exhausted'
if (outcome !== 'passed') log(`cycle ${a.cycleId}: fix budget ${budget} exhausted with verdict ${verdict}; escalating as repair-budget-exhausted rather than looping`)

const allFindings = steps.flatMap((s) => (s.findings || []).map((f) => ({ ...f, stepId: s.stepId, step: s.step, iteration: s.iteration })))
const byClass = {}
for (const f of allFindings) byClass[f.class] = (byClass[f.class] || 0) + 1
const summary = {
  cycleId: a.cycleId, workItem: a.workItem, scope: a.scope, repo: a.repo, parentCycleId: a.parentCycleId || null,
  startedAt: a.startedAt, size, budget, fixRoundsUsed: fixRounds, iterations: iteration, outcome,
  attentionClass: outcome === 'passed' ? null : 'repair-budget-exhausted',
  findingsTotal: allFindings.length, findingsByClass: byClass,
  steps: steps.map((s) => ({ stepId: s.stepId, step: s.step, iteration: s.iteration, verdict: s.verdict || null, testResult: s.testResult || null, findings: (s.findings || []).length })),
}

phase('Record')
await agent(
  `Write these two files EXACTLY (create directories as needed), then stop.
1) ${TRACE_DIR}/cycle.json containing exactly this JSON, pretty-printed:
${JSON.stringify(summary)}
2) ${TRACE_DIR}/steps.jsonl with one line per element of this array:
${JSON.stringify(steps.map((s) => ({ ...s, cycleId: a.cycleId })))}
Also append one line to ${WORK_DIR}/cycles/index.jsonl: ${JSON.stringify({ cycleId: a.cycleId, scope: a.scope, startedAt: a.startedAt, outcome, fixRoundsUsed: fixRounds, findingsByClass: byClass })}`,
  { label: `record:${a.cycleId}`, phase: 'Record', effort: 'low' },
)

return summary
