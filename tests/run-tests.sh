#!/usr/bin/env bash
# run-tests.sh — the macOS test runner (counterpart of run-tests.ps1 + run-attention-tests.ps1).
#
#   tests/run-tests.sh          run everything
#   tests/run-tests.sh --quiet  only print the summary
#
# Exit 0 = everything passed. Three suites:
#   1. classification.test.py  pure prompt-classification logic
#   2. hooks.test.py           every hook run as a subprocess against a temp HOME
#   3. hyperlinks.test.py      what a clicked file path resolves to — the terminal.lua
#                              rules and open-in-editor.sh, checked as one chain
#   4. attention.test.lua      the tab-attention decision logic, run in WezTerm's
#                              own bundled Lua (there is no `lua` binary here)
# Plus a load check of the installed WezTerm config, skipped when the config has
# not been installed yet.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-/usr/bin/python3}"
QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

FAILED=0
declare -a SUMMARY

note() { [ "$QUIET" = 1 ] || printf '%s\n' "$*"; }

record() {
  local label="$1" ok="$2" detail="${3:-}"
  if [ "$ok" = 0 ]; then
    SUMMARY+=("  ok    $label${detail:+  ($detail)}")
  else
    SUMMARY+=("  FAIL  $label${detail:+  ($detail)}")
    FAILED=1
  fi
}

run_python_suite() {
  local label="$1" script="$2" out
  note "== $label"
  out="$("$PY" "$REPO/$script" 2>&1)"
  local code=$?
  note "$out"
  record "$label" "$code" "$(printf '%s' "$out" | grep -Eo '[0-9]+ passed, [0-9]+ failed' | tail -1)"
}

run_python_suite 'classification (unit)' 'tests/classification.test.py'
run_python_suite 'hooks (integration)' 'tests/hooks.test.py'
run_python_suite 'hyperlinks (config+resolver)' 'tests/hyperlinks.test.py'

# ── linkrules.lua, via WezTerm's bundled Lua ─────────────────────────────────
# The click-routing predicate. Lua patterns are NOT regex and emulating them from python is how
# a check passes while the runtime fails, so this runs in the same interpreter the config does.
note '== link routing (lua, via wezterm)'
LINK_OUT="$REPO/tests/.last-link-results.txt"
if ! command -v wezterm >/dev/null 2>&1; then
  record 'link routing (lua)' 1 'wezterm not on PATH'
else
  rm -f "$LINK_OUT"
  wezterm --config-file "$REPO/tests/linkrules.test.lua" show-keys >/dev/null 2>&1
  if [ ! -f "$LINK_OUT" ]; then
    record 'link routing (lua)' 1 'no results written — the test file failed to load'
  else
    note "$(tail -1 "$LINK_OUT")"
    [ "$QUIET" = 1 ] || grep '^FAIL' "$LINK_OUT" || true
    if grep -q '^FAIL' "$LINK_OUT"; then
      record 'link routing (lua)' 1 "$(tail -1 "$LINK_OUT")"
    else
      record 'link routing (lua)' 0 "$(tail -1 "$LINK_OUT")"
    fi
  fi
fi

# ── attention.lua, via WezTerm's bundled Lua ─────────────────────────────────
note '== attention (lua, via wezterm)'
LUA_OUT="$REPO/tests/.last-results.txt"
if ! command -v wezterm >/dev/null 2>&1; then
  record 'attention (lua)' 1 'wezterm not on PATH'
else
  rm -f "$LUA_OUT"
  # show-keys is just a cheap subcommand that forces the config to load; the test
  # file writes its results to disk because WezTerm owns stdout here.
  wezterm --config-file "$REPO/tests/attention.test.lua" show-keys >/dev/null 2>&1
  if [ ! -f "$LUA_OUT" ]; then
    record 'attention (lua)' 1 'no results written — the test file failed to load'
  else
    note "$(tail -1 "$LUA_OUT")"
    [ "$QUIET" = 1 ] || grep '^FAIL' "$LUA_OUT" || true
    if grep -q '^FAIL' "$LUA_OUT"; then
      record 'attention (lua)' 1 "$(tail -1 "$LUA_OUT" | tr -d '-' | xargs)"
    else
      record 'attention (lua)' 0 "$(tail -1 "$LUA_OUT" | tr -d '-' | xargs)"
    fi
  fi
fi

# ── terminal.lua load check ──────────────────────────────────────────────────
# terminal.lua resolves attention.lua from ~/.claude, so this only means anything
# once setup.sh has run. A missing install is reported as a skip, not a failure.
note '== terminal.lua (load check)'

# Every module terminal.lua dofiles from ~/.claude MUST be installed there, or the live config
# dies on reload with a runtime error in a popup — which is exactly what adding linkrules.lua to
# the checkout and not to ~/.claude did on 2026-08-20. The dependency is read out of the file
# rather than from setup.sh's link list, so the two cannot drift apart. Optional modules loaded
# through pcall are skipped: absent is a legitimate state for those.
MISSING=""
while read -r mod; do
  [ -e "$HOME/.claude/$mod" ] || MISSING="$MISSING $mod"
done <<EOF
$(grep "dofile(wezterm.home_dir" "$REPO/terminal.lua" | grep -v pcall \
    | sed -E "s|.*/\.claude/([A-Za-z0-9_.-]+\.lua).*|\1|")
EOF
if [ -n "$MISSING" ]; then
  record 'terminal.lua modules installed' 1 "not in ~/.claude:$MISSING — run ./setup.sh"
else
  record 'terminal.lua modules installed' 0
fi

if [ ! -e "$HOME/.claude/attention.lua" ]; then
  SUMMARY+=('  skip  terminal.lua load check  (not installed yet — run ./setup.sh)')
  note '  skipped: ~/.claude/attention.lua missing'
else
  # Neither the exit code NOR stderr can report this: WezTerm falls back to its default config
  # and exits 0, and show-keys prints nothing about the failure. So the config is loaded inside
  # a pcall by a test config that reports through a file we own.
  LOAD_OUT="$REPO/tests/.last-load-results.txt"
  rm -f "$LOAD_OUT"
  wezterm --config-file "$REPO/tests/configload.test.lua" show-keys >/dev/null 2>&1
  if [ ! -f "$LOAD_OUT" ]; then
    record 'terminal.lua load check' 1 'no result written — the test config itself failed to load'
  elif grep -q '^FAIL' "$LOAD_OUT"; then
    record 'terminal.lua load check' 1 "$(grep '^FAIL' "$LOAD_OUT" | head -1 | cut -c1-100)"
  else
    record 'terminal.lua load check' 0
  fi
fi

printf '\n== summary\n'
for line in "${SUMMARY[@]}"; do printf '%s\n' "$line"; done
if [ "$FAILED" = 0 ]; then
  printf '\nAll suites passed.\n'
else
  printf '\nFAILURES — see above.\n'
fi
exit "$FAILED"
