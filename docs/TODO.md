---
purpose: The single queue for claudence — what is in flight, what is next, and what is deliberately deferred, so a fresh session picks up without re-deriving it
update-trigger: Work starts, finishes, or is deferred; a blocker clears or appears; a session ends
last-verified: 2026-08-10
status: current
---

# TODO

**Three sections, and the distinction is the point.** `Now` is in flight or blocked-on-a-person.
`Next` is agreed and unblocked. `Backlog` is deliberately deferred — recorded so it is not
rediscovered, not so it is done. **The `## Now` heading is read by the SessionStart hook and
injected into a fresh agent's context**, so keep it short and true.

Tags: ⏳ in flight · 🅿️ staged, not deployed · ⛔ blocked on a person · 🔬 needs a measurement

## Now

- ⛔ **The repo cannot be pushed.** The credential-helper account does not match the remote's owner,
  so pushes 403, and `macos` has no upstream — 15 commits exist on one disk with no verified backup.
  Run `scripts/doctor.py` for the two accounts and both fixes. Nothing here is durable until it
  clears.
- 🅿️ **`CLAUDE.md` describes a skill that does not exist** — it claims `/orchestrate` defines six
  role flows (feature / bugfix / arch-decision / security-review / go-to-market / hotfix) and
  assembles per-role packages. The skill has none. Either build the flows or correct the claim.
- 🅿️ **`/brief` reads `context.md`** (`skills/brief/SKILL.md:24,36,42`) — the legacy alias the state
  contract retired. Every role package it assembles points at a filename that no longer applies.
- 🅿️ **`docs/DECISIONS.md` and `docs/JOURNAL.md` do not exist.** Decisions are scattered across
  `AGENT-LOOP.md`, `MACOS-PORT.md` and commit messages. The project defining the contract should
  not be the one exempt from it — [`STATE.md`](STATE.md) §7.

## Next

- Adopt the contract in the remaining repos: copy `templates/STATE.md` to `docs/STATE.md` wherever
  discovery returns nothing. `ariadne` is done; `claudence` is done as of 2026-08-10.
- 🔬 **Confirm the §4b density thresholds actually fire.** `CLAUDE.md` is 42 KB and past the 500-line
  guidance; the counter-pressure is designed but its firing is unmeasured. A rule that never
  triggers is decoration.
- Fix the pinned `env.PATH` — it lists `/usr/local/bin`, which does not exist on this machine.
  Harmless today, but it is the exact class of drift whose only symptom is a hook not firing.
- Reconcile the two machine-only plugins (`datadog`, `ponytail`) into the repo's canonical settings,
  or record deliberately that they are local-only. Right now a second machine silently lacks both.

## Backlog

Deferred deliberately. Each records why, so it is not re-litigated.

- **A rendered artifact view of `STATE.md`** — markdown already satisfies "align the user against
  current scope", renders diagrams on GitHub, and costs nothing to keep current. An artifact is a
  second copy that drifts. Revisit when a state doc needs to be read by someone without repo access.
- **Cross-machine telemetry sync** — friction data is gitignored and machine-local by design.
  Blocked upstream by the push blocker anyway; revisit once there is a second machine.
- **A markdown renderer in the workspace right pane** — `less` is native and adequate. Revisit if
  `glow` or `bat` lands in PATH for another reason; the launcher already notes the upgrade path.
- **Auto-generating `## Now` from telemetry** — tempting and wrong. The value of `Now` is that a
  human asserted it; a generated one would be trusted without being true.
- **`statusline.py` emits a variable, unbounded line count (1 line typically, up to ~10 with
  theme history + helm breadcrumbs both populated) instead of a fixed small height.** Found
  2026-08-31: a background Workflow's live progress display rendered below the visible terminal
  frame, and this session's own statusline was measured emitting 4 real lines at the time (metrics
  row + 3 theme-history rows). Claude Code's terminal chrome likely reserves space for the status
  line based on an assumed height; a script that quietly grows past 1 line eats into space other
  UI (workflow progress, possibly Remote Control's own reserved row when RC is disabled) assumed
  was free. Owner's workaround for now: make the terminal window bigger rather than fix the
  script. Real fix, deferred: cap `THEME_ROWS`/helm-row output to a small fixed count (1-2 lines
  total, never variable), removing the height-budget mismatch at the source rather than relying on
  window size. Revisit when this recurs or before the next terminal-chrome-sensitive feature ships.
