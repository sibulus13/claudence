-- Tests for the notification decision logic (~/.claude/attention.lua).
-- Run:  wezterm --config-file ~/.claude/tests/attention.test.lua show-keys
-- Results are written to scratchpad/attention-test-out.txt (read that, not stdout).
local wezterm = require 'wezterm'
local A = dofile(wezterm.home_dir .. '/.claude/attention.lua')

local OUT = wezterm.home_dir .. '/.claude/tests/.last-results.txt'

local log, pass, fail = {}, 0, 0
local function check(name, cond, detail)
  if cond then pass = pass + 1; log[#log + 1] = 'PASS | ' .. name
  else fail = fail + 1; log[#log + 1] = 'FAIL | ' .. name .. '  -- ' .. tostring(detail or '') end
end
local function has(list, v)
  for _, x in ipairs(list) do if x == v then return true end end
  return false
end
local function count(t) local n = 0; for _ in pairs(t) do n = n + 1 end; return n end

local NOW = 1000000
local function ctx(over)
  local c = {
    pane_to_tab = {}, active_tab_id = -1, active_since = NOW - 999,
    now = NOW, dwell_secs = 5, max_age = 43200, repo_dir_norm = 'd:/repo',
  }
  for k, v in pairs(over or {}) do c[k] = v end
  return c
end

-- 1. live pane, non-active tab -> flagged + one chip, nothing removed
do
  local r = A.decide({ { path = 'p1', cwd = 'd:/repo/web/cashcow', repo = 'cashcow', pane = 32, ts = NOW } },
    ctx({ pane_to_tab = { [32] = 5 } }))
  check('live non-active -> flagged', r.flagged_tabs[5] == 'cashcow', 'flagged_tabs=' .. tostring(r.flagged_tabs[5]))
  check('live non-active -> 1 chip', #r.chips == 1 and r.chips[1].label == 'cashcow' and r.chips[1].count == 1)
  check('live non-active -> no removal', #r.remove == 0)
end

-- 2. pane not live (orphan) -> removed, no chip/flag
do
  local r = A.decide({ { path = 'p2', cwd = 'd:/repo/x', repo = 'x', pane = 99, ts = NOW } },
    ctx({ pane_to_tab = {} }))
  check('orphan -> removed', has(r.remove, 'p2'))
  check('orphan -> no flag', count(r.flagged_tabs) == 0)
  check('orphan -> no chip', #r.chips == 0)
end

-- 3. legacy flag (no pane field) is treated as orphan; is_legacy_name helper
do
  local r = A.decide({ { path = 'leg', cwd = 'd:/repo/life', repo = 'life', pane = nil, ts = NOW } }, ctx())
  check('legacy(no pane) -> removed', has(r.remove, 'leg'))
  check('is_legacy_name old', A.is_legacy_name('d-repo-life__abc.json') == true)
  check('is_legacy_name pane', A.is_legacy_name('pane-2.json') == false)
end

-- 4. active tab, dwell NOT yet met -> flagged (focus+dot), no chip, not removed
do
  local r = A.decide({ { path = 'p4', cwd = 'd:/repo/web/cashcow', repo = 'cashcow', pane = 32, ts = NOW } },
    ctx({ pane_to_tab = { [32] = 1 }, active_tab_id = 1, active_since = NOW - 2 }))
  check('active+short-dwell -> flagged', r.flagged_tabs[1] == 'cashcow')
  check('active+short-dwell -> no chip', #r.chips == 0)
  check('active+short-dwell -> not removed', #r.remove == 0)
end

-- 5. active tab, dwell met -> removed (attended)
do
  local r = A.decide({ { path = 'p5', cwd = 'd:/repo/web/cashcow', repo = 'cashcow', pane = 32, ts = NOW } },
    ctx({ pane_to_tab = { [32] = 1 }, active_tab_id = 1, active_since = NOW - 10 }))
  check('active+dwell -> removed', has(r.remove, 'p5'))
  check('active+dwell -> no flag', count(r.flagged_tabs) == 0)
end

-- 6. stale by age -> removed even when pane is live + non-active
do
  local r = A.decide({ { path = 'p6', cwd = 'd:/repo/x', repo = 'x', pane = 7, ts = NOW - 50000 } },
    ctx({ pane_to_tab = { [7] = 9 } }))
  check('stale -> removed', has(r.remove, 'p6'))
  check('stale -> no flag', count(r.flagged_tabs) == 0)
end

-- 7. Nexus label for the repo root
do
  local r = A.decide({ { path = 'p7', cwd = 'd:/repo', repo = 'repo', pane = 0, ts = NOW } },
    ctx({ pane_to_tab = { [0] = 3 } }))
  check('nexus label chip', #r.chips == 1 and r.chips[1].label == 'Nexus')
  check('nexus label flag', r.flagged_tabs[3] == 'Nexus')
end

-- 8. same repo across two non-active tabs -> single chip, count 2
do
  local r = A.decide({
    { path = 'a', cwd = 'd:/repo/web/cashcow', repo = 'cashcow', pane = 10, ts = NOW },
    { path = 'b', cwd = 'd:/repo/web/cashcow', repo = 'cashcow', pane = 11, ts = NOW },
  }, ctx({ pane_to_tab = { [10] = 7, [11] = 8 } }))
  check('dedup -> 1 chip', #r.chips == 1, '#chips=' .. #r.chips)
  check('dedup -> count 2', r.chips[1] and r.chips[1].count == 2)
  check('dedup -> both tabs flagged', r.flagged_tabs[7] == 'cashcow' and r.flagged_tabs[8] == 'cashcow')
end

-- 9. distinct repos -> ordered chips
do
  local r = A.decide({
    { path = 'a', cwd = 'd:/repo/aa', repo = 'aa', pane = 10, ts = NOW },
    { path = 'b', cwd = 'd:/repo/bb', repo = 'bb', pane = 11, ts = NOW },
  }, ctx({ pane_to_tab = { [10] = 7, [11] = 8 } }))
  check('order chip1=aa', r.chips[1] and r.chips[1].label == 'aa')
  check('order chip2=bb', r.chips[2] and r.chips[2].label == 'bb')
end

-- 10. norm_path
do
  check('norm leading/trailing slash', A.norm_path('/D:/repo/Foo/') == 'd:/repo/foo', A.norm_path('/D:/repo/Foo/'))
  check('norm backslashes', A.norm_path('D:\\repo\\Bar') == 'd:/repo/bar', A.norm_path('D:\\repo\\Bar'))
  check('norm empty', A.norm_path('') == '')
  check('norm nil', A.norm_path(nil) == '')
end

-- 11. active tab but active_since nil (just arrived) -> not cleared
do
  local c = ctx({ pane_to_tab = { [4] = 1 }, active_tab_id = 1 })
  c.active_since = nil  -- can't pass nil through the merge (Lua drops nil keys)
  local r = A.decide({ { path = 'p11', cwd = 'd:/repo/x', repo = 'x', pane = 4, ts = NOW } }, c)
  check('active+no-since -> not removed', #r.remove == 0)
  check('active+no-since -> flagged', r.flagged_tabs[1] == 'x')
end

-- 12. no flags -> all empty
do
  local r = A.decide({}, ctx())
  check('empty -> no remove', #r.remove == 0)
  check('empty -> no flags', count(r.flagged_tabs) == 0)
  check('empty -> no chips', #r.chips == 0)
end

-- 13. tab_style: the BACKGROUND must be identical in every state, so focusing a
-- flagged tab (or clearing it) never flips the bg -> no flicker. Flagged differs
-- from focused only by fg/dot.
do
  local fa = A.tab_style(true,  true,  false)  -- focused + flagged
  local ua = A.tab_style(false, true,  false)  -- unfocused + flagged
  local fp = A.tab_style(true,  false, false)  -- focused, no flag
  local ru = A.tab_style(false, false, true)   -- unfocused, running
  local id = A.tab_style(false, false, false)  -- idle
  check('tabstyle focused+flagged', fa.bg == 'tab' and fa.fg == 'focus' and fa.dot == true and fa.bold == true)
  check('tabstyle unfocused+flagged', ua.bg == 'tab' and ua.fg == 'attn' and ua.dot == true and ua.bold == true)
  check('NO-FLICKER: flagged focus==unfocus bg', fa.bg == ua.bg, tostring(fa.bg) .. ' vs ' .. tostring(ua.bg))
  check('NO-FLICKER: bg constant everywhere',
    fa.bg == 'tab' and ua.bg == 'tab' and fp.bg == 'tab' and ru.bg == 'tab' and id.bg == 'tab')
  check('tabstyle dot iff flagged', fa.dot and ua.dot and not fp.dot and not ru.dot and not id.dot)
  check('tabstyle focused-plain', fp.fg == 'focus' and fp.dot == false)
  check('tabstyle running', ru.fg == 'running' and ru.dot == false)
  check('tabstyle idle', id.fg == 'idle' and id.dot == false)
end

-- 14. dwell EXACTLY at the boundary (now - active_since == dwell_secs) -> removed.
-- Guards the `>=` in the dwell-clear rule: the terminal.lua repaint nudge only
-- fires on the tick a flag enters res.remove, so the boundary must clear, not lag
-- one tick past it (a `>` slip would leave the just-attended dot stuck).
do
  local r = A.decide({ { path = 'p14', cwd = 'd:/repo/x', repo = 'x', pane = 4, ts = NOW } },
    ctx({ pane_to_tab = { [4] = 1 }, active_tab_id = 1, active_since = NOW - 5 }))
  check('active+dwell-boundary -> removed', has(r.remove, 'p14'))
  check('active+dwell-boundary -> no flag', count(r.flagged_tabs) == 0)
end

log[#log + 1] = ('---- %d passed, %d failed ----'):format(pass, fail)
local f = io.open(OUT, 'w')
if f then f:write(table.concat(log, '\n') .. '\n'); f:close() end
return {}
