---
paths:
  - "**/*.js"
  - "**/*.mjs"
  - "**/*.cjs"
  - "**/package.json"
---
# JavaScript (Node ESM) ground rules

Baseline: Node 22+ LTS (Node 20 is deprecated on Vercel from 2026-10-01; AI SDK 7 needs 22), ESM (`"type": "module"`), pnpm. Each rule: **the rule**, then the reason.

## Imports and modules
- **Static `import` at the top of the module**; `node:` prefix for built-ins (`node:fs`, `node:path`).
  Dynamic `import()` only for a genuinely optional or lazy-loaded module, with a comment.
- Named exports; no default-export grab bags. One module, one responsibility.
- Dependencies declared in `package.json`; zero-dependency libraries stay zero-dependency.

## Async and processes
- `async`/`await`, never mixed with raw `.then` chains in the same function.
- No sync subprocess or sync network call on a daemon's hot path (`execSync`/`spawnSync` freeze the
  event loop). Use the repo's async exec helper.
- Child processes get `windowsHide: true`; argv arrays, not shell strings, unless the shell is the point.
- Every `fetch` has `AbortSignal.timeout(ms)`.

## Errors
- Catch at boundaries only; an error message that may contain a URL with a token is never logged.
- Typed refusals: stable reason strings or constants that callers compare, never substring matching.

## Structure and data
- Dependency injection for clock, fs, fetch, logger, so pure logic tests with no I/O.
- Constants for every threshold; no magic numbers.
- JSON crossing a boundary is validated against its schema; state files written atomically
  (temp + rename).

## Tests (node:test)
- Follow [testing.md](testing.md) (what to test, minimal asserts, prove it can fail); below are the language specifics.
- `node:test` + `node:assert/strict`; filesystem tests use `mkdtempSync` and clean up in `finally`.
- Behaviour over call strings: assert observable state (files, exit codes, outputs), not the exact
  commands an implementation issues (review finding 2026-10-24, Foreman post-merge views).
- **Minimal asserts: one behaviour per test, 1-3 asserts on the outcome.** No `deepEqual` of a
  whole payload unless the full shape is the requirement; assert the field that carries the
  behaviour (owner correction 2026-10-25).
