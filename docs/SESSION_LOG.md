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

---

## 2026-08-16 - Per-workspace docs roots

**Ask.** One designated doc set per workspace, so version-control lines stay segregated per project; when cwd is not a version-controlled workspace, either treat it as the workspace or walk up to the nearest parent that qualifies; and a key / mapping / environment variable to pin the answer.

**Shape of the problem, from the real layout.** `D:/repo` is not a repo, but most projects under it are - and `Life` is a repo whose *subfolders* (`Life/pylon`, `Life/karaoke`) are workspaces in their own right without their own VC. So nearest-`.git` answers most cases correctly and is genuinely ambiguous for exactly the nested-workspace case. That is the case the override mechanisms exist for, rather than being a general-purpose knob.

**Resolver** - `scripts/resolve-docs-root.ps1`, six rules, first hit wins:

| # | rule | when it is the right answer |
|---|---|---|
| 1 | `$CLAUDE_DOCS_ROOT` | one-off redirect for a single shell or session |
| 2 | `.claude-docs-root` marker, nearest ancestor | the pin should travel with the repo and be committed alongside it |
| 3 | `~/.claude/workspaces/doc-roots.json` pin, longest match | the pin is machine-local, or the repo must not carry a marker |
| 4 | nearest ancestor holding `.git` | the default - docs land on the project's own VC line |
| 5 | `<repo root>/<Category>/<project>` | a workspace under the repo-org convention with no VC of its own |
| 6 | `~/.claude/docs` | nothing matched; reported as source `fallback`, never as a confident answer |

An empty marker file means "the folder I sit in"; a marker holding one line names the root, absolute or relative to the marker. The repo root for rule 5 is read from `CLAUDE_REPO_ROOT` or `terminal.local.lua`, the same sources `terminal.lua` uses - never hardcoded, so the machine stays relocatable.

**Two flags the record carries beyond the path.** `tracked` is false when the resolved root is not under version control at all; `shared` is true when the root sits inside a *parent* repo, which is legal but means the log would land in a history shared with sibling projects. The SessionStart hook turns both into an explicit instruction to confirm with the user rather than write blind - the resolver surfaces ambiguity instead of guessing past it.

**Wiring.** A third SessionStart hook (`resolve-docs-root.ps1 -Hook`) states the resolved root at session open. CLAUDE.md's Terse-Output Contract now describes the resolution instead of naming claudence's docs directly, and its stale "each repo names its own docs in its project CLAUDE.md" clause was retired.

**Verification.** 23 Pester cases in `tests/docs-root.tests.ps1`, registered in `tests/run-tests.ps1`. Every case builds a throwaway tree under `$TestDrive`; a directory named `.git` is enough to look like a repo, so no test shells out to git or touches a real project. Three env seams (`CLAUDE_DOCS_ROOT`, `CLAUDE_REPO_ROOT`, `CLAUDE_DOC_ROOTS_FILE`) are reset per test and restored afterwards, so the live registry is never read or written by the suite.

**Caveats hit.**
- The script parsed as ANSI and died on its own em dashes: Windows PowerShell 5.1 treats a BOM-less `.ps1` as ANSI, and the mojibake landed inside string literals. Resolved by keeping the file pure ASCII (noted at the top of it), which matches the BOM-less convention of the other scripts here.
- Pester 5 rejects a `BeforeEach` at the container root, and expands `<...>` inside an `It` name as a data placeholder - a test called "falls back to `<repo root>/<Category>/<project>`" failed to parse. Resolved by scoping the setup per `Describe` and renaming the test.
- The `-Hook` tests initially read nothing: `[Console]::In.ReadToEnd()` reads *process* stdin, which a PowerShell-pipeline pipe never reaches. Resolved by driving the script as a child process (`$payload | powershell.exe -File ... -Hook`), which is also how the real hook runs it.

**Left open.** `doc-roots.json` ships empty - no workspace is pinned yet. `Life/pylon` and `Life/karaoke` currently resolve to the `Life` repo (flagged `shared`); whether either should keep its own log is the user's call.



## 2026-08-17 — Alt+O launcher coverage: which repos are actually openable

**The two questions.** (1) Why did some WezTerm windows show runtime errors? (2) Is every git repo reachable as a workspace, and specifically why is Crucible not?

**Runtime errors — three distinct causes, none of them the live config.**

| what the log showed | where it came from | live? |
|---|---|---|
| `mux::ssh_agent ... failed to create symlink (os error 1314)` in EVERY instance | WezTerm forwards `SSH_AUTH_SOCK` by symlinking it per-GUI-process; unprivileged Windows accounts cannot create symlinks without Developer Mode. Purely cosmetic unless SSH agent forwarding is used. | yes, harmless |
| `syntax error: [string "C:/Users/Michael/AppData/Local/Temp/claude/D-..."]` (pids 4416, 25756) | The isolated-repro WezTerm instances spawned during the 2026-08-16 cwd-bug hunt, launched against `scratchpad/repro*.lua`. Those scratch files have deliberate/incomplete Lua. | no — all exited |
| `terminal.lua:537: invalid escape sequence near ''[:/\ '` (pid 28944, 21:30) | The live config mid-edit, between introducing `transcript_exists` and fixing its character class. Fixed at 21:32; the surviving instance logged nothing after. | no |

Only pid 28944 is still running, and `wezterm show-keys --config-file ~/.wezterm.lua` parses the current config with zero errors. One older instance (pid 40692, since 2026-07-23) had logged `RenameWorkspace is not a valid KeyAssignment variant` on 2026-08-13 — that build predates the `RenameWorkspace` action; the current build (20260606-114717) accepts it, so the error dies with that window.

**Repo coverage — the gap was deliberate pruning plus one blind spot.**

Ground truth under `D:epo` at depth 8 with only structural prunes: **68 git repos**. `discover_repos()` returned **38**. The 30-repo delta is exactly the four name-based prunes, and PowerShell hashtable keys are case-INsensitive, so `'_Misc'` also prunes `web/_misc`:

| pruned segment | repos hidden | verdict |
|---|---|---|
| `_Misc` | 14 (`_Misc/*`) + 5 (`web/_misc/*`) | mostly correct — but it also hid `_Misc/Music/spotifyDL`, an active project |
| `archive` | 9 (`Stock/archive/*`) | correct |
| `example`/`examples` | 2 (`Example/*`) | correct |

So nothing was *accidentally* dropped by the walk. The real blind spots were elsewhere:

1. **Crucible was discoverable but unsearchable.** `Stock/Research 2026` is a git repo and the walk finds it. `REPO_ALIASES` maps that path to the product name `Crucible`, but the alias was consumed **only** by `format-tab-title` — `sorted_choices` labelled each row with the raw `rel`. Typing "crucible" into the fuzzy launcher therefore matched nothing. Same for `Cortex` and `Tarive`.
2. **`Life/pylon` was a favorite pinned to a row that is never drawn.** `repos.json` has `favorites: ["Life/pylon"]`, but `Life/pylon` is not its own repo — it lives inside the `Life` monorepo. `discover_repos()` keys on a `.git` child, so it never returned that rel, and the star had nothing to attach to. Every other `Life` sub-project (vantage, second-brain/Cortex, karaoke, Resume workshop, Europe 2026, Traction Complete) was likewise reachable only by opening the whole `Life` repo. Alt+P can pin any tab title, but only discovered repos are ever listed — pin and list disagreed on what a project is.
3. **The test gate enumerated its own files.** `tests/run-tests.ps1` hardcoded four paths, so a fifth test file would have been silently skipped and the gate would still have printed a confident green.

**Fixes.**
- New `EXTRA_PROJECTS` table in `terminal.lua`: rel paths that are first-class tabs but that the walk cannot see (inside a parent repo, or behind a prune). Seeded with the seven `Life` sub-projects and `_Misc/Music/spotifyDL`.
- Existence-tested **inside the same PowerShell scan** rather than from Lua. A `cmd.exe` spawn per entry would have added ~8 process launches to every Alt+O — more than the ~150ms walk itself. `Test-Path -LiteralPath` is used because folder names containing `[` `]` are otherwise read as wildcard patterns (hit live: a `[[...sign-in]]` route folder crashed the plain `Test-Path` during analysis).
- `sorted_choices` now renders `Crucible  ·  Stock/Research 2026` whenever an alias exists, so both the product name and the path hit the fuzzy matcher.
- The Alt+O callback resolves the chosen repo from an **id→record map** instead of parsing the rendered label. Label-parsing was already fragile (it stripped a star prefix by pattern); with an alias prefix it would have been wrong outright, and a wrong `rel` poisons `recents`, `frequency`, and the per-tab `workspaces` recipe.
- `tests/run-tests.ps1` now globs `*.tests.ps1` and fails loudly on an empty match rather than reporting a vacuous pass.

**Verification.** `tests/launcher.tests.ps1`, 11 cases, parsing the Lua tables out of `terminal.lua` rather than duplicating them, so the tests track the config instead of a copy. They assert: every `EXTRA_PROJECTS` path still exists; every entry is one the walk genuinely misses (it caught a wrong first draft of this invariant — spotifyDL *is* a git repo, it is just pruned); every `REPO_ALIASES` key resolves to a listed row; and every pinned favorite is reachable. Gate: **126/126**, up from 115.

**Caveats hit.**
- The Bash heredoc collapsed `\` to `\` before Python saw it, so anchor strings for a scripted patch never matched the Lua source. Resolved by writing the patch script with the Write tool and finishing the backslash-bearing edits with the Edit tool.
- A first patch pass leaked a Python variable name into the Lua (`REPO_ALIASES[r.rel:gsub('" + BS + BS + "', ...)]`). It parsed as a valid Lua string, so it would not have crashed — aliases would simply have never resolved, silently reverting the fix. Caught by reading the generated code back; the `renders the product name` test now pins it.

**Left open.** `EXTRA_PROJECTS` is a curated list, not a rule — a new `Life` sub-project has to be added by hand (the test will not notice an *absent* project, only a dead one). Whether `web/_misc/*` and `_Misc/job apps/*` should stay hidden is unconfirmed; they are currently pruned.
