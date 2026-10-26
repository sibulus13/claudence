---
paths:
  - "**/*.py"
  - "**/pyproject.toml"
  - "**/requirements*.txt"
---
# Python ground rules

Baseline: PEP 8 + PEP 20; 3.12. Each rule: **the rule**, then the reason or incident.

## Imports and dependencies
- **All imports at the top of the module**, grouped stdlib / third-party / local, one blank line
  between groups, `from __future__ import annotations` first. No imports inside functions.
- **Allowed exceptions, each with a one-line comment saying which:** (a) breaking a real import
  cycle, (b) a heavy optional dependency on a rarely used CLI path, (c) a platform-only module.
  "It might be missing" is NOT an exception: declare it instead.
  - Incident 2026-10-25: `from notifly.hub import ...` inside a function, copied from a lazy-import
    workaround whose real cause was an undeclared dependency.
- **Every third-party or sibling-package import is declared** (`requirements.txt` /
  `pyproject.toml`; a local package as `-e <path>`). An undeclared import that works on this machine
  is a latent failure in a fresh venv or worktree.
- No wildcard imports; no `sys.path` edits in library code (scripts may, at the top, with a comment).

## Structure
- Module docstring says what it is for and how to run it.
- Constants in UPPER_CASE at the top; no magic numbers in bodies.
- Pure functions for logic, I/O at the edges, so tests need no network or disk.
- Paths from `Path(__file__).resolve()`, never hardcoded repo paths.

## Types and data
- Type hints on public functions; `X | None`, built-in generics (`list[str]`).
- Structured data crossing a boundary has a schema (JSON Schema, dataclass, pydantic); validate at
  the boundary, trust inside.

## Errors
- Catch at system boundaries (network, subprocess, external files, user input) and catch the
  specific exception; never bare `except:`. A broad `except Exception` only on a best-effort side
  path, with a comment, and it records what failed.
- Never log or return a secret; an exception message from an HTTP client may contain the URL/token.

## I/O and processes
- `encoding="utf-8"` on every text open; write files with `newline="\n"` unless preserving CRLF.
- Atomic writes for state: temp file + `os.replace`.
- `subprocess.run([...], timeout=..., capture_output=True)` with an argv list (no `shell=True`);
  on Windows add `creationflags=subprocess.CREATE_NO_WINDOW` for background work.
- Every network call has a timeout. Long jobs print progress and write a heartbeat.

## Tests (pytest)
- Follow [testing.md](testing.md) (what to test, minimal asserts, prove it can fail); below are the language specifics.
- Tests are sanity, one per acceptance criterion, or a regression named after its incident.
- **Minimal asserts: one behaviour per test, asserted by its outcome (usually 1-3 asserts).** Assert
  the property that matters ("the note reaches the sink", "a foreign chat is ignored"), not the
  whole object, not exact formatting, not every intermediate call. No `==` on a full dict/envelope
  unless the full shape IS the requirement. A test that breaks on a harmless wording or field-order
  change is pinning implementation (owner correction 2026-10-25).
- No real network, phone or production paths in tests: mock adapters by default, live tests behind
  an env flag (e.g. `NOTIFLY_LIVE=1`) and skipped otherwise.
- Use `tmp_path` / `monkeypatch`; autouse fixtures sandbox anything a test could write for real.
