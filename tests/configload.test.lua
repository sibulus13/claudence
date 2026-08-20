-- configload.test.lua — does terminal.lua actually LOAD?
--
-- OBJECTIVE — catch a config that crashes at reload, which no exit code reveals.
--
-- The check this replaces ran `wezterm --config-file terminal.lua show-keys` and read the exit
-- code. WezTerm reports a bad config, silently falls back to its DEFAULT config, and exits 0 —
-- and prints nothing to stderr through show-keys either. So the check passed for two days while
-- a missing module made the live terminal throw a runtime error on every reload.
--
-- The fix is to stop asking WezTerm whether it succeeded and load the file ourselves, in its own
-- interpreter, reporting through a channel we own — the pattern attention.test.lua established.

local wezterm = require 'wezterm'

local HERE = (wezterm.config_file or ''):match('^(.*)[/\\][^/\\]+$')
             or (wezterm.home_dir .. '/.claude/tests')
local OUT = HERE .. '/.last-load-results.txt'

local ok, err = pcall(dofile, HERE .. '/../terminal.lua')

local out = io.open(OUT, 'w')
if ok then
  out:write('1 passed, 0 failed\n')
else
  out:write('FAIL | terminal.lua did not load: ' .. tostring(err) .. '\n')
  out:write('0 passed, 1 failed\n')
end
out:close()

return {}
