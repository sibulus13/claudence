-- Tests for the relative-hyperlink resolution logic (~/.claude/pathlink.lua).
-- Run:  wezterm --config-file ~/.claude/tests/pathlink.test.lua show-keys
-- Results are written to ~/.claude/tests/.last-results-pathlink.txt.
local wezterm = require 'wezterm'
local PL = dofile(wezterm.home_dir .. '/.claude/pathlink.lua')

local OUT = wezterm.home_dir .. '/.claude/tests/.last-results-pathlink.txt'

local log, pass, fail = {}, 0, 0
local function check(name, cond, detail)
  if cond then pass = pass + 1; log[#log + 1] = 'PASS | ' .. name
  else fail = fail + 1; log[#log + 1] = 'FAIL | ' .. name .. '  -- ' .. tostring(detail or '') end
end

-- split_suffix
do
  local p, s = PL.split_suffix('foo/bar.md:12:3')
  check('split_suffix line+col', p == 'foo/bar.md' and s == ':12:3', p .. '|' .. s)
  p, s = PL.split_suffix('foo/bar.md:12')
  check('split_suffix line only', p == 'foo/bar.md' and s == ':12', p .. '|' .. s)
  p, s = PL.split_suffix('foo/bar.md')
  check('split_suffix no suffix', p == 'foo/bar.md' and s == '', p .. '|' .. s)
  p, s = PL.split_suffix('')
  check('split_suffix empty', p == '' and s == '')
  p, s = PL.split_suffix(nil)
  check('split_suffix nil', p == '' and s == '')
end

-- classify
do
  check('classify absolute fwd-slash', PL.classify('D:/repo/foo.md') == 'absolute')
  check('classify absolute backslash', PL.classify('D:\\repo\\foo.md') == 'absolute')
  check('classify absolute file url leading slash', PL.classify('/D:/repo/foo.md') == 'absolute')
  check('classify file scheme', PL.classify('file:///D:/repo/foo.md') == 'absolute')
  check('classify relative bare filename', PL.classify('VERIFY.md') == 'relative')
  check('classify relative with line', PL.classify('MASTER-COMPARISON.md:129') == 'relative')
  check('classify relative nested', PL.classify('Life/Housing/NOMAD/VERIFY.md:20') == 'relative')
  check('classify relative backslash-nested', PL.classify('src\\foo.ts:12') == 'relative')
  check('classify http url -> other', PL.classify('http://example.com/foo.md') == 'other')
  check('classify https url -> other', PL.classify('https://example.com') == 'other')
  check('classify mailto -> other', PL.classify('mailto:a@b.com') == 'other')
  check('classify plain prose word -> other', PL.classify('hello') == 'other')
  check('classify empty -> other', PL.classify('') == 'other')
  check('classify nil -> other', PL.classify(nil) == 'other')
end

-- ancestor_dirs
do
  local dirs = PL.ancestor_dirs('D:/repo/Life/Housing/NOMAD', 'D:/repo')
  check('ancestor_dirs starts at cwd', dirs[1] == 'D:/repo/Life/Housing/NOMAD', dirs[1])
  check('ancestor_dirs ends at repo root', dirs[#dirs] == 'D:/repo', dirs[#dirs])
  check('ancestor_dirs walks every level', #dirs == 4, tostring(#dirs))  -- NOMAD, Housing, Life, repo

  local dirs2 = PL.ancestor_dirs('D:/repo', 'D:/repo')
  check('ancestor_dirs cwd==root -> single entry', #dirs2 == 1 and dirs2[1] == 'D:/repo', tostring(#dirs2))

  local dirs3 = PL.ancestor_dirs('', 'D:/repo')
  check('ancestor_dirs empty cwd -> empty', #dirs3 == 0)

  -- cwd outside repo_root: must not walk forever or blow past a sane bound
  local dirs4 = PL.ancestor_dirs('E:/elsewhere/deep/path', 'D:/repo')
  check('ancestor_dirs outside root terminates', #dirs4 > 0 and #dirs4 <= 12, tostring(#dirs4))

  -- trailing slashes / backslashes normalized
  local dirs5 = PL.ancestor_dirs('D:\\repo\\Life\\', 'D:/repo/')
  check('ancestor_dirs normalizes slashes', dirs5[1] == 'D:/repo/Life' and dirs5[#dirs5] == 'D:/repo',
    dirs5[1] .. ' .. ' .. dirs5[#dirs5])
end

-- pick_closest
do
  check('pick_closest empty -> nil', PL.pick_closest({}) == nil)
  check('pick_closest nil -> nil', PL.pick_closest(nil) == nil)
  check('pick_closest single', PL.pick_closest({ 'D:/repo/a/foo.md' }) == 'D:/repo/a/foo.md')
  local best = PL.pick_closest({ 'D:/repo/deep/nested/dir/foo.md', 'D:/repo/foo.md' })
  check('pick_closest shortest wins', best == 'D:/repo/foo.md', best)
  local tie = PL.pick_closest({ 'D:/repo/b/x.md', 'D:/repo/a/x.md' })
  check('pick_closest tie -> alphabetical', tie == 'D:/repo/a/x.md', tie)
end

log[#log + 1] = ('---- %d passed, %d failed ----'):format(pass, fail)
local f = io.open(OUT, 'w')
if f then f:write(table.concat(log, '\n') .. '\n'); f:close() end
return {}
