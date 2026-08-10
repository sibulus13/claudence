---
as-of: 2026-03-30
status: archived
superseded-by: ../STATE.md
---

> **ARCHIVED — describes the pre-port Windows harness.** Superseded by
> [`../STATE.md`](../STATE.md) on 2026-08-10. Every `.ps1` path, the Pester suite, and
> `skills/retrospect.md` named below were replaced by python3/zsh equivalents in the macOS port
> ([`../MACOS-PORT.md`](../MACOS-PORT.md)).
>
> **Kept for the root cause, not the content.** This file *was* the project's state page, and it
> went 4½ months stale unnoticed because it sat under a filename that the state-reader shipped in
> this same repo (`scripts/workspace-state.py`) does not recognise as `STATE.md`. A convention with
> a reader and no writer reaches only the projects where someone typed the file out by hand — which
> is why `templates/STATE.md` now exists. Retrieved as evidence when the same question was asked
> again on 2026-08-10 and nobody could find where it had been answered before.

# Claudence — Status TLDR

> Hooks-driven friction tracking and telemetry for Claude Code on Windows.
> Repo: `~/.claude` — live at **https://github.com/sibulus13/claudence**

---

## What's Working

| Feature | Status |
|---------|--------|
| Live status bar | ✅ After every response — Prompts, Overrides, Additions, Blocked, ctx%, cost, elapsed |
| Sound on stop | ✅ Chimes (ring-half.wav). Louder ring if elapsed >30s, score ≥5, or retrospect threshold hit |
| Ding on permission request | ✅ ding-half.wav plays async on every PermissionRequest event |
| Prompt classification | ✅ 3 signals: first_prompt / followup / override (+3) / addition (+1) |
| Per-session friction report | ✅ JSON to `telemetry/reports/<id>.json` on every Stop |
| Rolling averages | ✅ Window=5 sessions, tracks o_rate / a_rate / b_rate |
| Trend indicators | ✅ `+`/`-` on Overrides and Blocked when rate drifts >10pp from average |
| Retrospection prompt | ✅ Fires when cumulative score ≥6 across ≥3 sessions → suggests `/retrospect` |
| `/retrospect` skill | ✅ Defined in `skills/retrospect.md`. Documented in CLAUDE.md. Visible after full restart |
| Pester test suite | ✅ 57 tests across Test-IsOverride, Test-IsAddition, Get-PromptClassification |
| Pre-commit hook | ✅ Blocks commits touching `telemetry/` if tests fail |
| `setup.ps1` bootstrap | ✅ Creates dirs, generates WAV files, installs Pester 5 + NuGet provider, wires pre-commit hook |
| GitHub repo | ✅ Pushed to `main` at https://github.com/sibulus13/claudence |

## Hooks Wired

| Event | Script | Blocking |
|-------|--------|---------|
| UserPromptSubmit | log-prompt.ps1 | yes (sync — ensures status bar is current) |
| Stop | analyze-session.ps1 | yes (sync — plays sound, writes report) |
| PostToolUse | log-tool-done.ps1 | no |
| PostCompact | record-compact.ps1 | no |
| PermissionRequest | log-permission.ps1 + ding | no |

## Recently Fixed (this session)

- **GitHub push** — repo created at `sibulus13/claudence`, pushed to `main` (was on `master`); upstream tracking corrected
- **Path de-personalization** — settings.json hook commands resolve `$USERPROFILE` and the `.ps1` scripts resolve `$HOME`, so no hardcoded username remains and no per-machine patching is needed
- **setup.ps1: NuGet provider guard** — `Install-Module Pester` fails silently without NuGet provider; guard added
- **setup.ps1: skills/ dir** — now explicitly created; previously relied on robocopy alone
- **setup.ps1: post-install guidance** — added clear "quit and reopen Claude Code" instruction so users know why `/retrospect` isn't visible immediately
- **CLAUDE.md: skill documented** — `/retrospect` now listed in global CLAUDE.md so it's injected into every session context regardless of menu state
- **(Previous session)** Stop hook parse error — em dash in `friction_notes.Add()` caused PowerShell parser crash; replaced with hyphen
- **(Previous session)** PSModulePath missing user dir — run-tests.ps1 now injects Pester path when invoked from bash

## Pending / Tomorrow

- [ ] **Verify `/retrospect` appears in `/` menu** — requires fully quitting and reopening Claude Code (not just new terminal). If it still doesn't appear, type `/retrospect` directly; the CLAUDE.md injection means the model always knows about it
- [ ] **Telemetry on new machines** — friction data (`reports/`, `rolling-averages.json`, `cumulative.json`) is gitignored and machine-local; cross-machine sync is a roadmap item, not yet implemented

## Roadmap (nice to have)

- **Skills:** `/friction` (live score on demand), `/report` (last session summary), `/session` (event timeline)
- **Hooks:** `Notification` (sound when needs input), `PreCompact` (preserve prompt), `PreToolUse` (richer telemetry + input rewriting)
- **Scale:** Cross-machine telemetry sync via remote store, team mode

---

*Last updated: 2026-03-30*
