-- attention.lua — PURE decision logic for the cross-tab "agent needs you"
-- notifications. No wezterm/io/os dependencies: data in, data out, so it can be
-- unit-tested in isolation (see tests/attention.test.lua). terminal.lua calls
-- this, so the tested logic IS the runtime logic.

local M = {}

-- Windows-aware path normalizer: backslashes -> '/', strip a leading slash
-- before a drive letter (/D:/x -> D:/x), drop trailing slashes, lowercase.
function M.norm_path(p)
  if not p or p == '' then return '' end
  p = p:gsub('\\', '/')
  if p:match('^/[A-Za-z]:') then p = p:sub(2) end
  return (p:gsub('/+$', '')):lower()
end

-- A flag filename is "legacy" (pre pane-id rename) if it ends in .json but is
-- not named pane-*.json. Such files must be purged so they can't ghost.
function M.is_legacy_name(name)
  if not name or not name:match('%.json$') then return false end
  return not name:match('^pane%-')
end

-- Chip/label text for a flag: the repo root maps to "Nexus", else the repo name.
function M.chip_label(cwd, repo, repo_dir_norm)
  if repo_dir_norm and repo_dir_norm ~= '' and cwd == repo_dir_norm then return 'Nexus' end
  return repo or '?'
end

-- Decide what to do with the current flags.
--   flags: array of { path, cwd (normalized), repo, pane (number|nil), ts (number|nil) }
--   ctx:   { pane_to_tab = {[pane_id]=tab_id} (live panes only),
--            active_tab_id, active_since, now, dwell_secs, max_age, repo_dir_norm }
-- returns { remove = {paths}, flagged_tabs = {[tab_id]=label}, chips = {{label,count}} }
--
-- Rules, in priority order, per flag:
--   * stale (older than max_age)                      -> remove
--   * pane gone / no pane field (orphan)              -> remove
--   * on the active tab AND dwelled >= dwell_secs     -> remove (attended)
--   * otherwise                                       -> flag its tab;
--       and if it's NOT the active tab, add a chip (deduped by label, counted)
function M.decide(flags, ctx)
  local out = { remove = {}, flagged_tabs = {}, chips = {} }
  local order, counts = {}, {}

  for _, fl in ipairs(flags) do
    local stale = fl.ts ~= nil and ctx.max_age ~= nil and (ctx.now - fl.ts) > ctx.max_age
    local tid   = fl.pane ~= nil and ctx.pane_to_tab[fl.pane] or nil

    if stale or tid == nil then
      out.remove[#out.remove + 1] = fl.path                          -- aged out OR orphan
    elseif tid == ctx.active_tab_id
        and ctx.active_since ~= nil
        and (ctx.now - ctx.active_since) >= ctx.dwell_secs then
      out.remove[#out.remove + 1] = fl.path                          -- attended on its tab
    else
      local label = M.chip_label(fl.cwd, fl.repo, ctx.repo_dir_norm)
      out.flagged_tabs[tid] = label                                  -- paint the tab amber
      if tid ~= ctx.active_tab_id then
        if counts[label] == nil then order[#order + 1] = label end
        counts[label] = (counts[label] or 0) + 1
      end
    end
  end

  for _, label in ipairs(order) do
    out.chips[#out.chips + 1] = { label = label, count = counts[label] }
  end
  return out
end

-- Visual style for a tab, as semantic tokens (terminal.lua maps them to colors).
-- The background is ALWAYS 'tab', so focusing a flagged tab — or clearing its
-- flag — never swaps the background (no flicker). Attention is carried by the
-- `dot` + the fg token, not by a background fill.
--   returns { bg = 'tab', fg = 'focus'|'attn'|'running'|'idle', dot = bool, bold = bool }
function M.tab_style(is_active, flagged, has_unseen)
  local s = { bg = 'tab', dot = flagged == true, bold = false }
  if is_active then
    s.fg, s.bold = 'focus', true
  elseif flagged then
    s.fg, s.bold = 'attn', true
  elseif has_unseen then
    s.fg = 'running'
  else
    s.fg = 'idle'
  end
  return s
end

return M
