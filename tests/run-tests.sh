#!/usr/bin/env bash
# run-tests.sh — the macOS test runner (counterpart of run-tests.ps1 + run-attention-tests.ps1).
#
#   tests/run-tests.sh          run everything
#   tests/run-tests.sh --quiet  only print the summary
#
# Exit 0 = everything passed. Three suites:
#   1. classification.test.py  pure prompt-classification logic
#   2. hooks.test.py           every hook run as a subprocess against a temp HOME
#   3. attention.test.lua      the tab-attention decision logic, run in WezTerm's
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
if [ ! -e "$HOME/.claude/attention.lua" ]; then
  SUMMARY+=('  skip  terminal.lua load check  (not installed yet — run ./setup.sh)')
  note '  skipped: ~/.claude/attention.lua missing'
else
  if wezterm --config-file "$REPO/terminal.lua" show-keys >/dev/null 2>&1; then
    record 'terminal.lua load check' 0
  else
    record 'terminal.lua load check' 1 'wezterm rejected the config'
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
