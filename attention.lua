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

-- ── Claude-session detection (drives no-Claude tab dimming) ──────────────────
-- A pane's foreground PROCESS name is an unreliable "is Claude here?" signal:
-- while Claude runs a tool the foreground process is the tool's shell
-- (bash/pwsh/cmd), not claude.exe, so a process-only check flickers and reads
-- "no Claude" mid-tool. Claude owns the pane's OSC TITLE the entire time it runs
-- though — "✳ Claude Code" when idle, "✳ <activity>" / "⠂ <activity>" (braille
-- spinner) when working — and that title is STABLE across tool execution. So we
-- treat a pane as Claude when EITHER the process or the title says so. These are
-- pure string predicates → unit-tested, so the runtime detection is the tested one.

-- Claude's brand/spinner lead glyphs: the ✳ sparkle family and the braille
-- spinner block (U+2800–U+28FF). Generic bullets/stars are deliberately excluded
-- to avoid false positives from ordinary shell prompts.
local CLAUDE_SPARKS = {
  '\u{2733}', '\u{2734}', '\u{2731}', '\u{2732}', '\u{2736}', '\u{2737}',
  '\u{2726}', '\u{2728}', '\u{273B}', '\u{273D}', '\u{2742}', '\u{2743}',
  '\u{2748}', '\u{2749}', '\u{274A}', '\u{274B}',
}

-- True when a title STARTS with a Claude "working" spinner frame: the braille
-- block (U+2800–U+28FF = E2 A0..A3 xx) or the ◐◓◑◒ half-circles (U+25D0–U+25D3 =
-- E2 97 90..93) that current Claude Code versions cycle while processing. The
-- ✳ sparkle is the IDLE title, so it is deliberately not a spinner.
function M.title_is_spinning(title)
  if not title or title == '' then return false end
  local b1, b2, b3 = title:byte(1, 3)
  if b1 ~= 0xE2 or b2 == nil then return false end
  if b2 >= 0xA0 and b2 <= 0xA3 then return true end
  return b2 == 0x97 and b3 ~= nil and b3 >= 0x90 and b3 <= 0x93
end

-- True when a title STARTS with a Claude marker glyph (sparkle or braille frame).
function M.title_has_claude_marker(title)
  if not title or title == '' then return false end
  for _, m in ipairs(CLAUDE_SPARKS) do
    if title:sub(1, #m) == m then return true end
  end
  return M.title_is_spinning(title)
end

-- True when a pane is running Claude Code, by process name OR OSC title.
function M.is_claude_pane(proc, title)
  if proc and proc:lower():find('claude', 1, true) then return true end
  if title and title:lower():find('claude', 1, true) then return true end
  return M.title_has_claude_marker(title)
end

-- Claude state of ONE pane: 'running' (spinner title), 'idle' (Claude open,
-- not working), or 'none'. A tab takes the strongest state across its panes.
function M.claude_state(proc, title)
  if M.title_is_spinning(title) then return 'running' end
  if M.is_claude_pane(proc, title) then return 'idle' end
  return 'none'
end

-- Tab paint = two INDEPENDENT channels, so neither can hide the other:
--   background → FOCUS  ('focus' on the active tab, 'tab' otherwise)
--   title fg   → STATE  ('attn' | 'running' | 'idle' | 'noclaude')
-- A flag clearing never flips the bg (no flicker), and focusing a tab no longer
-- paints over its state. Precedence: attn (agent finished, you haven't looked —
-- the Stop-hook flag) > running > idle > noclaude.
--   returns { bg = 'tab'|'focus', fg = <state>, dot = bool, bold = bool }
function M.tab_paint(is_active, flagged, claude_state)
  local fg = 'noclaude'
  if flagged then fg = 'attn'
  elseif claude_state == 'running' then fg = 'running'
  elseif claude_state == 'idle' then fg = 'idle' end
  return { bg = is_active and 'focus' or 'tab', fg = fg, dot = flagged == true,
           bold = is_active == true or flagged == true }
end

return M
