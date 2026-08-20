-- linkrules.lua — PURE classification of a clicked link: is this target a LOCAL FILE that
-- should open in an editor, or something the OS should handle (a web URL, a mail address)?
--
-- OBJECTIVE — the decision that routes a click, kept where it can be tested. No wezterm/io/os
-- dependencies: string in, boolean out, so tests/linkrules.test.lua exercises the same code the
-- runtime does (the pattern attention.lua established).
--
-- It exists because this predicate was inline in terminal.lua and silently WRONG for the most
-- common shape in agent output. Its character class excluded '/' while being anchored ^...$, so
-- "docs/notes/harness/MAP.md" — a repo-relative path — was classified NON-local and handed to
-- the browser. Both halves of the chain around it had already been fixed; the click still did
-- nothing, because a rule made the link and this predicate threw it away.

local M = {}

-- Anything with a scheme belongs to the OS, except file: which is ours. Checked FIRST so a URL
-- can never fall through to the path patterns below.
local function has_foreign_scheme(uri)
  local scheme = uri:match('^(%a[%w+.-]*):')
  return scheme ~= nil and scheme:lower() ~= 'file'
end

-- One optional trailing :line or :line:col, which editors accept and paths do not contain.
local POSITION = ':%d+:?%d*$'

--- Is `uri` a local file target?
-- @param uri  the matched link text, verbatim from the terminal
-- @param is_win  true on Windows, where drive letters are paths and not schemes
function M.is_local_target(uri, is_win)
  if type(uri) ~= 'string' or uri == '' then return false end
  if uri:match('^file:') then return true end

  if is_win then
    -- D:\repo\x.ts or /D:/repo/x.ts — a drive letter looks like a scheme, so it precedes the
    -- foreign-scheme test rather than following it.
    if uri:match('^/?%a:[/\\]') then return true end
  end
  if has_foreign_scheme(uri) then return false end

  -- Absolute and home-relative are unambiguous.
  if uri:match('^/') or uri:match('^~/') then return true end

  -- Everything else must carry a file extension to be a file at all. The class now includes
  -- '/' so a repo-relative path with directories qualifies, and '$'-anchoring is kept so a
  -- sentence containing a path does not.
  local body = uri:gsub(POSITION, '')
  if body:match('^[%w%-%+@_./]+%.%a[%w]*$') then return true end

  return false
end

return M
