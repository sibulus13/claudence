-- pathlink.lua — PURE decision logic for resolving a clicked terminal
-- hyperlink that has no drive-letter prefix (a "bare relative" file
-- reference: the common shape when a citation forgets D:/..., or when raw
-- tool output — a stack trace, a test-runner line, `git diff` — cites a path
-- relative to some working directory). No wezterm/io/os dependencies, so it
-- is unit-tested in isolation (see tests/pathlink.test.lua) the same way
-- attention.lua is. terminal.lua does the actual I/O (pane cwd lookup,
-- file-exists checks, the bounded fuzzy PowerShell search) and calls into
-- this module for the pure parts of the decision.

local M = {}

-- Splits a clicked reference into its path portion and a trailing ":line" or
-- ":line:col" suffix, if present. "foo/bar.md:12:3" -> "foo/bar.md", ":12:3".
-- "foo/bar.md" (no suffix) -> "foo/bar.md", "".
function M.split_suffix(ref)
  if not ref or ref == '' then return '', '' end
  local path_part, suffix = ref:match('^(.-)(:%d+:?%d*)$')
  if path_part and path_part ~= '' then return path_part, suffix end
  return ref, ''
end

-- Classifies a hyperlink-rule match so open-uri knows which branch to take:
--   "absolute" -- already has a drive letter ("D:/..." or "D:\...", with or
--                 without a leading "/" from a file:// URL)
--   "relative" -- looks like a bare file reference with no drive letter
--                 (a path ending in ".ext", optional trailing :line:col)
--   "other"    -- a URL scheme (http://, mailto:, etc.) or anything else --
--                 hand it back to WezTerm's own default handling
function M.classify(uri)
  if not uri or uri == '' then return 'other' end
  if uri:match('^file:') or uri:match('^/?%a:[/\\]') then return 'absolute' end
  if uri:match('^%a[%w+.-]*://') or uri:match('^mailto:') then return 'other' end
  local path_part = M.split_suffix(uri)
  if path_part:match('%.%a[%w]*$') then return 'relative' end
  return 'other'
end

-- Ordered list of absolute directories to try a direct join against, walking
-- from `cwd` up to (and including) `repo_root`, bounded so it can never walk
-- past the repo root or loop forever on a malformed cwd. Comparison against
-- repo_root is case-insensitive (Windows drive letters/paths). Pure string
-- logic -- callers do the actual io.open existence check against each entry.
function M.ancestor_dirs(cwd, repo_root)
  local out = {}
  if not cwd or cwd == '' then return out end
  cwd = cwd:gsub('\\', '/'):gsub('/+$', '')
  repo_root = (repo_root or ''):gsub('\\', '/'):gsub('/+$', '')
  local seen = {}
  local dir = cwd
  for _ = 1, 12 do
    if seen[dir:lower()] then break end
    seen[dir:lower()] = true
    out[#out + 1] = dir
    if repo_root ~= '' and dir:lower() == repo_root:lower() then break end
    local parent = dir:match('^(.*)/[^/]+$')
    if not parent or parent == '' then break end
    if repo_root ~= '' and #parent < #repo_root then break end
    dir = parent
  end
  return out
end

-- From a list of fuzzy-search hits (absolute paths under the search root),
-- picks the most likely intended match: shortest path wins (closest to the
-- search root = fewest directory hops from where the reference was likely
-- made), ties broken alphabetically for determinism. Returns nil for an
-- empty list.
function M.pick_closest(hits)
  if not hits or #hits == 0 then return nil end
  local best = hits[1]
  for i = 2, #hits do
    local h = hits[i]
    if #h < #best or (#h == #best and h < best) then best = h end
  end
  return best
end

return M
