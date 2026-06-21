#!/usr/bin/env bash
# open-workspace.sh — Open (or focus) a named WezTerm workspace.
# Usage: open-workspace.sh <workspace-name> <project-path> [idea-filename] [right-cmd]
#
# Cross-platform (macOS / Linux / WSL).
# Requires: wezterm CLI in PATH, python3 for registry updates.
set -euo pipefail

WORKSPACE_NAME="${1:?usage: open-workspace.sh <name> <path> [idea] [right-cmd]}"
PROJECT_PATH="${2:?usage: open-workspace.sh <name> <path> [idea] [right-cmd]}"
IDEA_FILENAME="${3:-}"
RIGHT_CMD="${4:-}"

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
else:
    ws.append({
        'name':         '$WORKSPACE_NAME',
        'projectPath':  '$PROJECT_PATH',
        'ideaFilename': '$IDEA_FILENAME',
        'lastUsed':     '$NOW',
        'useCount':     1,
    })

ws.sort(key=lambda x: x.get('lastUsed', ''), reverse=True)
reg['workspaces'] = ws[:20]
with open(registry_path, 'w') as f:
    json.dump(reg, f, indent=2)

active = {'workspace': '$WORKSPACE_NAME', 'cwd': '$PROJECT_PATH', 'updatedAt': '$NOW'}
with open('$ACTIVE', 'w') as f:
    json.dump(active, f)
PYEOF
