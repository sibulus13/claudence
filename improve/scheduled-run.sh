#!/bin/bash
# scheduled-run.sh — the unattended half of the self-improvement loop.
#
# Answers "can it run without someone typing the command": yes. A hook cannot
# invoke an agent, but launchd can invoke the headless CLI, and that is durable
# in a way CronCreate is not (session-only, expires after 7 days).
#
# Two properties this deliberately has:
#
#   Read-only.   The agent is given Read/Glob/Grep and nothing else. It cannot
#                edit a governance file even if it decides it should. *This*
#                script does the writing, appending the agent's proposals to
#                LEDGER.md. That is AGENT-LOOP.md's build-order step 3 —
#                shadow mode first, record what would change.
#
#   Gated on evidence, not the clock. It exits without spending anything unless
#                audit.py says the loop is due AND new sessions have accumulated
#                since the last run. Running four times a day over the same
#                telemetry re-processes identical rows and biases toward acting
#                on noise; it does not reduce staleness.
#
# launchd does not source a profile, so every path here is absolute.

set -uo pipefail

CLAUDE="$HOME/.local/bin/claude"
PY=/opt/homebrew/bin/python3
[ -x "$PY" ] || PY=/usr/bin/python3
IMPROVE="$HOME/repo/claudence/improve"
STATE="$IMPROVE/state.json"
LEDGER="$IMPROVE/LEDGER.md"
HISTORY="$IMPROVE/history.jsonl"
REPORTS="$HOME/.claude/telemetry/reports"
STAMP=$(date "+%Y-%m-%d %H:%M")

log() { echo "[$STAMP] $*"; }

[ -x "$CLAUDE" ] || { log "claude CLI not found at $CLAUDE — nothing to do"; exit 0; }
[ -f "$STATE" ]  || { log "no state.json — audit.py has not run yet"; exit 0; }

# --- gate: due, and is there actually new material? -------------------------
GATE=$("$PY" - "$STATE" "$HISTORY" "$REPORTS" <<'PYEOF'
import json, os, sys
state_p, hist_p, reports_d = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    st = json.load(open(state_p))
except Exception:
    print("skip no-state"); raise SystemExit
cfg_p = os.path.join(os.path.dirname(state_p), 'config.json')
try:
    cfg = json.load(open(cfg_p))
except Exception:
    cfg = {}
min_new = cfg.get('minNewSessionsSinceLastRun', 3)

last_ts = st.get('last_run')
n_reports = 0
if os.path.isdir(reports_d):
    for f in os.listdir(reports_d):
        if not f.endswith('.json'):
            continue
        p = os.path.join(reports_d, f)
        if last_ts is None:
            n_reports += 1
        else:
            try:
                from datetime import datetime, timezone
                lt = datetime.fromisoformat(last_ts.replace('Z', '+00:00')).timestamp()
                if os.path.getmtime(p) > lt:
                    n_reports += 1
            except Exception:
                n_reports += 1

flagged = sum((st.get('counts') or {}).get(k, 0) for k in ('refactor', 'duplication', 'stale'))
if not st.get('due') and not flagged:
    print("skip not-due"); raise SystemExit
if n_reports < min_new and flagged == 0:
    print("skip thin-evidence %d<%d" % (n_reports, min_new)); raise SystemExit
print("run %d %d" % (n_reports, flagged))
PYEOF
)

case "$GATE" in
  skip*) log "$GATE"; exit 0 ;;
esac
read -r _ NEW_SESSIONS FLAGGED <<< "$GATE"
log "running — $NEW_SESSIONS new session reports, $FLAGGED density findings"

# --- the bounded prompt ----------------------------------------------------
PROMPT="Run the /self-improve loop in SHADOW MODE.

You have read-only tools. Do not attempt to edit any file — report only.

1. Read ~/.claude/improve/state.json. It already measured context density,
   cross-file duplication, staleness and due-ness. Do not re-derive those.
2. Read the friction reports under ~/.claude/telemetry/reports/ and the memory
   index at ~/.claude/projects/*/memory/MEMORY.md.
3. Apply the threshold in ~/.claude/improve/config.json: a pattern needs at
   least thresholdOccurrences occurrences to be proposed.
4. Output ONLY a markdown list. One line per proposal:
   - **<target file>** — <the change, in one sentence> (seen Nx: <evidence>)
   Include refactor and deduplication proposals from state.json, not just
   additions. If nothing meets the threshold, output exactly: NOTHING TO PROPOSE.

Be terse. No preamble, no summary, no closing remarks."

OUT=$("$CLAUDE" -p "$PROMPT" \
        --allowedTools Read Glob Grep \
        --model claude-sonnet-5 \
        < /dev/null 2>&1) || { log "claude exited non-zero; output follows"; log "$OUT"; exit 1; }

# --- record ---------------------------------------------------------------
if [ -z "${OUT// }" ]; then
  log "empty output — recording nothing"
  exit 0
fi

{
  printf '\n## Proposals — %s (shadow)\n\n' "$STAMP"
  printf '%s new session reports · %s density findings · read-only run\n\n' "$NEW_SESSIONS" "$FLAGGED"
  printf '%s\n' "$OUT" | grep -v "^Warning: no stdin data received"
} >> "$LEDGER"

"$PY" - "$HISTORY" "$NEW_SESSIONS" "$FLAGGED" <<'PYEOF'
import json, sys
from datetime import datetime, timezone
hist, new, flagged = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
row = {
    "id": "run-%s" % datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
    "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "mode": "shadow",
    "trigger": "launchd",
    "sessionsAnalyzed": new,
    "densityFindings": flagged,
    "applied": [],
}
with open(hist, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(row) + "\n")
PYEOF

log "appended proposals to LEDGER.md and a row to history.jsonl"
