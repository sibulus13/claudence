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
# Usage: open-in-editor.sh <path>[:<line>[:<col>]] [pane-cwd]
set -uo pipefail

target="${1:-}"
pane_cwd="${2:-}"   # the clicking pane's directory, when terminal.lua could read it
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

# Resolve a path that does not exist as given. WezTerm hands the matched text over verbatim and
# this process has no useful cwd, so the known roots are the only frame of reference. THREE shapes
# arrive, and only the first of them used to be handled:
#
#   OBSERVABILITY.md              bare name          -> search the roots by name
#   docs/notes/harness/MAP.md     repo-relative      -> join onto each root
#   /notes/harness/MAP.md         TRUNCATED relative -> the hyperlink rule in terminal.lua is
#     unanchored and its leading "/" is optional-dot-prefixed, so a repo-relative path printed by
#     an agent matches from its FIRST SLASH: "docs/" is left outside the link and what arrives
#     here looks absolute and does not exist. Strip the slash, retry, then fall back to the name.
#
# The old guard was `[[ "$path" != */* ]]` -- anything carrying a directory skipped the search
# entirely and fell straight to the silent `exit 0` below, which is exactly what a click on a
# relative path did: nothing, with no error anywhere.
#
# First match in root order wins, so ordering IS the disambiguation. Depth is bounded and
# .git/node_modules pruned to keep this interactive.
resolve_in_roots() {
  local want="$1" rel root found match
  local -a roots
  IFS=':' read -r -a roots <<< "${CLAUDENCE_LINK_ROOTS:-$HOME/repo}"
  rel="${want#/}"

  # The pane's own directory first. A link is printed by something running THERE, so its checkout
  # is the right answer -- and it is the only signal that separates one repo's "docs/TODO.md" from
  # another's. Root order cannot do this: it would always pick the same repo whichever pane clicked.
  [ -n "$pane_cwd" ] && [ -e "$pane_cwd/$rel" ] && { printf '%s\n' "$pane_cwd/$rel"; return 0; }

  # Exact join first -- unambiguous, and costs a stat rather than a walk.
  for root in "${roots[@]}"; do
    [ -d "$root" ] || continue
    [ -e "$root/$rel" ] && { printf '%s\n' "$root/$rel"; return 0; }
  done

  # Then by filename. Collect every candidate across ALL roots FIRST, then choose -- a per-root
  # decision cannot see that a later root holds the exact directories we were handed, so a decoy
  # of the same name in an earlier root would win. Preferring the suffix match is the whole point
  # of the truncated-path case, so the choice has to be made over the full list.
  local all=""
  for root in "${roots[@]}"; do
    [ -d "$root" ] || continue
    all+="$(find "$root" -maxdepth 5 \
              \( -name .git -o -name node_modules -o -name vendor -o -name tmp \) -prune -o \
              -type f -name "${want##*/}" -print 2>/dev/null)"$'\n'
  done
  match=$(printf '%s' "$all" | grep -m1 -F "/$rel")          # same directories -> certain
  [ -n "$match" ] || match=$(printf '%s' "$all" | grep -m1 .) # else root order decides
  [ -n "$match" ] && { printf '%s\n' "$match"; return 0; }
  return 1
}

# One runnable check -- the three link shapes, against a throwaway tree that includes a decoy of
# the same filename in an EARLIER root. That decoy is the whole reason the candidate list is
# gathered before it is filtered.
if [ "$target" = "--selftest" ]; then
  tmp=$(mktemp -d)
  mkdir -p "$tmp/r1/elsewhere" "$tmp/r2/docs/notes/harness"
  : > "$tmp/r1/elsewhere/MAP.md"
  : > "$tmp/r2/docs/notes/harness/MAP.md"
  export CLAUDENCE_LINK_ROOTS="$tmp/r1:$tmp/r2"
  fail=0; ran=0
  check() {
    ran=$((ran + 1)); local got; got=$(resolve_in_roots "$1")
    if [ "$got" = "$2" ]; then printf '  ok    %-30s -> %s\n' "$1" "${got#$tmp/}"
    else printf '  FAIL  %-30s -> %s (wanted %s)\n' "$1" "${got:-<unresolved>}" "$2"; fail=1; fi
  }
  check "elsewhere/MAP.md"          "$tmp/r1/elsewhere/MAP.md"
  check "docs/notes/harness/MAP.md" "$tmp/r2/docs/notes/harness/MAP.md"
  check "/notes/harness/MAP.md"     "$tmp/r2/docs/notes/harness/MAP.md"
  check "MAP.md"                    "$tmp/r1/elsewhere/MAP.md"

  # The case root order alone gets WRONG: the same relative path in two checkouts. Without the
  # pane's directory the earlier root always wins, whichever pane was clicked in.
  mkdir -p "$tmp/r1/docs" "$tmp/r2/docs"
  : > "$tmp/r1/docs/TODO.md"
  : > "$tmp/r2/docs/TODO.md"
  check "docs/TODO.md"              "$tmp/r1/docs/TODO.md"
  pane_cwd="$tmp/r2"
  check "docs/TODO.md"              "$tmp/r2/docs/TODO.md"
  check "/docs/TODO.md"             "$tmp/r2/docs/TODO.md"
  pane_cwd=""
  rm -rf "$tmp"
  [ "$fail" = 0 ] && echo "open-in-editor: $ran link shapes resolve" || echo "SELFTEST FAILED"
  exit "$fail"
fi

if [ ! -e "$path" ]; then
  resolved=$(resolve_in_roots "$path") && path="$resolved"
fi

[ -e "$path" ] || exit 0

# Absolutise before handing over. A relative path that happens to exist against THIS process's cwd
# resolves against the EDITOR's cwd once passed on, which is a different directory and usually the
# wrong file. Every shape above must arrive at the editor as one unambiguous path.
case "$path" in
  /*) ;;
  *) path="$(cd -- "$(dirname -- "$path")" && pwd)/$(basename -- "$path")" ;;
esac

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

# PATH is the WRONG PLACE to look for these, and the loop above is why a resolved file still did
# not open in an editor. `code` reaches PATH only if the user ran VS Code's "Shell Command:
# Install 'code' command in PATH", and this process is spawned by the WezTerm GUI app, which
# inherits launchd's environment rather than a login shell's -- so even an installed shim in
# /usr/local/bin may be absent here. The CLI inside the app bundle is what that shim points at,
# so look there directly before conceding to LaunchServices.
for bundle in \
  "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" \
  "$HOME/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" \
  "/Applications/Cursor.app/Contents/Resources/app/bin/cursor" \
  "/Applications/Windsurf.app/Contents/Resources/app/bin/windsurf" ; do
  [ -x "$bundle" ] && exec "$bundle" -r -g "$position" >/dev/null 2>&1
done

# Sublime Text takes the position directly, with no -g.
if command -v subl >/dev/null 2>&1; then
  exec subl "$position" >/dev/null 2>&1
fi

# Nothing installed — hand the file to whatever LaunchServices registered for it.
# Line and column are lost on this path; `open` cannot carry a position.
exec /usr/bin/open "$path" >/dev/null 2>&1
