-- Tests for the session-restore decision logic (restore.lua).
-- Run:  tests/run-tests.sh   (or directly:
--       wezterm --config-file <this file> show-keys)
-- Results are written next to this file as .last-restore-results.txt — read that,
-- not stdout: WezTerm owns stdout when it loads a config file.
--
-- This suite exists because the restore path had none, and the failure mode was
-- the quiet kind: a freshness cap silently discarded every tab across a weekend
-- close, so the window opened bare and read as "nothing was ever saved".
local wezterm = require 'wezterm'

local HERE = (wezterm.config_file or ''):match('^(.*)[/\\][^/\\]+$')
             or (wezterm.home_dir .. '/.claude/tests')
local R = dofile(HERE .. '/../restore.lua')

local OUT = HERE .. '/.last-restore-results.txt'
local log, pass, fail = {}, 0, 0
local function check(name, cond, detail)
  if cond then pass = pass + 1; log[#log + 1] = 'PASS | ' .. name
  else fail = fail + 1; log[#log + 1] = 'FAIL | ' .. name .. '  -- ' .. tostring(detail or '') end
end

local HOUR = 3600
local NOW  = 1787600000

-- 1. Freshness: the regression that ate a weekend's layout.
do
  check('a layout saved minutes ago is fresh',
    R.layout_is_fresh(NOW - 120, NOW) == true)
  check('an overnight close still restores (14 h)',
    R.layout_is_fresh(NOW - 14 * HOUR, NOW) == true)
  check('a weekend close still restores (61 h)',
    R.layout_is_fresh(NOW - 61 * HOUR, NOW) == true)
  check('past a week it is dropped — the pane bindings are reaped by then',
    R.layout_is_fresh(NOW - 169 * HOUR, NOW) == false)
  local _, age = R.layout_is_fresh(NOW - 61 * HOUR, NOW)
  check('the age comes back so the drop can be logged, not silent',
    math.abs(age - 61) < 0.01, age)
  check('a missing savedAt is ancient, not fresh',
    R.layout_is_fresh(nil, NOW) == false)
  check('the cap is a week', R.MAX_H == 168, R.MAX_H)
end

-- 2. Which tabs round-trip.
do
  check('a repo-relative tab is restored', R.is_repo_tab('web/myapp') == true)
  check('Nexus is not a repo tab', R.is_repo_tab('Nexus') == false)
  check('a shell-named tab is not a repo tab', R.is_repo_tab('zsh') == false)
  check('a home-relative tab is skipped', R.is_repo_tab('~/scratch') == false)
  check('an empty title is not a repo tab', R.is_repo_tab('') == false)
  check('a nil title is not a repo tab', R.is_repo_tab(nil) == false)
end

-- 3. The session id is interpolated into a shell command — it must be UUID-shaped.
do
  check('a UUID is accepted',
    R.valid_session_id('59611ad4-bc6a-44c6-affb-685fd7b5a2be') ~= nil)
  check('a shell metacharacter is refused', R.valid_session_id('abc; rm -rf /') == nil)
  check('a quoted injection is refused', R.valid_session_id("a' && curl x") == nil)
  check('an empty id is refused', R.valid_session_id('') == nil)
  check('a non-string id is refused', R.valid_session_id({}) == nil)
  check('an injected id falls back to --continue rather than running',
    R.claude_cmd('abc; rm -rf /') == R.CLAUDE_FALLBACK)
end

-- 4. What a pane gets relaunched with.
do
  check('a bound Claude pane resumes THAT conversation',
    R.resume_cmd('/Users/x/.local/bin/claude', 'abc-123', nil, nil, false)
      == 'claude --resume abc-123 --permission-mode auto')
  check('an unbound Claude pane falls back to the cwd guess',
    R.resume_cmd('claude', nil, nil, nil, false) == R.CLAUDE_FALLBACK)
  check('a restored agent is not left in ask-everything mode',
    R.claude_cmd('abc-123'):find('--permission-mode auto', 1, true) ~= nil)
  check('an idle shell is NOT captured as a command',
    R.resume_cmd('/bin/zsh', nil, '/bin/zsh', { '-zsh' }, false) == nil)
  check('a dev server is reconstructed from argv',
    R.resume_cmd('/opt/homebrew/bin/node', nil, '/opt/homebrew/bin/node',
                 { 'node', 'vite' }, false) == 'node vite')
  check('an argument with spaces survives quoting',
    R.resume_cmd('node', nil, 'node', { 'node', 'a b' }, false) == "node 'a b'")
  check('a whitelisted program with no argv is not resumed',
    R.resume_cmd('node', nil, 'node', {}, false) == nil)
  check('an unlisted program is not resumed',
    R.resume_cmd('/usr/bin/less', nil, '/usr/bin/less', { 'less', 'x' }, false) == nil)
  check('a windows exe resolves to its leaf key',
    R.leaf_name('C:\\Program Files\\nodejs\\node.exe') == 'node')
end

-- 5. The spawn wrapper: an exited command must leave a live prompt.
do
  local a = R.launch_args('claude --continue', '/Users/x/repo/app', '/bin/zsh', false)
  check('the pane cds into the repo first', a[3]:find("cd '/Users/x/repo/app'", 1, true) ~= nil, a[3])
  check('a crashed command leaves an interactive shell',
    a[3]:find('exec /bin/zsh -l', 1, true) ~= nil, a[3])
  check('a compound command is braced, so `exec` is not bound to its first clause',
    a[3]:find('{ claude --continue; }', 1, true) ~= nil, a[3])
  check('a quote in the cwd cannot break out of the quoting',
    R.launch_args('x', "/tmp/it's", '/bin/zsh', false)[3]:find("'\\''", 1, true) ~= nil)
  check('no command means no wrapper — the caller spawns a plain shell',
    R.launch_args(nil, '/tmp', '/bin/zsh', false) == nil)
  check('an empty command means no wrapper',
    R.launch_args('', '/tmp', '/bin/zsh', false) == nil)
  check('windows gets PowerShell -NoExit',
    R.launch_args('pnpm dev', 'C:/repo', nil, true)[4] == '-NoExit')
end

log[#log + 1] = ('---- %d passed, %d failed ----'):format(pass, fail)
local f = io.open(OUT, 'w')
if f then f:write(table.concat(log, '\n') .. '\n'); f:close() end
return {}
