#!/usr/bin/env bash
# open-workspace.sh — Open (or focus) a named WezTerm workspace.
# Usage: open-workspace.sh <workspace-name> <project-path> [state-doc] [right-cmd]
#
# The right pane opens the project's live state document — docs/STATE.md by the
# workspace state contract, or an explicit path as the third argument. That doc
# is the one page answering where the project is, what it must do, and what is
# blocked; opening it with the workspace is the point of having it.
#
# Discovery mirrors scripts/workspace-state.py so the pane and the SessionStart
# hook can never disagree about which file is the state of the project.
#
# Cross-platform (macOS / Linux / WSL).
# Requires: wezterm CLI in PATH, python3 for registry updates.
set -euo pipefail

# `--state-doc <path>` resolves the state document and exits, so the discovery
# below is testable without a terminal — and callable from other launchers.
if [ "${1:-}" = '--state-doc' ]; then
  WORKSPACE_NAME='' PROJECT_PATH="${2:?usage: open-workspace.sh --state-doc <path>}" DRY_RUN=1
else
  WORKSPACE_NAME="${1:?usage: open-workspace.sh <name> <path> [state-doc] [right-cmd]}"
  PROJECT_PATH="${2:?usage: open-workspace.sh <name> <path> [state-doc] [right-cmd]}"
  DRY_RUN=0
fi
STATE_DOC="${3:-}"
RIGHT_CMD="${4:-}"

# ── Find the state document ──────────────────────────────────────────────────
# Same canonical name and aliases as workspace-state.py, same search order.
if [ -z "$STATE_DOC" ]; then
  for d in docs .; do
    for f in STATE.md context.md workflow_state.md KNOWLEDGE.md; do
      if [ -f "$PROJECT_PATH/$d/$f" ]; then
        STATE_DOC="$d/$f"
        break 2
      fi
    done
  done
fi

# The right pane shows the state doc when one exists, unless a command was given
# explicitly. `less` ships with macOS and every Linux — no renderer to install,
# and -R keeps any ANSI intact if a renderer is added later.
# ponytail: raw markdown in a pager; pipe through glow/bat if either lands in PATH.
if [ -z "$RIGHT_CMD" ] && [ -n "$STATE_DOC" ]; then
  RIGHT_CMD="${PAGER:-less} -R $STATE_DOC"
fi

if [ "$DRY_RUN" = 1 ]; then
  echo "${STATE_DOC:-none}"
  exit 0
fi

REGISTRY_DIR="$HOME/.claude/workspaces"
REGISTRY="$REGISTRY_DIR/registry.json"
ACTIVE="$REGISTRY_DIR/active.json"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

mkdir -p "$REGISTRY_DIR"

# ── Check if workspace already open ──────────────────────────────────────────
EXISTING_PANE=""
if wezterm cli list 2>/dev/null | awk 'NR>1 && $4=="'"$WORKSPACE_NAME"'"{print $3; exit}' | grep -q .; then
  EXISTING_PANE=$(wezterm cli list 2>/dev/null | awk 'NR>1 && $4=="'"$WORKSPACE_NAME"'"{print $3; exit}')
fi

if [ -n "$EXISTING_PANE" ]; then
  echo "Focusing existing workspace '$WORKSPACE_NAME' (pane $EXISTING_PANE)"
  wezterm cli activate-pane --pane-id "$EXISTING_PANE"
else
  echo "Creating workspace '$WORKSPACE_NAME' in $PROJECT_PATH"

  # Left pane: Claude Code
  LEFT_PANE=$(wezterm cli spawn \
    --workspace "$WORKSPACE_NAME" \
    --cwd "$PROJECT_PATH" \
    -- bash -c 'claude --continue; exec bash')
  sleep 0.6

  # Right pane: aux shell or custom command
  if [ -n "$RIGHT_CMD" ]; then
    # shellcheck disable=SC2086
    RIGHT_PANE=$(wezterm cli split-pane --pane-id "$LEFT_PANE" --right --cwd "$PROJECT_PATH" -- $RIGHT_CMD)
  else
    RIGHT_PANE=$(wezterm cli split-pane --pane-id "$LEFT_PANE" --right --cwd "$PROJECT_PATH" -- bash)
  fi

  wezterm cli set-tab-title --pane-id "$LEFT_PANE" --title "$WORKSPACE_NAME"
  wezterm cli activate-pane --pane-id "$LEFT_PANE"
  echo "Workspace '$WORKSPACE_NAME' ready — left=$LEFT_PANE right=$RIGHT_PANE"
  if [ -n "$STATE_DOC" ]; then
    echo "  state doc: $STATE_DOC"
  else
    echo "  no state doc found — copy templates/STATE.md to docs/STATE.md"
  fi
fi

# ── Update registry via python3 ───────────────────────────────────────────────
python3 - <<PYEOF
import json, os

registry_path = '$REGISTRY'
if os.path.exists(registry_path):
    with open(registry_path) as f:
        reg = json.load(f)
else:
    reg = {'workspaces': []}

ws = reg.setdefault('workspaces', [])
entry = next((w for w in ws if w['name'] == '$WORKSPACE_NAME'), None)
if entry:
    entry['lastUsed']   = '$NOW'
    entry['useCount']   = entry.get('useCount', 0) + 1
    entry['projectPath'] = '$PROJECT_PATH'
    entry['stateDoc']    = '$STATE_DOC'
else:
    ws.append({
        'name':        '$WORKSPACE_NAME',
        'projectPath': '$PROJECT_PATH',
        'stateDoc':    '$STATE_DOC',
        'lastUsed':    '$NOW',
        'useCount':    1,
    })

ws.sort(key=lambda x: x.get('lastUsed', ''), reverse=True)
reg['workspaces'] = ws[:20]
with open(registry_path, 'w') as f:
    json.dump(reg, f, indent=2)

active = {'workspace': '$WORKSPACE_NAME', 'cwd': '$PROJECT_PATH', 'updatedAt': '$NOW'}
with open('$ACTIVE', 'w') as f:
    json.dump(active, f)
PYEOF
