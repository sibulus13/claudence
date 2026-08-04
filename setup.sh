#!/usr/bin/env bash
# setup.sh — install the macOS port of these dotfiles into ~/.claude and point
# WezTerm at it. The counterpart of setup.ps1 on Windows.
#
#   ./setup.sh            install / re-install (idempotent)
#   ./setup.sh --dry-run  print what would happen, change nothing
#
# Unlike the Windows flow (which robocopies the repo into ~/.claude), this
# SYMLINKS the code into ~/.claude so the checkout stays the single copy you
# edit. Two files are copied rather than linked:
#   * settings.json — Claude Code rewrites it when settings change, and a
#     write-via-rename would silently replace the symlink with a regular file,
#     detaching it from the repo without any error.
#   * ~/.config/wezterm/wezterm.lua — a 1-line loader, so there is nothing to
#     keep in sync.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
WEZTERM_DIR="$HOME/.config/wezterm"
STAMP="$(date +%Y%m%d-%H%M%S)"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

# Code and content that lives in the repo and is symlinked into ~/.claude.
# telemetry/ and workspaces/ are included even though they accumulate runtime
# state: .gitignore already excludes every runtime path, so the checkout stays
# clean and the scripts stay editable in place.
LINKS=(
  CLAUDE.md
  terminal.lua
  attention.lua
  keymap.txt
  statusline.py
  startup-reminder.py
  telemetry
  scripts
  skills
  templates
  tests
  docs
  improve
  hooks
  workspaces
  setup.sh
)

# Runtime directories the hooks and terminal config expect to exist.
RUNTIME_DIRS=(
  "$REPO/telemetry/sessions"
  "$REPO/telemetry/reports"
  "$REPO/workspaces/attention"
  "$REPO/workspaces/pane-sessions"
  "$CLAUDE_DIR/sounds"
)

say()  { printf '  %s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
run()  { if [ "$DRY_RUN" = 1 ]; then say "would: $*"; else "$@"; fi; }

require_macos() {
  [ "$(uname -s)" = "Darwin" ] || {
    echo "setup.sh is the macOS installer; on Windows use setup.ps1." >&2
    exit 1
  }
}

# Move an existing real file/dir aside once, keeping a timestamped copy. An
# existing symlink is just replaced — there is nothing of the user's in it.
backup_and_remove() {
  local target="$1"
  if [ -L "$target" ]; then
    run rm -f "$target"
  elif [ -e "$target" ]; then
    say "backup: $(basename "$target") -> $(basename "$target").bak-$STAMP"
    run mv "$target" "$target.bak-$STAMP"
  fi
}

require_macos

step "Directories"
for dir in "${RUNTIME_DIRS[@]}"; do
  [ -d "$dir" ] || say "create $dir"
  run mkdir -p "$dir"
done
run mkdir -p "$CLAUDE_DIR" "$WEZTERM_DIR"

step "Executable bits"
# The hooks are invoked as `python3 <script>` from settings.json, so this is for
# running them by hand; the .sh helpers genuinely need it.
for script in "$REPO"/telemetry/*.py "$REPO"/scripts/*.py "$REPO"/scripts/*.sh \
              "$REPO"/statusline.py "$REPO"/startup-reminder.py \
              "$REPO"/setup.sh "$REPO"/tests/*.sh "$REPO"/hooks/pre-commit; do
  [ -e "$script" ] && run chmod +x "$script"
done

step "Symlinks into $CLAUDE_DIR"
for name in "${LINKS[@]}"; do
  src="$REPO/$name"
  dst="$CLAUDE_DIR/$name"
  if [ ! -e "$src" ]; then
    say "skip $name (not in repo)"
    continue
  fi
  # Already correct — leave it alone so re-running is quiet.
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
    continue
  fi
  backup_and_remove "$dst"
  say "link $name"
  run ln -s "$src" "$dst"
done

step "settings.json"
if [ -f "$CLAUDE_DIR/settings.json" ] && \
   cmp -s "$REPO/settings.macos.json" "$CLAUDE_DIR/settings.json"; then
  say "already current"
else
  backup_and_remove "$CLAUDE_DIR/settings.json"
  say "copy settings.macos.json -> settings.json"
  run cp "$REPO/settings.macos.json" "$CLAUDE_DIR/settings.json"
fi

step "terminal.local.lua (machine-specific, gitignored)"
if [ -f "$REPO/terminal.local.lua" ]; then
  say "already present: $(sed -n 's/.*repo_root *= *//p' "$REPO/terminal.local.lua" | tr -d "',")"
else
  say "create with repo_root = $HOME/repo"
  if [ "$DRY_RUN" = 0 ]; then
    cat > "$REPO/terminal.local.lua" <<EOF
-- Machine-specific values for terminal.lua (gitignored).
-- repo_root is the folder the Alt+O launcher scans for git repos, and the
-- default cwd for the Nexus home tab.
return {
  repo_root = '$HOME/repo',
}
EOF
  fi
fi
if [ ! -L "$CLAUDE_DIR/terminal.local.lua" ]; then
  backup_and_remove "$CLAUDE_DIR/terminal.local.lua"
  run ln -s "$REPO/terminal.local.lua" "$CLAUDE_DIR/terminal.local.lua"
fi

step "WezTerm config"
if [ -f "$WEZTERM_DIR/wezterm.lua" ] && \
   cmp -s "$REPO/wezterm.loader.lua" "$WEZTERM_DIR/wezterm.lua"; then
  say "already current"
else
  backup_and_remove "$WEZTERM_DIR/wezterm.lua"
  say "install loader -> $WEZTERM_DIR/wezterm.lua"
  run cp "$REPO/wezterm.loader.lua" "$WEZTERM_DIR/wezterm.lua"
fi

step "Pre-commit hook"
if [ -d "$REPO/.git" ]; then
  run cp "$REPO/hooks/pre-commit" "$REPO/.git/hooks/pre-commit"
  run chmod +x "$REPO/.git/hooks/pre-commit"
  say "installed"
else
  say "skipped (no .git)"
fi

step "Verify"
if [ "$DRY_RUN" = 0 ]; then
  if "$REPO/tests/run-tests.sh" >/dev/null 2>&1; then
    say "tests pass"
  else
    say "TESTS FAILED — run tests/run-tests.sh to see why"
  fi
  if wezterm --config-file "$WEZTERM_DIR/wezterm.lua" show-keys >/dev/null 2>&1; then
    say "wezterm config loads"
  else
    say "WEZTERM CONFIG FAILED TO LOAD — run: wezterm --config-file $WEZTERM_DIR/wezterm.lua show-keys"
  fi
fi

cat <<'EOF'

Setup complete.

Next steps:
  1. Fully quit and reopen Claude Code (not just a new terminal) so the hooks load
  2. Run /hooks in Claude Code to confirm they registered
  3. Restart WezTerm — the Nexus home tab and the Alt+/ keymap appear on launch

Run tests anytime:  ~/.claude/tests/run-tests.sh
EOF
