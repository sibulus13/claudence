# Decisions — claudence (`~/.claude`)

ADR-lite journal for this repo. One row per decision.

**status** — `assumed` (a default chosen to keep moving; safe to change) · `confirmed` (owner-ratified) · `superseded` (with pointer).
**revisit-when** — the trigger that should re-open it.

| id | date | decision | status | rationale | revisit-when |
|----|------|----------|--------|-----------|--------------|
| D1 | 2026-08-16 | Restored WezTerm panes are placed by an explicit `Set-Location`, not by WezTerm's spawn-time `cwd` field | confirmed | `MuxWindow:spawn_tab{cwd=...}` is ignored on the `gui-startup` path (verified in an isolated instance); `MuxPane:split` honours it. Relying on the field made left-pane placement silently wrong. | A WezTerm release fixes `spawn_tab` cwd — then the `Set-Location` becomes belt-and-braces, not load-bearing |
| D2 | 2026-08-16 | A `claude --resume <id>` recipe is validated at **both** save and restore | confirmed | The pane→session binding can be stale (pane ids recycle every relaunch) *and* the transcript can be reaped between save and restore. Validating only at save left the on-disk recipes poisoned. | Claude exposes a first-class "does this session exist" query — replace the filesystem probe with it |
| D3 | 2026-08-16 | Keep the `explanatory-output-style` plugin enabled; resolve its conflict with the Terse-Output Contract by precedence, not removal | assumed | The two collide on length only, not on substance. Precedence keeps the educational depth while moving it out of the terminal into this repo's docs. | Terminal responses stay long despite the precedence rule — then disable the plugin in `settings.json` → `enabledPlugins` |
