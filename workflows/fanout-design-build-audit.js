export const meta = {
  name: 'fanout-design-build-audit',
  description: 'Design -> Design Review -> Build -> (Build Review + Adversarial Audit -> Fix)* until converged, per component. The canonical fan-out template.',
  whenToUse: 'Any multi-component build where each component has a clear file/test boundary and a spec to build against. Encodes the Fan-Out Workflow Pre-Flight Checklist and Observability & Self-Validating Output standards from global CLAUDE.md so they do not need to be re-derived into a bespoke script each time.',
  phases: [
    { title: 'Design', detail: 'one Designer agent per component confirms/produces an explicit interface contract before any code is written' },
    { title: 'Design Review', detail: 'independent adversarial check of the design itself, catches architecture mismatches before they get built' },
    { title: 'Build', detail: 'Implementer agents build against the REVIEWED design, real unit tests alongside' },
    { title: 'Build Review + Audit + Fix (looped)', detail: 'validate+verify against spec AND a separate adversarial break-it pass, fix findings, repeat until converged or the iteration cap is hit' },
  ],
}

/*
 * Expected `args` shape (pass via Workflow({..., args})):
 * {
 *   repo: 'D:/repo/AI/nuwa',                          // absolute repo root
 *   pyInterpreter: 'D:/repo/AI/nuwa/.venv/Scripts/python.exe',  // PINNED interpreter — determinism checklist item 5
 *   designDoc: 'D:/repo/AI/nuwa/docs/SOME-DESIGN.md',  // the spec every stage reads
 *   schemasFile: 'D:/repo/AI/nuwa/nuwa/ops/content/schemas.py', // the one shared contract, never redefined by a component
 *   maxLoopIterations: 3,                              // safety cap on the Build Review/Audit/Fix loop — logged if hit, never silent
 *   components: [
 *     {
 *       key: 'shot_matcher',
 *       file: 'D:/repo/AI/nuwa/nuwa/ops/content/shot_matcher.py',
 *       test: 'D:/repo/AI/nuwa/tests/test_shot_matcher.py',
 *       designBrief: 'One-paragraph pointer to the relevant design-doc section + a one-line summary of what this component does.',
 *     },
 *     // ...more components
 *   ],
 * }
 *
 * Every agent prompt below explicitly names its persona (checklist item 1) and receives determinism
 * (pinned interpreter + exact test command, checklist item 5) and the shared schema/contract
 * (checklist item 3) directly in the prompt text, per the Fan-Out Workflow Pre-Flight Checklist in
 * global CLAUDE.md. Verdicts use the validate-vs-verify split (checklist item 4): CONFIRMED /
 * PLAUSIBLE / FAILED, never a bare "looks good."
 */

const { repo, pyInterpreter, designDoc, schemasFile, components } = args
const MAX_LOOP = args.maxLoopIterations || 3

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    component: { type: 'string' },
    verdict: { type: 'string', enum: ['CONFIRMED', 'PLAUSIBLE', 'FAILED'] },
    tests_actually_pass: { type: 'boolean' },
    independently_verified: { type: 'boolean', description: 'did you personally run something real (test, render, script) rather than just read code' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          severity: { type: 'string', enum: ['blocker', 'concern', 'nit'] },
          finding: { type: 'string' },
        },
        required: ['severity', 'finding'],
      },
    },
  },
  required: ['component', 'verdict', 'tests_actually_pass', 'independently_verified', 'findings'],
}

// ---- Phase 1: Design ------------------------------------------------------------------------
phase('Design')

const designs = await parallel(components.map(c => () =>
  agent(`
Persona: Designer. Repo: ${repo}. Pinned interpreter: ${pyInterpreter}.
Design spec: ${designDoc}. Shared schema/contract (import from it, never redefine): ${schemasFile}.
Component: ${c.key}. Target file (may not exist yet): ${c.file}. Its test file: ${c.test}.
Brief: ${c.designBrief}

Do NOT write implementation code. Read the design spec's section for this component and the shared schema. Produce an explicit, concrete interface contract: the exact public function signature(s) this component must expose, exactly which schema types it consumes/produces, and the 3-5 concrete acceptance criteria a Build Review will later check it against (paraphrase the design doc's own "unit test plan" bullets for this component if present, or write equivalent ones if not). If you find the design brief/spec is ambiguous or under-specified for this component, say so explicitly rather than guessing — that's a real Design Review finding, not something to paper over.

Report: the exact signature(s), the schema types touched, and the acceptance criteria list.
`, { label: `design:${c.key}`, phase: 'Design', effort: 'high' })
    .then(result => ({ key: c.key, result }))
))

log(`Design phase done for: ${designs.filter(Boolean).map(d => d.key).join(', ')}`)

// ---- Phase 2: Design Review -----------------------------------------------------------------
phase('Design Review')

const designReviews = await parallel(components.map((c, i) => () =>
  agent(`
Persona: Reviewer (design-stage) — adversarial, you did not write this design. Repo: ${repo}.
Design spec: ${designDoc}. Shared schema: ${schemasFile}.
Component: ${c.key}. Proposed design/signature to review:
${JSON.stringify(designs[i] && designs[i].result, null, 2)}

Check BEFORE any code gets written: does this signature actually fit how it will be CALLED by other components (check the design doc for the calling component's expectations, not just this component's own section)? Does it depend on anything unlikely to exist in this environment (an API key, a native library, a system binary) without a stated fallback? Does it match the shared schema exactly, or does it quietly redefine/reshape a type? Would building this signature as-is force a later component to fight it (the kind of mismatch that's expensive to discover only after building — that is exactly what this phase exists to catch)?

Verdict: CONFIRMED (design is sound, build as specified) / PLAUSIBLE (buildable, minor concerns noted) / FAILED (a real architecture problem — name exactly what must change before building).
`, { label: `design-review:${c.key}`, phase: 'Design Review', schema: VERDICT_SCHEMA, effort: 'high', agentType: 'reviewer' })
))

const designBlockers = designReviews.filter(Boolean).filter(r => r.verdict === 'FAILED')
if (designBlockers.length) {
  log(`Design Review found ${designBlockers.length} FAILED design(s) — stopping before Build. Fix the design first.`)
  return { stage: 'design-review-failed', designs, designReviews }
}
log(`Design Review clean: ${designReviews.filter(Boolean).map(r => `${r.component}=${r.verdict}`).join(', ')}`)

// ---- Phase 3: Build ---------------------------------------------------------------------------
phase('Build')

const builds = await parallel(components.map((c, i) => () =>
  agent(`
Persona: Implementer. Repo: ${repo}. Pinned interpreter (use exactly this): ${pyInterpreter}.
Design spec: ${designDoc}. Shared schema (import from it, never redefine): ${schemasFile}.
Component: ${c.key}. File: ${c.file}. Test: ${c.test}.
Reviewed, approved design to build against (do not deviate from this without noting why in your report):
${JSON.stringify(designs[i] && designs[i].result, null, 2)}

Write real, working, unit-tested code — not stubs. Tests alongside implementation. Every test must run with zero network/external-API calls (inject any real seam as a callable parameter, mock/fake it in tests). Test command: cd ${repo} && ${pyInterpreter} -m pytest ${c.test} -v — get it green before reporting.

Durable build evidence (dark-factory phase 4 requirement, D15 in ~/.claude/docs/DECISIONS.md): once green, run your own real code against one real/representative input and write the actual output — not a description of it — to ${repo}/docs/build-records/${c.key}.md, with today's date. This is what a later regression points at to see the last-known-good output, not just a passing test name.

Report: what you built (file:line summary), the final pytest line, and confirm the build-record file was written.
`, { label: `build:${c.key}`, phase: 'Build', effort: 'high', agentType: 'implementer' })
    .then(result => ({ key: c.key, result }))
))

log(`Build phase done for: ${builds.filter(Boolean).map(b => b.key).join(', ')}`)

// ---- Phase 4: Build Review + Adversarial Audit + Fix, looped until converged ------------------
phase('Build Review + Audit + Fix (looped)')

let iteration = 0
let outstanding = components.slice()
const historyByComponent = {}

while (outstanding.length && iteration < MAX_LOOP) {
  iteration += 1
  log(`Loop iteration ${iteration}/${MAX_LOOP} — checking: ${outstanding.map(c => c.key).join(', ')}`)

  // Build Review (validate+verify against spec) and Adversarial Audit (try to break it) are
  // deliberately TWO DIFFERENT LENSES on the same component, not one combined check — a
  // spec-fidelity reviewer and someone actively trying to break it catch different things.
  const reviewAndAudit = await parallel(outstanding.flatMap(c => [
    () => agent(`
Persona: Reviewer (build-stage) — adversarial, you did not write this code. Repo: ${repo}. Pinned interpreter: ${pyInterpreter}.
Component: ${c.key}. File: ${c.file}. Test: ${c.test}. Design spec: ${designDoc}. Schema: ${schemasFile}.
Run the test command yourself: cd ${repo} && ${pyInterpreter} -m pytest ${c.test} -v — record the REAL result, do not trust any prior self-report.
VALIDATE: does the shipped signature match the approved design? Does it import from the shared schema rather than redefining types?
VERIFY: does it actually fulfill the design's INTENT (not just its shape)? Read every test and flag any that's tautological (would pass even if the real behavior were subtly wrong).
Verdict: CONFIRMED/PLAUSIBLE/FAILED with named findings (blocker/concern/nit).
`, { label: `build-review:${c.key}:iter${iteration}`, phase: 'Build Review + Audit + Fix (looped)', schema: VERDICT_SCHEMA, effort: 'high', agentType: 'reviewer' })
      .then(r => r && ({ ...r, lens: 'build-review' })),
    () => agent(`
Your only job this pass is to break this component, not to confirm it works — a distinct lens from the build-review pass, which checks spec fidelity; you are specifically hunting for scenarios nobody has tried yet. Repo: ${repo}. Pinned interpreter: ${pyInterpreter}.
Component: ${c.key}. File: ${c.file}. Design spec: ${designDoc}. Schema: ${schemasFile}.
Construct at least 2 scenarios the component's own tests do NOT cover (edge cases, malformed input, empty/zero-length input, a value outside the schema's expected enum, concurrent/repeated calls if relevant) and actually RUN them for real against the pinned interpreter — don't just reason about them. Report exactly what you tried and what actually happened for each.
Verdict: CONFIRMED (survived every attempt to break it) / PLAUSIBLE (survived with a caveat, name it) / FAILED (you broke it — describe exactly how).
`, { label: `audit:${c.key}:iter${iteration}`, phase: 'Build Review + Audit + Fix (looped)', schema: VERDICT_SCHEMA, effort: 'high', agentType: 'reviewer' })
      .then(r => r && ({ ...r, lens: 'adversarial-audit' })),
  ]))

  const byComponent = {}
  for (const r of reviewAndAudit.filter(Boolean)) {
    byComponent[r.component] = byComponent[r.component] || []
    byComponent[r.component].push(r)
  }
  for (const c of outstanding) {
    historyByComponent[c.key] = historyByComponent[c.key] || []
    historyByComponent[c.key].push({ iteration, results: byComponent[c.key] || [] })
  }

  const stillBroken = outstanding.filter(c => (byComponent[c.key] || []).some(r => r.verdict === 'FAILED'))

  if (!stillBroken.length) {
    log(`Iteration ${iteration}: all components CONFIRMED/PLAUSIBLE from both lenses — converged.`)
    outstanding = []
    break
  }

  log(`Iteration ${iteration}: ${stillBroken.length} component(s) still have FAILED findings — fixing: ${stillBroken.map(c => c.key).join(', ')}`)

  await parallel(stillBroken.map(c => () => {
    const failedFindings = (byComponent[c.key] || [])
      .filter(r => r.verdict === 'FAILED')
      .flatMap(r => r.findings.filter(f => f.severity === 'blocker').map(f => `[${r.lens}] ${f.finding}`))
    return agent(`
Persona: Implementer fixing specific, already-diagnosed issues — not a general cleanup pass. Repo: ${repo}. Pinned interpreter: ${pyInterpreter}.
Component: ${c.key}. File: ${c.file}. Test: ${c.test}. Design spec: ${designDoc}. Schema: ${schemasFile} (do not change unless a finding explicitly says to).
Blocker findings to fix, from an independent Reviewer and a separate Adversarial Auditor:
${failedFindings.map((f, idx) => `${idx + 1}. ${f}`).join('\n')}

Apply exactly these fixes. Add/update tests proving each fix. Test command: cd ${repo} && ${pyInterpreter} -m pytest ${c.test} -v — get it green. If the fix changed real behavior, refresh ${repo}/docs/build-records/${c.key}.md with the new real output (D15). Report what changed and the final pytest line.
`, { label: `fix:${c.key}:iter${iteration}`, phase: 'Build Review + Audit + Fix (looped)', effort: 'high', agentType: 'implementer' })
  }))

  outstanding = stillBroken
}

if (outstanding.length) {
  log(`Loop hit the ${MAX_LOOP}-iteration cap with ${outstanding.length} component(s) still unresolved: ${outstanding.map(c => c.key).join(', ')} — stopping for human review rather than looping silently forever.`)
}

return {
  designs,
  designReviews,
  builds,
  converged: outstanding.length === 0,
  unresolvedComponents: outstanding.map(c => c.key),
  loopHistory: historyByComponent,
  iterationsUsed: iteration,
}
