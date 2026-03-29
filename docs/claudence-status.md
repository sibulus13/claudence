# Claudence — Status TLDR

> Hooks-driven friction tracking and telemetry for Claude Code on Windows.
> Repo: `C:\Users\Michael\.claude` (git, not yet pushed to GitHub)

---

## What's Working

| Feature | Status |
|---------|--------|
| Live status bar | ✅ After every response — Prompts, Overrides, Additions, Blocked, ctx%, cost, elapsed |
| Sound on stop | ✅ Chimes (ring-half.wav). Louder ring if elapsed >30s, score ≥5, or retrospect threshold hit |
| Ding on permission request | ✅ ding-half.wav plays async on every PermissionRequest event |
| Prompt classification | ✅ 4 types: first_prompt, followup, override (+3), addition (+1) |
| Per-session friction report | ✅ JSON to `telemetry/reports/<id>.json` on every Stop |
| Rolling averages | ✅ Window=5 sessions, tracks o_rate / a_rate / b_rate |
| Trend indicators | ✅ `+`/`-` on Overrides and Blocked when rate drifts >10pp from average |
| Retrospection prompt | ✅ Fires when cumulative score ≥6 across ≥3 sessions → suggests `/retrospect` |
| `/retrospect` skill | ✅ Defined in `skills/retrospect.md`. Reviews reports, proposes allow rules + CLAUDE.md edits |
| Pester test suite | ✅ 57 tests across Test-IsOverride, Test-IsAddition, Get-PromptClassification |
| Pre-commit hook | ✅ Blocks commits touching `telemetry/` if tests fail |
| `setup.ps1` bootstrap | ✅ Creates dirs, generates WAV files at 80% volume, installs Pester 5, wires pre-commit hook |

## Hooks Wired

| Event | Script | Blocking |
|-------|--------|---------|
| UserPromptSubmit | log-prompt.ps1 | yes (sync — ensures status bar is current) |
| Stop | analyze-session.ps1 | yes (sync — plays sound, writes report) |
| PostToolUse | log-tool-done.ps1 | no |
| PostCompact | record-compact.ps1 | no |
| PermissionRequest | log-permission.ps1 + ding | no |

## Known Issues / Recently Fixed

- **Stop hook parse error** (fixed 2026-03-29) — em dash in friction_notes.Add() strings caused PowerShell parser error. Replaced with hyphen.
- **Status bar stale data** (fixed earlier) — `async: true` on UserPromptSubmit caused race condition. Removed; hook is now synchronous.
- **PSModulePath missing user dir** (fixed 2026-03-29) — run-tests.ps1 now adds `~\Documents\WindowsPowerShell\Modules` so Pester 5 is found when invoked from bash.

## Pending

- [ ] Push to GitHub (`claudence` repo — user must create at github.com/new, then `git remote add origin` + `git push`)
- [ ] `/retrospect` may need Claude Code restart to appear in the `/` menu (skill loaded at session start)

## Roadmap (nice to have)

- **Skills:** `/friction` (live score on demand), `/report` (last session summary), `/session` (event timeline)
- **Hooks:** `Notification` (sound when needs input), `PreCompact` (preserve prompt), `PreToolUse` (richer telemetry + input rewriting)
- **Scale:** Cross-machine telemetry sync, team mode

---

*Last updated: 2026-03-29*
