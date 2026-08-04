#!/usr/bin/env bash
# open-in-editor.sh — open a file clicked in WezTerm (via terminal.lua's open-uri
# handler) in a GUI editor, at its line where the editor supports it.
#
# Port of open-in-vscode.ps1. Two things the Windows version did are dropped
# deliberately:
#   * the VS Code .cmd shim path — resolved from PATH instead
#   * the SendKeys chord that flipped markdown into preview mode — that was
#     Windows-only UI automation (System.Windows.Forms), with no equivalent here
#     that does not require granting Accessibility permissions
#
# $VISUAL / $EDITOR are deliberately NOT consulted: they usually name a TERMINAL
# editor (vim, nano), which cannot run here — this is spawned detached with no
# tty — and their flags differ from the ones below (`vim -r` means recovery mode,
# not "reuse window"). Set $CLAUDENCE_EDITOR to override; it must accept a single
# `path:line:col` argument.
#
# Usage: open-in-editor.sh <path>[:<line>[:<col>]]
set -uo pipefail

target="${1:-}"
[ -n "$target" ] || exit 0

# Split a trailing :line[:col] off the path so the file can be checked for
# existence and the position handed to the editor separately.
path="$target"
line=""
col=""
if [[ "$target" =~ ^(.*):([0-9]+):([0-9]+)$ ]]; then
  path="${BASH_REMATCH[1]}"; line="${BASH_REMATCH[2]}"; col="${BASH_REMATCH[3]}"
elif [[ "$target" =~ ^(.*):([0-9]+)$ ]]; then
  path="${BASH_REMATCH[1]}"; line="${BASH_REMATCH[2]}"
fi

[ -e "$path" ] || exit 0

position="$path"
[ -n "$line" ] && position="$path:$line"
[ -n "$col" ] && position="$path:$line:$col"

if [ -n "${CLAUDENCE_EDITOR:-}" ] && command -v "${CLAUDENCE_EDITOR}" >/dev/null 2>&1; then
  exec "$CLAUDENCE_EDITOR" "$position" >/dev/null 2>&1
fi

# VS Code family: -r reuses the existing window, -g jumps to file:line:col.
for editor in code code-insiders cursor windsurf; do
  if command -v "$editor" >/dev/null 2>&1; then
    exec "$editor" -r -g "$position" >/dev/null 2>&1
  fi
done

# Sublime Text takes the position directly, with no -g.
if command -v subl >/dev/null 2>&1; then
  exec subl "$position" >/dev/null 2>&1
fi

# Nothing installed — hand the file to whatever LaunchServices registered for it.
# Line and column are lost on this path; `open` cannot carry a position.
exec /usr/bin/open "$path" >/dev/null 2>&1
