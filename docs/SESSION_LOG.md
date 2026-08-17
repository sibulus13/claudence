# Session Log — claudence (`~/.claude`)

Append-only. Verbose detail that the Terse-Output Contract keeps out of the terminal:
run narratives, console-output explanations, caveat back-length, mechanism write-ups.
Newest entries at the bottom.

---

## 2026-08-16 — Restored tabs opened in the repo root

**Symptom as reported:** after a WezTerm restart the tab titles restored correctly, but the panes were not in the tab's folder, so the previous session's last command failed.

**Three independent defects, stacking into one symptom.**

*1. `spawn_tab` ignores `cwd` at `gui-startup`.* A three-arm experiment in a throwaway WezTerm instance (own config, own mux, killed afterward) probed `[System.Environment]::CurrentDirectory` — the process working directory, which `Set-Location` does not touch — in three panes spawned three ways:

| spawn form | resulting process cwd |
|---|---|
| `MuxWindow:spawn_tab{cwd=T, args=…}` | `D:\repo` ← **ignored** |
| `MuxPane:split{cwd=T, args=…}`, parent spawned without args | `D:\repo\Stock\Research 2026` |
| `MuxPane:split{cwd=T, args=…}`, parent spawned with args | `D:\repo\Stock\Research 2026` |

So the left pane of every restored tab inherited the mux window's cwd (the repo root). Panes carrying a saved command masked this, because `pane_launch_args` prefixed a `Set-Location`; panes without one had nothing placing them at all. That is the case the user hit: `↑`-recall of the previous session's command ran in `D:\repo`.

*2. The argv reconstruction emitted PowerShell that cannot parse.* `pane_resume_cmd` rebuilt a running Next.js server from argv as `'C:\Program Files\nodejs\node.exe' '…\start-server.js'`. In PowerShell a statement beginning with a quoted string is an *expression*, not an invocation, and a second string token after it is a parse error. PowerShell parses the entire `-Command` block up front, so the error also killed the `Set-Location` sitting in front of it in the same block — the pane dropped to a prompt in the spawn cwd. This is why the two defects were hard to separate: #2 made #1 visible on a pane that should have been immune to it.

*3. Pane→session bindings were cross-wired.* `workspaces/pane-sessions/pane-<id>.json` is keyed purely on the WezTerm pane id, and WezTerm restarts pane ids at 0 on every relaunch. `record-pane-session.ps1` only reaps files after 7 days — an eternity next to a restart — so `pane-1.json` still held a session whose recorded cwd was `C:\Users\Michael\AppData\Local\Temp`, and the `Stock/Research 2026` tab inherited it. Claude scopes conversations per project dir, so restore died with `No conversation found with session ID: ff843908-…`.

A fourth finding fell out of #3: all three stored `--resume` ids (`Stock/Research 2026`, `web/cashcow`, `web/sunset`) pointed at transcripts that no longer existed anywhere under `~/.claude/projects/`. Claude reaps transcripts on its own schedule, so a recipe saved hours earlier can be dead by restore time even when the binding is correct. That is why validation runs at restore as well as at save.

**Fix** — `terminal.lua`, commit `36cd134`:
- every restored pane launches through PowerShell with a leading `Set-Location`, command or not; a command-less pane gets the `PSREADLINE_INIT` that an arg-less `default_prog` spawn would have given it, so cross-session `↑` history is unchanged
- `pane_resume_cmd` emits the call operator `&` and quotes *every* argv token (an unquoted token is still parsed, so a stray `$`, `@`, `(` or backtick would expand or abort); `pane_launch_args` repairs recipes captured before this fix by prefixing `&` to any command starting with a quote
- `pane_session_id` takes the tab's repo dir and rejects a binding whose recorded cwd differs; `transcript_exists` then confirms the conversation is still on disk. Both checks degrade to `claude --continue` — exactly what the code did before per-pane binding existed, so a false negative costs only the exact resume

**Verification.** Patched launch path re-tested in an isolated instance: the command-less pane and a legacy quoted-path recipe both land in `D:\repo\Stock\Research 2026`. `transcript_exists` exercised at Lua runtime via `wezterm --config-file … show-keys` (loads config in-process, no GUI) against the real transcript store — 4/4, including the space-and-case path `d:/repo/Stock/Research 2026` → `D--repo-Stock-Research-2026`. Repo gate 92/92. All throwaway instances killed; none left running.

**Caveats hit.**
- A first ad-hoc probe suggested `split` also ignored `cwd`, contradicting an earlier run. Resolved by building the purpose-made three-arm experiment above, which isolated the variable; the earlier reading was the unreliable one, and the shipped fix does not depend on the answer either way.
- This shell collapses `\\` to `\` inside quoted heredocs, which silently produced an invalid Lua escape (`'[:/\ ]'`) that WezTerm rejected while falling back to the default config — so the config *appeared* to load. Resolved by constructing backslashes via `chr(92)` in Python and using the Write tool for test configs.
- `wezterm --config-file` is a global flag and must precede the subcommand; `wezterm start --config-file …` errors.

**Left open.** `save_session` still captures only the first split, so a 3+-pane tab loses panes on restore (it logs, never restores). `transcript_exists` / `quote_arg` are file-local in `terminal.lua` and therefore outside the Pester gate; covering them means extracting into `attention.lua`.

---

## 2026-08-16 — Why the Terse-Output Contract was not taking effect

Not disabled — the contract text sits in `CLAUDE.md` lines 100–109 and was loaded in session context. Two causes.

*1. A competing instruction outranked it.* The `explanatory-output-style` plugin (enabled in `settings.json` → `enabledPlugins`) installs a SessionStart hook at `plugins/cache/claude-plugins-official/explanatory-output-style/1.0.0/hooks-handlers/session-start.sh` whose injected context says verbatim "you may exceed typical length constraints" and mandates `★ Insight` blocks. That arrives as fresh session context each session and contradicts "terminal bullets are terse" head-on.

*2. The contract had no landing zone.* It routes anything longer than one sentence to a repo doc and says each repo names its own docs in its CLAUDE.md. `~/.claude` had only `docs/claudence-status.md` — no session log, no decision log, and CLAUDE.md named neither. With nowhere to send detail, the terminal was the only channel available, so the contract could not be satisfied here even in principle.

**Fix.** Added a *Precedence over output styles* bullet to the contract (educational depth is kept but written here and cited in one line — terseness governs the channel, not the depth), named this repo's two docs in the same section, and created `docs/DECISIONS.md` + this file. Plugin left enabled — see D3.
