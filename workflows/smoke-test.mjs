#!/usr/bin/env node
// Execute a workflow script's control flow with stubbed agents.
//
// Why this exists: `node --check` validates syntax and nothing else, and two
// runtime bugs got past it in one session — an unescaped backtick that silently
// truncated a template literal, and a reference to a variable a refactor had
// deleted, which would have crashed at the last phase after ~20 agents had
// already run. Both were free to catch and expensive to hit.
//
//   node workflows/smoke-test.mjs workflows/adversarial-research.js
import fs from 'fs';

const file = process.argv[2];
if (!file) { console.error('usage: smoke-test.mjs <workflow.js>'); process.exit(2); }
let src = fs.readFileSync(file, 'utf8').replace(/^export const meta/m, 'const meta');

const calls = [];
// Fakes are matched off the schema's own field names, so a new schema shape needs
// a new branch here — deliberately, since a silently-empty return would make the
// test pass on a workflow that cannot actually run.
const agent = async (prompt, opts = {}) => {
  calls.push(opts.label || '(unlabelled)');
  const s = JSON.stringify(opts.schema || {});
  if (s.includes('reachable')) return { channel: 'stub', reachable: true, findings: [{ claim: 'c', grade: 'measured', how: 'h', source: 's', axis: 'functional' }], absent: ['nothing'] };
  if (s.includes('ranked')) return { ranked: [{ claim: 'c', weight: 8, channels_agreeing: ['code', 'database'], grade: 'measured', axis: 'functional' }], contradictions: [{ subject: 'x', positions: ['a', 'b'], how_to_settle: 'q' }], threads_to_deepen: [{ question: 'q1', why: 'load-bearing', where_to_look: 'code' }] };
  if (s.includes('would_falsify')) return { dimension: 'thread-1', findings: [{ claim: 'c2', grade: 'measured', provenance: { how: 'h', source: 's', environment: 'production' }, load_bearing: true, would_falsify: 'w' }], dead_ends: [] };
  if (s.includes('refuted')) return { refuted: false, reasoning: 'r' };
  if (s.includes('summary_sections')) return { headline: 'H', summary_sections: [{ heading: 'a', body: 'b', detail_anchor: 'x' }], detail_sections: [{ anchor: 'x', heading: 'a', body: 'b', provenance: 'p' }] };
  if (s.includes('gaps')) return { gaps: [{ what: 'w', why_it_matters: 'm' }], verdict: 'v' };
  if (s.includes('entry_points')) return { tables: [{ name: 't1', rows: 10, why: 'w' }], entry_points: ['c#a'], wiki_pages: ['P'], excluded: ['x'] };
  if (s.includes('load_bearing') && s.includes('lens')) return { lens: 'stub', findings: [{ claim: 'c', grade: 'measured', how: 'h', source: 's', environment: 'production', load_bearing: true, dull_explanation: 'd' }], absent: ['a'], locations: [{ looking_for: 'x', found_in: 'y', not_in: 'z' }] };
  if (s.includes('corrected_claim')) return { verdict: 'narrowed', reasoning: 'r', corrected_claim: 'cc', queries_run: ['q'] };
  if (s.includes('caveats')) return { headline: 'H', summary_sections: [{ heading: 'a', body: 'b', confidence: 'measured' }], detail_sections: [{ heading: 'a', body: 'b', provenance: 'p' }], caveats: ['c'] };
  return {};
};
const parallel = async (thunks) => Promise.all(thunks.map(t => t()));
const pipeline = async (items, ...stages) => Promise.all(items.map(async (it, i) => {
  let v = it;
  for (const st of stages) v = await st(v, it, i);
  return v;
}));
const phases = [];
const phase = (t) => phases.push(t);
const log = () => {};
const budget = { total: null, spent: () => 0, remaining: () => Infinity };
// Superset of the arg names workflows read, so one harness smoke-tests any of them.
const args = { topic: 'smoke-test question', module: 'smoke-test-module',
               context: 'ctx', constraints: 'read-only' };

const fn = new Function('agent', 'parallel', 'pipeline', 'phase', 'log', 'budget', 'args',
  '"use strict"; return (async()=>{' + src + '})()');
try {
  const out = await fn(agent, parallel, pipeline, phase, log, budget, args);
  console.log('phases   :', phases.join(' -> '));
  console.log('agents   :', calls.length, '·', calls.join(' '));
  console.log('returns  :', Object.keys(out || {}).join(', ') || '(nothing — suspicious)');
  console.log('PASS');
} catch (e) {
  console.log('FAIL:', e.message);
  process.exit(1);
}
