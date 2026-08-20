-- linkrules.test.lua — every shape a clicked link arrives in, and where it must be routed.
--
-- Run by tests/run-tests.sh through WezTerm's bundled Lua (there is no `lua` binary here), the
-- same mechanism attention.test.lua uses. Results go to disk because WezTerm owns stdout.
--
-- The case that matters most is the repo-relative path: it is the shape agent output and this
-- repo's own documents are full of, and it was classified as a WEB link for as long as the
-- predicate lived inline and untested.

local wezterm = require 'wezterm'
-- Resolve the module relative to THIS file, not ~/.claude, so the suite tests the checkout
-- being edited and runs before setup.sh has installed anything. wezterm.config_file is the
-- path handed to --config-file.
local HERE = (wezterm.config_file or ''):match('^(.*)[/\\][^/\\]+$')
             or (wezterm.home_dir .. '/.claude/tests')
local L = dofile(HERE .. '/../linkrules.lua')

local pass, fail, lines = 0, 0, {}

local function check(uri, want, is_win)
  local got = L.is_local_target(uri, is_win or false)
  if got == want then
    pass = pass + 1
  else
    fail = fail + 1
    table.insert(lines, string.format('FAIL | %q -> %s, wanted %s', uri, tostring(got), tostring(want)))
  end
end

-- LOCAL — must reach the editor
check('docs/notes/harness/ORCHESTRATION-MAP.md', true)   -- the shape that was broken
check('4JIM/PROPOSAL.md', true)
check('docs/README.md:12', true)
check('harness/x1_tools.py:31:4', true)
check('/Users/me/repo/x/foo.ts', true)
check('/Users/me/repo/x/foo.ts:31:4', true)
check('~/repo/claudence/terminal.lua', true)
check('./scripts/gates.py', true)
check('ORCHESTRATION-MAP.md', true)
check('create_corporation.rb:31', true)
check('file:///Users/me/x.md', true)
check('D:\\repo\\foo.ts', true, true)                    -- Windows drive letter, not a scheme
check('/D:/repo/foo.ts', true, true)

-- NOT LOCAL — must stay with the OS
check('https://github.com/x/y', false)
check('http://admin.app.localhost:3000/administration', false)
check('mailto:someone@example.com', false)
check('ssh://host/path/file.md', false)
check('', false)
check('and/or', false)                                   -- no extension, so not a file
check('read/write', false)

-- A path-shaped thing with a scheme is still the OS's, which is the ordering the module enforces
check('vscode://file/Users/me/x.md', false)

local summary = string.format('%d passed, %d failed', pass, fail)
local out = io.open(HERE .. '/.last-link-results.txt', 'w')
for _, l in ipairs(lines) do out:write(l .. '\n') end
out:write(summary .. '\n')
out:close()

return {}
