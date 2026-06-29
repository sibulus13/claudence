local wezterm = require 'wezterm'
local config  = wezterm.config_builder()
local act     = wezterm.action

-- Pure notification decision logic (unit-tested in tests/attention.test.lua).
-- terminal.lua does only the impure I/O; all the rules live in this module, so
-- the tested logic IS the runtime logic.
local A = dofile(wezterm.home_dir .. '/.claude/attention.lua')

-- Auto-reload on file save — no Ctrl+Shift+R needed after edits.
-- WezTerm watches the resolved symlink target, so saving terminal.lua
-- in ~/.claude/ triggers the reload directly.
config.automatically_reload_config = true
-- This file is dofile'd from ~/.wezterm.lua, so WezTerm's reload watcher never
-- sees it on its own. Register it explicitly so saving terminal.lua reloads.
if wezterm.add_to_config_reload_watch_list then
  wezterm.add_to_config_reload_watch_list(wezterm.home_dir .. '/.claude/terminal.lua')
  -- attention.lua is dofile'd too, so watch it as well — otherwise editing the
  -- notification logic alone wouldn't trigger a reload (stale-config trap).
  wezterm.add_to_config_reload_watch_list(wezterm.home_dir .. '/.claude/attention.lua')
end

-- ── Appearance ────────────────────────────────────────────────────────────────
-- Base theme: Catppuccin Mocha, fetched as a mutable table so individual slots
-- can be tweaked. Built-in schemes don't define tab_bar, so we set it below.
local theme      = wezterm.color.get_builtin_schemes()['Catppuccin Mocha']
theme.ansi[5]    = '#7a5cf0'   -- blue (ANSI 4)   → darker, more saturated violet (not reddish)
theme.brights[5] = '#9d86ff'   -- bright blue (12) → lighter violet for bold/bright text

-- Flat tab bar: active and inactive tabs share one background, so the focused
-- tab is signalled by BOLD accent text in format-tab-title — not a low-contrast
-- background swap. (Built-in schemes omit tab_bar, hence the full definition.)
theme.tab_bar = {
  background         = '#11111b',
  active_tab         = { bg_color = '#181825', fg_color = '#f53f8f', intensity = 'Bold' },
  inactive_tab       = { bg_color = '#181825', fg_color = '#9399b2' },
  inactive_tab_hover = { bg_color = '#11111b', fg_color = '#cdd6f4' },
  new_tab            = { bg_color = '#11111b', fg_color = '#585b70' },
  new_tab_hover      = { bg_color = '#181825', fg_color = '#cdd6f4' },
}
config.colors = theme
config.font                      = wezterm.font('JetBrains Mono', { weight = 'Regular' })
config.font_size                 = 11.0
config.window_padding            = { left = 6, right = 6, top = 4, bottom = 4 }
config.window_background_opacity = 1.0   -- fully opaque (was 0.96 — that 4% was the "semi-translucent" look)

-- ── Accent palette ──────────────────────────────────────────────────────────
-- Matched to the keymap section-header accent (rgb 200,70,155 / #c8469b) but
-- pushed darker, more saturated, and toward the red side of magenta per request.
local ACCENT    = '#cf1a73'   -- status bar + focused-tab base (reddish-purple)
local ACCENT_HI = '#f53f8f'   -- focused tab title — brighter tint, pops on active-tab bg
local ATTN      = '#f9af3a'   -- amber: agent stopped (bell), tab is waiting on you
local RUNNING   = '#9399b2'   -- agent still producing output
local IDLE      = '#585b70'   -- inactive, quiet
-- No-Claude dimming: a tab/workspace with no live Claude session reads in a
-- LOW-contrast grey so the ones that DO have an agent dominate the bar. Both are
-- dimmer than IDLE (a tab can be idle yet still have Claude open); the *_HI tone
-- is for the focused tab so "you are here" stays legible without the loud accent.
local NOCLAUDE    = '#3a3c4e'   -- no Claude, unfocused: barely-there, recedes into the bar
local NOCLAUDE_HI = '#7f849c'   -- no Claude, focused (or the off-home chip): muted but readable

-- Left Alt = clean modifier (no special chars); Right Alt still composes é, ñ, etc.
config.send_composed_key_when_left_alt_is_pressed  = false
config.send_composed_key_when_right_alt_is_pressed = true

-- Bell drives the tab attention indicator (amber ⬤) via the 'bell' event below.
-- Disabled here only silences WezTerm's own beep — the event still fires.
config.audible_bell = 'Disabled'

-- New panes (Alt+T / Alt+C / the split_dir table) inherit this. Without it,
-- WezTerm's Windows default is cmd.exe, which keeps NO cross-session command
-- history — so ↑-recall is empty after a restart. PowerShell + PSReadLine
-- persists history incrementally to ConsoleHost_history.txt. Only ARG-LESS
-- spawns use this; every explicit `powershell.exe {...}` spawn below is
-- unaffected. -NoProfile keeps parity with the rest of the file; PSReadLine
-- auto-loads on the first Set-PSReadLineOption call, then -NoExit drops to the
-- interactive shell.
config.default_prog = {
  'powershell.exe', '-NoProfile', '-NoLogo', '-NoExit', '-Command',
  'Set-PSReadLineOption -HistorySaveStyle SaveIncrementally -MaximumHistoryCount 10000',
}

-- ── Tab bar ───────────────────────────────────────────────────────────────────
config.use_fancy_tab_bar              = false
config.tab_bar_at_bottom              = true
config.hide_tab_bar_if_only_one_tab   = false
config.tab_max_width                  = 28
config.show_new_tab_button_in_tab_bar = false

-- Tab states — color carries focus; the ⬤ appears ONLY when a tab needs you:
--   focused   → bold accent text     you are here (no dot, no bg highlight)
--   attention → amber ⬤ + bold       Stop/permission hook flagged it: agent done
--   running   → muted (has output)   agent still working in the background
--   idle      → dim                  nothing happening
-- "attention" is driven by the per-session flag files (attn_set), not a terminal
-- bell — distinct from has_unseen_output, which flips on every line of output.

-- ── Cross-workspace attention (file-bridge) — shared state ──────────────────
-- WezTerm's tab bar only renders the ACTIVE workspace's tabs, so the bell can't
-- show that a *background* workspace's agent finished. The Stop / Permission-
-- Request hooks drop one flag file PER SESSION here (keyed by cwd + session id,
-- so two sessions in the same repo stay independent):
--   ~/.claude/workspaces/attention/<cwd>__<sid>.json = {cwd,repo,session,ts}
-- update-status refills attn_set each tick so format-tab-title can paint the
-- matching TAB amber (tabs are clickable). Matching is EXACT per directory, so
-- every workspace/tab — including the Nexus home (the repo root) — is treated
-- independently: a flag colors only its own tab and clears only when you DWELL
-- in that exact tab for ATTN_DWELL_SECS. Alt+G jumps to whatever is waiting.
local ATTN_DIR        = wezterm.home_dir .. '/.claude/workspaces/attention'
local ATTN_DWELL_SECS = 5
local ATTN_MAX_AGE    = 12 * 3600   -- auto-expire zombie flags after 12 h
local flagged_tabs    = {}          -- [tab_id] = repo  (tabs with a pending flag; refilled each tick)
local claude_tabs      = {}         -- [tab_id] = true when a pane in the tab runs Claude (drives no-Claude dimming)
local _claude_scan_at  = 0          -- last os.time() the foreground-process scan ran (throttled below)
local CLAUDE_SCAN_SECS = 2          -- min secs between scans — a per-pane proc lookup isn't free at 4 ticks/s
local REPO_DIR_NORM   = ''          -- normalized repo root; set once REPO_DIR is known (labels the home flag "Nexus")
local _attn_active_tab   = nil      -- focused tab_id; drives the dwell-clear timer
local _attn_active_since = 0

local norm_path = A.norm_path  -- alias the tested normalizer

-- Read every flag file into raw records. All filtering (stale/orphan/dwell) is
-- A.decide's job; here we just surface what's on disk (the `now` arg is unused,
-- kept for call-site compatibility).
local function read_attention(now)
  local out = {}
  local ok, entries = pcall(wezterm.read_dir, ATTN_DIR)
  if not ok then return out end
  for _, path in ipairs(entries) do
    if path:match('%.json$') then
      local f = io.open(path, 'r')
      if f then
        local raw = f:read('*a'); f:close()
        raw = raw:gsub('^\239\187\191', '')  -- strip UTF-8 BOM if present
        local ok2, data = pcall(wezterm.json_parse, raw)
        if ok2 and type(data) == 'table' and data.cwd then
          out[#out+1] = { path = path, cwd = norm_path(data.cwd), repo = data.repo or '?',
                          pane = data.pane, ts = data.ts }
        end
      end
    end
  end
  return out
end

-- On load/reload: purge legacy (pre-pane-id) attention flags so a stale chip
-- from the old cwd-keyed format can't ghost. Only pane-*.json is valid now.
do
  local ok, entries = pcall(wezterm.read_dir, ATTN_DIR)
  if ok then
    for _, p in ipairs(entries) do
      if A.is_legacy_name(p:match('[^/\\]+$') or '') then os.remove(p) end
    end
  end
end

-- Locate the workspace + tab that owns a pending flag, by matching the flag's
-- recorded WezTerm pane id to a live pane. Powers Alt+G — the cross-workspace
-- analogue of clicking an on-screen amber tab. Pane id is reliable even when a
-- pane's reported cwd (OSC-7) is stale. Reads fresh so it works before tick 1.
local function attention_target()
  local pend = read_attention(os.time())
  if not pend[1] then return nil end
  local want = {}
  for _, fl in ipairs(pend) do if fl.pane then want[fl.pane] = true end end
  for _, mw in ipairs(wezterm.mux.all_windows()) do
    local wsname = mw:get_workspace()
    for _, tab in ipairs(mw:tabs()) do
      for _, p in ipairs(tab:panes()) do
        if want[p:pane_id()] then return wsname, tab end
      end
    end
  end
  return nil
end

-- Map A.tab_style's semantic fg tokens to colours, plus the constant tab bg.
local TAB_BG = '#181825'
local TAB_FG = { focus = ACCENT_HI, attn = ATTN, running = RUNNING, idle = IDLE }

-- A program running in a pane (notably Claude Code) bakes a decorative brand/
-- attention glyph into its OSC window title — e.g. the ✳ sparkle. When a tab has
-- no explicit title (Alt+T spawns, or the brief pre-set_title window on restore)
-- format-tab-title falls back to that pane title, so the glyph leaks into the tab
-- bar and reads like a SECOND, competing notification marker. Attention is ours
-- to signal (the amber ⬤), so strip any leading run of these markers + spaces.
-- Plain anchored compares (not a byte-class) so multibyte glyphs match cleanly.
-- NOTE: \u{FE0F} (emoji variation selector-16) is listed so an emoji-style
-- "✳️" (U+2733 U+FE0F) is fully consumed — stripping only the 2733 would leave
-- the invisible 3-byte FE0F as the new leading "char", which display_name's
-- byte-wise capitalize then mangles into mojibake.
local TITLE_MARKERS = {
  '\u{2733}', '\u{2734}', '\u{2731}', '\u{2732}', '\u{2736}', '\u{2737}',
  '\u{2726}', '\u{2605}', '\u{2606}', '\u{25CF}', '\u{2B24}', '\u{2022}', '*',
  '\u{2728}', '\u{273B}', '\u{273D}', '\u{2742}', '\u{2743}', '\u{2748}',
  '\u{2749}', '\u{274A}', '\u{274B}', '\u{FE0F}',
}
local function strip_title_markers(t)
  while true do
    t = t:match('^%s*(.-)%s*$') or t                 -- trim surrounding whitespace
    local hit = false
    for _, m in ipairs(TITLE_MARKERS) do
      if t:sub(1, #m) == m then t = t:sub(#m + 1); hit = true; break end
    end
    if not hit then return t end
  end
end

-- Repo display aliases + leaf-only naming. Both are PURELY cosmetic: they change
-- only what format-tab-title PAINTS. The tab's real title (tab:get_title()) stays
-- the full rel, so session save (the ':find("/")' sentinel), restore (which
-- rebuilds the cwd as REPO_DIR/<title>), workspaces[title] config lookup, and
-- pane-id notification/Alt+G targeting are all untouched — none of them read the
-- rendered text. Keys are the repo path RELATIVE to the repo root, forward-
-- slashed + lowercased. No entry => the leaf folder name (last path segment).
local REPO_ALIASES = {
  ['web/cashcow']         = 'Tarive',        -- legacy folder name; product rebranded to Tarive (web app)
  ['web/tarive']          = 'Tarive (app)',  -- the Expo mobile app — disambiguated from the web tab above
  ['stock/research 2026'] = 'Crucible',      -- algo-trading paper-gate project (#37); folder predates the name
  ['life/second-brain']   = 'Cortex',        -- #31 second brain + Helm dashboard; product name = Cortex
}

-- ── Custom tab names (persistent) ───────────────────────────────────────────
-- A tab's identity stays its repo-relative path (so session-restore + attention
-- keep working); this map overlays a user-chosen DISPLAY label on top, keyed by
-- that same identity. The home tab is keyed by its title 'Nexus'. Persisted to
-- disk so a rename survives a restart, and loaded into memory ONCE —
-- format-tab-title reads it on every repaint, so it must never touch disk.
local TAB_NAMES_PATH = wezterm.home_dir .. '/.claude/workspaces/tab-names.json'
local tab_names = {}

local function load_tab_names()
  local f = io.open(TAB_NAMES_PATH, 'r')
  if not f then return end
  local raw = f:read('*a'); f:close()
  local ok, data = pcall(wezterm.json_parse, raw)
  if ok and type(data) == 'table' then tab_names = data end
end

local function save_tab_names()
  local f = io.open(TAB_NAMES_PATH, 'w')
  if f then f:write(wezterm.json_encode(tab_names)); f:close() end
end

load_tab_names()

-- Cosmetic tab label for a repo identity `rel`. Alias wins (brand names shown
-- verbatim); otherwise the leaf folder name with its first letter capitalized,
-- so every tab reads uniformly Title-cased regardless of the folder's own casing:
--   'web/cashcow'  -> 'Tarive'    (alias hit, verbatim)
--   'Life/vantage' -> 'Vantage'   (leaf, first letter capitalized)
--   'Nexus'        -> 'Nexus'     (no slash: leaf is the whole thing)
local function display_name(rel)
  if not rel or rel == '' then return rel end
  local key   = rel:gsub('\\', '/'):lower()
  local alias = REPO_ALIASES[key]
  if alias then return alias end
  local leaf = rel:match('[^/\\]+$') or rel
  -- Capitalize ONLY a leading ASCII letter. If the first byte is non-ASCII (a
  -- marker glyph that slipped past strip_title_markers, or a multibyte head),
  -- pass it through untouched — byte-slicing :upper() on a multibyte head
  -- produces mojibake, which is exactly the "title-capping gets messed up" bug.
  if leaf:sub(1, 1):match('%a') then
    return leaf:sub(1, 1):upper() .. leaf:sub(2)
  end
  return leaf
end

-- Pick the tab's display source from data WE control — never the program's
-- decorative OSC title (Claude Code's "✳ <activity>"). Priority:
--   1. tab.tab_title — the repo rel path we set via tab:set_title (source of truth)
--   2. the active pane's cwd, mapped repo-relative — survives an empty tab title
--      (Alt+T spawns, the brief pre-set_title window on restore) without ever
--      surfacing the program's title or its sparkle glyph
--   3. last resort: the OSC pane title, with leading marker glyphs stripped
local function tab_label_src(tab)
  if tab.tab_title and tab.tab_title ~= '' then return tab.tab_title end
  local u = tab.active_pane and tab.active_pane.current_working_dir
  if u then
    local p = (u.file_path or tostring(u)):gsub('\\', '/')
    if p:match('^/[A-Za-z]:') then p = p:sub(2) end
    p = p:gsub('/+$', '')
    -- The repo ROOT itself is "Nexus", not its path leaf ("repo"). Honor the same
    -- alias chip_label/gui-startup use, so a root tab with no explicit title reads
    -- "Nexus" instead of the literal folder name.
    if REPO_DIR_NORM ~= '' and p:lower() == REPO_DIR_NORM then return 'Nexus' end
    if REPO_DIR_NORM ~= '' and p:lower():sub(1, #REPO_DIR_NORM + 1) == REPO_DIR_NORM .. '/' then
      return p:sub(#REPO_DIR_NORM + 2)            -- repo-relative, e.g. web/cashcow
    end
    local leaf = p:match('[^/]+$')
    if leaf and leaf ~= '' then return leaf end
  end
  return strip_title_markers(tab.active_pane.title or '')
end

wezterm.on('format-tab-title', function(tab, _tabs, _panes, _conf, _hover, _max_width)
  -- A user-set custom label (Alt+R) wins over the derived repo name. Keyed by the
  -- tab's identity (repo-rel path, or 'Nexus' for home) so it survives restore.
  local src   = tab_label_src(tab)
  local title = tab_names[src] or display_name(src)
  local idx   = tostring(tab.tab_index + 1)

  -- flagged_tabs is keyed by tab id (matched by pane id in update-status), so
  -- it's immune to stale OSC-7 cwd. A.tab_style picks the look — and keeps the
  -- BACKGROUND constant in every state, so focusing or clearing a flag never
  -- flips the bg (no flicker). Attention = an amber ⬤ + amber title; focusing a
  -- flagged tab only swaps the title colour to the accent, dot and bg unchanged.
  local flagged = flagged_tabs[tab.tab_id] ~= nil
  local st      = A.tab_style(tab.is_active, flagged, tab.active_pane.has_unseen_output)

  -- Dim tabs with no live Claude session so agent tabs stand out. A flagged tab
  -- (amber ⬤ — agent finished / needs you) is NEVER dimmed even if its process
  -- already exited: attention has to stay loud. Otherwise no Claude → low-contrast
  -- grey, with a softer focused tone so the current tab is still findable.
  local has_claude = claude_tabs[tab.tab_id] == true
  local title_fg, title_bold
  if flagged or has_claude then
    title_fg, title_bold = TAB_FG[st.fg], st.bold
  else
    title_fg, title_bold = (tab.is_active and NOCLAUDE_HI or NOCLAUDE), false
  end

  local cells = { { Background = { Color = TAB_BG } } }
  if st.dot then
    cells[#cells + 1] = { Foreground = { Color = ATTN } }
    cells[#cells + 1] = { Attribute  = { Intensity = 'Bold' } }
    cells[#cells + 1] = { Text = ' ⬤ ' }
    cells[#cells + 1] = { Foreground = { Color = title_fg } }
    cells[#cells + 1] = { Attribute  = { Intensity = title_bold and 'Bold' or 'Normal' } }
    cells[#cells + 1] = { Text = idx .. ':' .. title .. ' ' }
  else
    cells[#cells + 1] = { Foreground = { Color = title_fg } }
    cells[#cells + 1] = { Attribute  = { Intensity = title_bold and 'Bold' or 'Normal' } }
    cells[#cells + 1] = { Text = '  ' .. idx .. ':' .. title .. ' ' }
  end
  return cells
end)

-- ── Status bar ────────────────────────────────────────────────────────────────
-- Forward declaration: save_session is defined later in the file, but
-- update-status needs to call it. Lua closures capture the variable binding,
-- so by the time the event fires (runtime) the assignment will have happened.
local save_session
local _last_session_save  = 0
local _cached_agent_task  = ""
local _reload_notice_at   = 0   -- os.time() of last config reload; drives the short-lived status pill
local RELOAD_NOTICE_SECS  = 3   -- how long the "✓ reloaded" pill lingers in the status bar

-- Build the left-status cells for a workspace name. Factored out so the Alt+N
-- rename handler can repaint it IMMEDIATELY with the new name instead of waiting
-- up to one status_update_interval for the next tick — that wait is the source of
-- the post-rename name flicker. 'nexus' is aliased to 'home' (display only).
local function left_status_cells(ws, dim)
  local cells = {}
  -- Show the workspace name ONLY when you've left the home workspace. On home it's
  -- noise (everything lives here as tabs); off-home it doubles as a "you're not in
  -- Nexus" signal so a stray workspace switch is immediately obvious. `dim` softens
  -- the chip to the no-Claude grey when no tab in the workspace has a live session.
  local has_chip = ws ~= 'nexus'
  if has_chip then
    cells[#cells + 1] = { Foreground = { Color = dim and NOCLAUDE_HI or ACCENT } }
    cells[#cells + 1] = { Attribute  = { Intensity = dim and 'Normal' or 'Bold' } }
    cells[#cells + 1] = { Text = '  ⬡ ' .. ws .. '  ' }
  end
  if _cached_agent_task ~= "" then
    cells[#cells + 1] = { Foreground = { Color = '#585b70' } }
    cells[#cells + 1] = { Attribute  = { Intensity = 'Normal' } }
    cells[#cells + 1] = { Text = (has_chip and '\n  · ' or '  · ') .. _cached_agent_task:sub(1, 60) .. '  ' }
  end
  return cells
end

wezterm.on('update-status', function(window, pane)
  local ws  = window:active_workspace()
  local now = os.time()

  -- The focused TAB drives the dwell-clear timer.
  local at            = window:active_tab()
  local active_tab_id = at and at:tab_id() or nil
  if active_tab_id ~= _attn_active_tab then
    _attn_active_tab, _attn_active_since = active_tab_id, now
  end

  -- Map every live pane id -> its tab id, across all workspaces. The SAME sweep
  -- records which tabs have a live Claude session (any pane), throttled to
  -- CLAUDE_SCAN_SECS since a per-pane foreground-process lookup isn't free at 4
  -- ticks/s. format-tab-title reads claude_tabs to dim the ones without.
  local pane_tab       = {}
  local do_claude_scan = (now - _claude_scan_at >= CLAUDE_SCAN_SECS)
  local claude_seen    = do_claude_scan and {} or nil
  local scan_tabs      = do_claude_scan and {} or nil
  for _, mw in ipairs(wezterm.mux.all_windows()) do
    for _, t in ipairs(mw:tabs()) do
      local tid = t:tab_id()
      if do_claude_scan then scan_tabs[#scan_tabs + 1] = t end
      for _, p in ipairs(t:panes()) do
        pane_tab[p:pane_id()] = tid
        if do_claude_scan and not claude_seen[tid] then
          local proc = p:get_foreground_process_name() or ''
          if proc:lower():find('claude') then claude_seen[tid] = true end
        end
      end
    end
  end
  if do_claude_scan then
    -- Force a repaint for any tab whose Claude presence flipped — WezTerm caches
    -- tab titles and won't re-run format-tab-title for an idle tab on its own, so
    -- the dim/brighten would otherwise lag until the next interaction (cf. the
    -- attention dwell-clear nudge below).
    for _, t in ipairs(scan_tabs) do
      local tid = t:tab_id()
      if (claude_seen[tid] == true) ~= (claude_tabs[tid] == true) then
        t:set_title(t:get_title())
      end
    end
    _claude_scan_at = now
    claude_tabs     = claude_seen
  end

  -- Cross-tab attention — all rules live in the tested module A.decide(); here we
  -- only feed it live state and apply its verdict (delete files, repaint tabs).
  local res = A.decide(read_attention(now), {
    pane_to_tab   = pane_tab,
    active_tab_id = active_tab_id,
    active_since  = _attn_active_since,
    now           = now,
    dwell_secs    = ATTN_DWELL_SECS,
    max_age       = ATTN_MAX_AGE,
    repo_dir_norm = REPO_DIR_NORM,
  })
  for _, path in ipairs(res.remove) do os.remove(path) end
  for k in pairs(flagged_tabs) do flagged_tabs[k] = nil end
  for tid, label in pairs(res.flagged_tabs) do flagged_tabs[tid] = label end

  -- A dwell-clear deletes the flag in memory, but WezTerm caches each tab's
  -- rendered title and won't re-run format-tab-title for an idle focused tab —
  -- so the just-cleared amber dot would linger until the next tab switch forces
  -- a redraw. Re-setting the active tab's title to itself marks it dirty and
  -- forces the repaint in place. Guard on res.remove so we only nudge on the
  -- tick a flag actually cleared (the dwell-clear path only removes flags on the
  -- active tab, so the active tab is exactly the one that needs the repaint).
  if #res.remove > 0 and at then at:set_title(at:get_title()) end

  -- Left: just the workspace name + active agent task. Attention is already
  -- signalled per-tab in the tab bar (amber ⬤), so the left status does NOT
  -- duplicate it — no name chips, and the label keeps its normal colour.
  -- Built by left_status_cells() (shared with the Alt+N rename handler); the
  -- home workspace keeps the internal id 'nexus' but READS as "home". The chip
  -- dims when no tab in the active workspace has a live Claude session.
  local ws_has_claude = false
  for _, t in ipairs(window:mux_window():tabs()) do
    if claude_tabs[t:tab_id()] then ws_has_claude = true; break end
  end
  window:set_left_status(wezterm.format(left_status_cells(ws, not ws_has_claude)))

  -- Right: show directional split hint when split_dir key table is active
  if window:active_key_table() == 'split_dir' then
    window:set_right_status(wezterm.format {
      { Foreground = { Color = '#f9e2af' } },
      { Attribute = { Intensity = 'Bold'   } },
      { Text = '  split →D  ←A  ↓S  ↑W   esc cancel  ' },
    })
  else
    -- Short-lived "reloaded" pill: shown for RELOAD_NOTICE_SECS after a config
    -- reload, then it vanishes on its own as update-status keeps repainting.
    local right = {}
    if os.time() - _reload_notice_at <= RELOAD_NOTICE_SECS then
      right[#right+1] = { Foreground = { Color = ACCENT } }
      right[#right+1] = { Attribute  = { Intensity = 'Bold' } }
      right[#right+1] = { Text = '✓ reloaded   ' }
      right[#right+1] = { Attribute  = { Intensity = 'Normal' } }
    end
    right[#right+1] = { Foreground = { Color = '#585b70' } }
    right[#right+1] = { Text = os.date('%H:%M') .. '   Alt+/  keys  ' }
    window:set_right_status(wezterm.format(right))
  end

  -- Periodic session save (every 30 s) so the active tab is always current.
  -- window-focus-changed only fires on OS-level focus loss, not tab switches.
  if save_session and now - _last_session_save >= 30 then
    _last_session_save = now
    save_session(window)
  end
end)

-- ── Repos config (load/save) — declared early; used by save_session + make_tab ─
local REPOS_CFG_PATH    = wezterm.home_dir .. '/.claude/repos.json'
local REPOS_MAX_RECENTS = 10

local function load_repos_cfg()
  local f = io.open(REPOS_CFG_PATH, 'r')
  if not f then return { favorites = {}, recents = {}, workspaces = {} } end
  local raw = f:read('*a'); f:close()
  local ok, data = pcall(wezterm.json_parse, raw)
  if not ok or type(data) ~= 'table' then return { favorites = {}, recents = {}, workspaces = {} } end
  return {
    favorites  = data.favorites  or {},
    recents    = data.recents    or {},
    workspaces = data.workspaces or {},
  }
end

local function save_repos_cfg(cfg)
  local function arr(t)
    local parts = {}
    for _, v in ipairs(t) do parts[#parts+1] = '"' .. v:gsub('"', '\\"') .. '"' end
    return '[' .. table.concat(parts, ',') .. ']'
  end
  local function ws_json(ws)
    local kv = {}
    for k, v in pairs(ws) do
      local fields = {}
      if v.left  then fields[#fields+1] = '"left":"'  .. v.left:gsub('"', '\\"')  .. '"' end
      if v.right then fields[#fields+1] = '"right":"' .. v.right:gsub('"', '\\"') .. '"' end
      kv[#kv+1] = '"' .. k:gsub('"', '\\"') .. '":{' .. table.concat(fields, ',') .. '}'
    end
    return '{' .. table.concat(kv, ',') .. '}'
  end
  local f = io.open(REPOS_CFG_PATH, 'w')
  if f then
    f:write('{"favorites":' .. arr(cfg.favorites) ..
            ',"recents":'   .. arr(cfg.recents)   ..
            ',"workspaces":' .. ws_json(cfg.workspaces or {}) .. '}\n')
    f:close()
  end
end

-- ── Session persistence ───────────────────────────────────────────────────────
local SESSION_PATH  = wezterm.home_dir .. '/.claude/session.json'
local SESSION_MAX_H = 12
-- Command used to re-launch a detected Claude session on restore. --permission-mode
-- auto starts it in Auto mode (the classifier-driven mode, distinct from acceptEdits)
-- so restored agents don't sit in the normal ask-everything mode. Stored verbatim in
-- repos.json by save_session; any older 'claude --continue' value is rewritten to this
-- on the next save (so repos.json already holds the auto form by the next restart).
local CLAUDE_RESTORE_CMD = 'claude --continue --permission-mode auto'

save_session = function(window)
  local cfg     = load_repos_cfg()
  local changed = false
  local parts   = {}

  for _, tab in ipairs(window:mux_window():tabs()) do
    local title = tab:get_title()
    if not title:find('/') then goto continue end  -- skip Nexus/shell-named tabs
    parts[#parts + 1] = '"' .. title:gsub('"', '\\"') .. '"'

    -- panes_with_info gives position data needed for layout detection.
    local pinfo = tab:panes_with_info()

    -- Auto-detect Claude running in the leftmost/topmost pane.
    if pinfo[1] then
      local proc = pinfo[1].pane:get_foreground_process_name() or ''
      if proc:lower():find('claude') then
        cfg.workspaces[title] = cfg.workspaces[title] or {}
        if cfg.workspaces[title].left ~= CLAUDE_RESTORE_CMD then
          cfg.workspaces[title].left = CLAUDE_RESTORE_CMD
          changed = true
        end
      end
    end

    -- Detect split direction from pane positions: if pane 2 is below pane 1
    -- it's a top/bottom split (Down); otherwise side-by-side (Right).
    if pinfo[2] then
      local dir = (pinfo[2].top > pinfo[1].top) and 'Down' or 'Right'
      cfg.workspaces[title] = cfg.workspaces[title] or {}
      if cfg.workspaces[title].split_direction ~= dir then
        cfg.workspaces[title].split_direction = dir
        changed = true
      end
    end
    ::continue::
  end

  -- Record which tab was active so restore can refocus it
  local active_title = ''
  local at = window:mux_window():active_tab()
  if at then active_title = at:get_title():gsub('"', '\\"') end

  local f = io.open(SESSION_PATH, 'w')
  if f then
    f:write('{"tabs":[' .. table.concat(parts, ',') ..
            '],"activeTab":"' .. active_title ..
            '","savedAt":'    .. tostring(os.time()) .. '}\n')
    f:close()
  end
  -- Only flush repos.json when something actually changed
  if changed then save_repos_cfg(cfg) end
end

local function load_session()
  local empty = { tabs = {}, activeTab = '' }
  local f = io.open(SESSION_PATH, 'r')
  if not f then return empty end
  local raw = f:read('*a'); f:close()
  local ok, data = pcall(wezterm.json_parse, raw)
  if not ok or type(data) ~= 'table' then return empty end
  if (os.time() - (data.savedAt or 0)) / 3600 > SESSION_MAX_H then return empty end
  return { tabs = data.tabs or {}, activeTab = data.activeTab or '' }
end

-- ── Nexus sync: write active workspace on focus / tab change ─────────────────
-- _cached_agent_task is declared at the top of the file (before update-status).
-- write_active updates it here on focus change, keeping update-status disk-free.
local function write_active(window, pane)
  if not window:is_focused() then return end
  local workspace = window:active_workspace()
  local cwd_obj   = pane:get_current_working_dir()
  local cwd       = cwd_obj and cwd_obj.file_path or ''
  if cwd:match('^/[A-Za-z]:') then cwd = cwd:sub(2) end
  cwd = cwd:gsub('\\', '/')

  -- Resolve git branch for the current working directory.
  local branch = ""
  local ok, stdout = wezterm.run_child_process({
    'git', '-C', cwd:gsub('/', '\\'), 'branch', '--show-current',
  })
  if ok then branch = stdout:match('^%s*(.-)%s*$') or "" end

  -- Read helm-status.json — only show if written within the last 2 hours.
  -- Stale entries from completed agent sessions are silently suppressed.
  local status_file = cwd:gsub('/$', '') .. '/helm-status.json'
  local sf = io.open(status_file, 'r')
  _cached_agent_task = ""
  if sf then
    local raw = sf:read('*a'); sf:close()
    local task    = raw:match('"currentTask"%s*:%s*"([^"]*)"')
    local updated = raw:match('"updatedAt"%s*:%s*"([^"]*)"')
    if task and updated then
      local y, mo, d, h, m = updated:match('(%d+)-(%d+)-(%d+)T(%d+):(%d+)')
      if y then
        local age = os.time() - os.time({
          year = tonumber(y), month = tonumber(mo), day = tonumber(d),
          hour = tonumber(h), min  = tonumber(m),   sec = 0,
          isdst = false,
        })
        if age < 7200 then _cached_agent_task = task end
      end
    end
  end

  local path = wezterm.home_dir .. '/.claude/workspaces/active.json'
  local f = io.open(path, 'w')
  if f then
    f:write(string.format(
      '{"workspace":"%s","cwd":"%s","branch":"%s","updatedAt":"%s"}\n',
      workspace:gsub('"', '\\"'),
      cwd:gsub('"', '\\"'),
      branch:gsub('"', '\\"'),
      os.date('!%Y-%m-%dT%H:%M:%SZ')
    ))
    f:close()
  end

  save_session(window)
end

-- ── Default startup layout ────────────────────────────────────────────────────
-- Tab 1: persistent keys reference (always visible on launch)
-- Tab 2: shell in the repo root (main working directory)
-- config.maximized is not valid in this WezTerm build; gui-startup is the
-- correct hook for window-state setup.
local keymap_file = wezterm.home_dir .. '/.claude/keymap.txt'

-- Repo root is machine-specific, so it is NOT committed. It comes from a
-- gitignored terminal.local.lua (`return { repo_root = '...' }`) or the
-- CLAUDE_REPO_ROOT env var, falling back to ~/repo. See terminal.local.example.lua.
local function load_local_cfg()
  local ok, t = pcall(dofile, wezterm.home_dir .. '/.claude/terminal.local.lua')
  if ok and type(t) == 'table' then return t end
  return {}
end
local LOCAL       = load_local_cfg()
local REPO_DIR    = LOCAL.repo_root or os.getenv('CLAUDE_REPO_ROOT') or (wezterm.home_dir .. '/repo')
local REPO_DIR_BS = REPO_DIR:gsub('/', '\\')
REPO_DIR_NORM     = norm_path(REPO_DIR)   -- forward-declared by the attention block; labels the home flag "Nexus"

-- Path of `p` relative to REPO_DIR (slash-agnostic, case-insensitive on the
-- drive letter), or nil if `p` is not under the repo root.
local function rel_under_repo(p)
  local norm = p:gsub('\\', '/')
  if norm:lower():sub(1, #REPO_DIR + 1) == REPO_DIR:lower() .. '/' then
    return norm:sub(#REPO_DIR + 2)
  end
  return nil
end

-- Right-pane width, shared by the Nexus home tab and every repo tab so the
-- layout is consistent. WezTerm sizes the NEW (right) pane as this fraction of
-- the pane being split; the ratio is preserved across later window resizes.
local RIGHT_PANE_FRAC = 0.40

-- Nexus keymap pane only. WezTerm panes are RATIO-preserving across resizes, so
-- to guarantee every keymap row stays on ONE line down to a half-monitor window
-- we can't pin a cell count — we derive the fraction at startup from the live
-- full-screen column width (see gui-startup) so the pane is >= this many cells
-- when the window is half-screen. Longest keymap row is ~28 cells; +margin.
local KEYMAP_TARGET_CELLS = 32

local function keymap_args()
  if wezterm.target_triple:find('windows') then
    local f = keymap_file:gsub('/', '\\')
    -- ESC[2J = erase screen, ESC[H = cursor home (row 1 col 1).
    -- More reliable than Clear-Host in non-interactive pane contexts.
    return {
      'powershell.exe', '-NoProfile', '-NoLogo', '-NonInteractive', '-Command',
      -- Poll window dimensions every 500ms; redraw only when they change.
      -- This handles all resize events (split, zoom, window drag) without
      -- relying on SIGWINCH, which PowerShell on Windows does not expose.
      '[Console]::OutputEncoding=[Text.Encoding]::UTF8; ' ..
      '$e=[char]27; $lh=0; $lw=0; ' ..
      'while ($true) { ' ..
        '$h=[Console]::WindowHeight; $w=[Console]::WindowWidth; ' ..
        'if ($h -ne $lh -or $w -ne $lw) { ' ..
          '$lh=$h; $lw=$w; ' ..
          'Write-Host "${e}[3J${e}[2J${e}[H" -NoNewline; ' ..
          'Get-Content "' .. f .. '" -Encoding UTF8 ' ..
        '}; ' ..
        'Start-Sleep -Milliseconds 500 ' ..
      '}',
    }
  end
  -- SIGWINCH fires on every terminal resize; trap redraws immediately.
  return { 'bash', '-c',
    'f="' .. keymap_file .. '"; ' ..
    'draw() { printf "\\033[3J\\033[2J\\033[H"; cat "$f"; }; ' ..
    'trap draw WINCH; draw; ' ..
    'while true; do sleep 86400; done' }
end

-- ── Shared helper: create a repo tab (NO keymap — that's Nexus-only) ─────────
-- Left pane (60%): shell, or saved command (e.g. "claude --continue").
--   Wrapped in PS so a shell prompt survives after the command exits.
-- Right pane (40%): shell, or saved service command (e.g. "pnpm dev").
local function make_tab(mux_win, title, cwd)
  local ws  = (load_repos_cfg().workspaces or {})[title] or {}

  -- Left pane: use -NoExit so the same PS session becomes the interactive shell
  -- once the restore command exits. Avoids the nested-PS TUI issue where
  -- -Command "...; child_ps" breaks interactive apps like Claude Code.
  local left_args
  if ws.left and ws.left ~= '' then
    local safe = cwd:gsub("'", "''")
    left_args = {
      'powershell.exe', '-NoProfile', '-NoLogo', '-NoExit', '-Command',
      "Set-Location '" .. safe .. "'; " .. ws.left,
    }
  end

  -- Right pane: run service/tool directly (no wrapper needed)
  local right_args
  if ws.right and ws.right ~= '' then
    local parts = {}
    for p in ws.right:gmatch('%S+') do parts[#parts+1] = p end
    right_args = parts
  end

  local split_dir = ws.split_direction or 'Right'
  local spawn_cfg = left_args and { cwd = cwd, args = left_args } or { cwd = cwd }
  local tab = mux_win:spawn_tab(spawn_cfg)
  if not tab then return nil end
  tab:set_title(title)
  local left_pane = tab:active_pane()
  left_pane:split { direction = split_dir, size = RIGHT_PANE_FRAC, args = right_args, cwd = cwd }
  left_pane:activate()
  return tab
end

wezterm.on('gui-startup', function(cmd)
  if cmd then
    local _, _, window = wezterm.mux.spawn_window(cmd)
    window:gui_window():maximize()
    return
  end

  -- Create the Nexus home tab (workspace name matches config.default_workspace)
  local _, shell_pane, window = wezterm.mux.spawn_window({
    workspace = 'nexus',
    cwd       = REPO_DIR,
  })
  -- Maximize BEFORE splitting so the split fraction is computed against the
  -- full-screen cell grid rather than the small initial spawn size. Splitting
  -- first could leave the right pane proportionally squeezed.
  window:gui_window():maximize()
  window:active_tab():set_title('Nexus')
  -- Half-screen-safe keymap width: measure the now-maximized full-screen column
  -- count from the single un-split pane, then size the split so the keymap pane
  -- is >= KEYMAP_TARGET_CELLS even when the window is later snapped to HALF the
  -- monitor (frac * full_cols/2 >= TARGET). Ratio is preserved on resize, so at
  -- full screen it's ~2x that (wider, but never wraps). Clamped, with a fallback
  -- if the width reads 0 (e.g. maximize hasn't settled).
  local full_cols = (window:active_tab():panes_with_info()[1] or {}).width or 0
  local keymap_frac = 0.32
  if full_cols > 0 then
    keymap_frac = math.max(0.12, math.min(0.45, (KEYMAP_TARGET_CELLS * 2) / full_cols))
  end
  shell_pane:split { direction = 'Right', size = keymap_frac, args = keymap_args(), cwd = REPO_DIR }
  shell_pane:activate()

  -- Restore previously open repo tabs (if session is < 12 h old).
  -- Capture the tab object that matches activeTab so we can activate it directly
  -- (avoids a post-loop title lookup that can race with WezTerm's async title init).
  local session       = load_session()
  local active_tab_ref = nil
  for _, title in ipairs(session.tabs) do
    if not title:match('^~/') then
      local tab = make_tab(window, title, REPO_DIR .. '/' .. title)
      if tab and title == session.activeTab then
        active_tab_ref = tab
      end
    end
  end

  -- Focus the saved active tab, or Nexus if none matched.
  if active_tab_ref then
    active_tab_ref:activate()
  else
    window:tabs()[1]:activate()
  end
  window:gui_window():maximize()
end)

wezterm.on('window-focus-changed', write_active)
wezterm.on('window-activated',     write_active)

-- Save session on close so Claude process detection is captured even if the
-- user closes WezTerm without switching away first (avoiding the race where
-- window-focus-changed fires too late during the shutdown sequence).
wezterm.on('window-close-requested', function(window)
  save_session(window)
  window:close()
end)

-- Toast on config reload — but NOT on the initial startup load.
-- wezterm.GLOBAL persists across config reloads within a session and resets
-- on WezTerm exit, so the first event after each cold start is always silent.
wezterm.on('window-config-reloaded', function(_window, _pane)
  if not wezterm.GLOBAL.nexus_boot_done then
    wezterm.GLOBAL.nexus_boot_done = true
    return
  end
  -- Stamp the reload time; update-status renders a short-lived pill (no toast).
  _reload_notice_at = os.time()
end)

-- ── Help: jump to Nexus tab (always tab 0, always has the keymap pane) ───────

-- ── Repo launcher ─────────────────────────────────────────────────────────────
-- Alt+O: fuzzy picker over all git repos under the repo root.
-- Favorites (★) are pinned to the top; recently opened repos come next;
-- everything else is below but still fuzzy-searchable.
-- Alt+P: toggle-pin the current workspace's repo as a favorite.

local function path_to_ws_name(rel)
  return rel:lower()
    :gsub('[/\\%s]+', '-')
    :gsub('[^a-z0-9%-]', '')
    :gsub('%-+', '-')
    :gsub('^%-+', '')
    :gsub('%-+$', '')
end

local function discover_repos()
  -- Pruned breadth-first walk over a manual stack. Records any directory that
  -- has a .git child (and keeps descending, so nested repos are still found),
  -- but never descends into node_modules / .git internals / build output. The
  -- old `Get-ChildItem -Recurse -Depth 4` walked ~24k dirs (mostly
  -- node_modules) on EVERY Alt+O — ~400ms of the ~500ms latency. Pruning at the
  -- directory door cuts the walk to ~150ms and returns the identical repo set.
  -- 'example[s]' is pruned by segment name to match the old regex exclusion.
  local ps =
    "$r='" .. REPO_DIR_BS .. "';$md=4;" ..
    "$p=@{'node_modules'=1;'.git'=1;'dist'=1;'.next'=1;'build'=1;'out'=1;" ..
    "'.worktrees'=1;'archive'=1;'_Misc'=1;'example'=1;'examples'=1;'.venv'=1;" ..
    "'venv'=1;'__pycache__'=1;'target'=1;'obj'=1;'.turbo'=1;'.cache'=1};" ..
    "$o=New-Object System.Collections.Generic.List[string];" ..
    "$s=New-Object System.Collections.Generic.Stack[object];" ..
    "$s.Push(@{P=$r;D=0});" ..
    "while($s.Count){$c=$s.Pop();" ..
    "if(Test-Path (Join-Path $c.P '.git')){$o.Add($c.P)};" ..
    "if($c.D -ge $md){continue};" ..
    "try{foreach($d in [System.IO.Directory]::EnumerateDirectories($c.P)){" ..
    "$n=[System.IO.Path]::GetFileName($d);" ..
    "if($p.ContainsKey($n)){continue};$s.Push(@{P=$d;D=$c.D+1})}}catch{}};" ..
    "$o|Sort-Object -Unique"
  local ok, stdout = wezterm.run_child_process({
    'powershell.exe', '-NoProfile', '-NoLogo', '-NonInteractive', '-Command', ps,
  })
  if not ok then return {} end
  local repos = {}
  for line in stdout:gmatch('[^\r\n]+') do
    line = line:match('^%s*(.-)%s*$')
    if line ~= '' then
      local rel = rel_under_repo(line) or line:gsub('\\', '/')
      table.insert(repos, { path = line, rel = rel, ws = path_to_ws_name(rel) })
    end
  end
  return repos
end

local function sorted_choices(repos, cfg)
  local fav_idx, rec_idx, freq = {}, {}, cfg.frequency or {}
  for i, r in ipairs(cfg.favorites) do fav_idx[r] = i end
  for i, r in ipairs(cfg.recents)   do rec_idx[r] = i end

  -- Sort: favorites first (by pin order), then frequency desc, then recency, then alpha.
  table.sort(repos, function(a, b)
    local af = fav_idx[a.rel] or math.huge
    local bf = fav_idx[b.rel] or math.huge
    if af ~= bf then return af < bf end
    local afreq = freq[a.rel] or 0
    local bfreq = freq[b.rel] or 0
    if afreq ~= bfreq then return afreq > bfreq end
    local ar = rec_idx[a.rel] or math.huge
    local br = rec_idx[b.rel] or math.huge
    if ar ~= br then return ar < br end
    return a.rel < b.rel
  end)

  local choices = {}
  -- Extras (paths outside the repo root) pinned above favorites with ~ prefix
  for _, e in ipairs(cfg.extras or {}) do
    table.insert(choices, { id = e.path, label = '~ ' .. e.label })
  end
  for _, r in ipairs(repos) do
    local prefix = fav_idx[r.rel] and '\u{2605} ' or (rec_idx[r.rel] and '  ' or '  ')
    table.insert(choices, { id = r.path, label = prefix .. r.rel })
  end
  return choices
end

local function record_open(rel)
  local cfg = load_repos_cfg()
  -- Update recents (most recent first, capped at REPOS_MAX_RECENTS)
  local next_rec = { rel }
  for _, r in ipairs(cfg.recents) do
    if r ~= rel and #next_rec < REPOS_MAX_RECENTS then next_rec[#next_rec+1] = r end
  end
  cfg.recents = next_rec
  -- Increment open frequency counter
  cfg.frequency = cfg.frequency or {}
  cfg.frequency[rel] = (cfg.frequency[rel] or 0) + 1
  save_repos_cfg(cfg)
end

local function launch_repo(win, pane, repo)
  record_open(repo.rel)
  make_tab(win:mux_window(), repo.rel, repo.path)
end

-- ── Keybindings ───────────────────────────────────────────────────────────────
--
--  Nominal usage: 1–3 horizontal panes per tab, 1–3 tabs per workspace.
--
--  PANE NAV   A=left  D=right
--  TAB NAV    W=prev  S=next   ⇧W/⇧S=move tab   R=rename tab
--  PANE OPS   Z=zoom  X=close  C=split-H  V=split-V  T=new-tab
--  WORKSPACES F=fuzzy  N=rename-ws  [/]=cycle  G=jump-to-alert  (O=repo launcher)
--  HELP       /=keymap pane
--
-- Alt+B activates this table; press one of WASD to split in that direction.
-- one_shot = true means it auto-pops after one keypress (or after timeout).
config.key_tables = {
  split_dir = {
    { key = 'd', action = act.SplitPane { direction = 'Right' } },
    { key = 'a', action = act.SplitPane { direction = 'Left'  } },
    { key = 's', action = act.SplitPane { direction = 'Down'  } },
    { key = 'w', action = act.SplitPane { direction = 'Up'    } },
    { key = 'Escape', action = act.PopKeyTable },
  },
}

config.keys = {

  -- ── Pane navigation (cycle through all panes regardless of split axis) ──
  { key = 'a', mods = 'ALT', action = act.ActivatePaneDirection 'Prev' },
  { key = 'd', mods = 'ALT', action = act.ActivatePaneDirection 'Next' },

  -- ── Tab navigation (W=prev, S=next) ──────────────────────────────────
  { key = 'w', mods = 'ALT', action = act.ActivateTabRelative(-1) },
  { key = 's', mods = 'ALT', action = act.ActivateTabRelative(1)  },

  -- ── Move (reorder) the current tab: Shift + the same W/S nav keys ──────
  -- (WezTerm has no drag-to-reorder; this is the supported way.)
  { key = 'W', mods = 'ALT|SHIFT', action = act.MoveTabRelative(-1) },
  { key = 'S', mods = 'ALT|SHIFT', action = act.MoveTabRelative(1)  },

  -- ── Jump to tab by number ─────────────────────────────────────────────
  { key = '1', mods = 'ALT', action = act.ActivateTab(0) },
  { key = '2', mods = 'ALT', action = act.ActivateTab(1) },
  { key = '3', mods = 'ALT', action = act.ActivateTab(2) },
  { key = '4', mods = 'ALT', action = act.ActivateTab(3) },
  { key = '5', mods = 'ALT', action = act.ActivateTab(4) },

  -- ── Pane / tab operations ─────────────────────────────────────────────
  { key = 'z', mods = 'ALT', action = act.TogglePaneZoomState                    },
  { key = 'x', mods = 'ALT', action = act.CloseCurrentPane { confirm = true }    },
  { key = 'q', mods = 'ALT', action = act.CloseCurrentTab  { confirm = true }    },
  { key = 'c', mods = 'ALT', action = act.SplitPane { direction = 'Right' } },
  { key = 'e', mods = 'ALT', action = act.PaneSelect { mode = 'SwapWithActive' } },
  { key = 'b', mods = 'ALT', action = act.ActivateKeyTable {
      name = 'split_dir', one_shot = true, timeout_milliseconds = 8000 } },
  { key = 't', mods = 'ALT', action = act.SpawnTab 'CurrentPaneDomain'           },

  -- ── Workspace management ──────────────────────────────────────────────
  -- Alt+O: repo launcher — favorites first, then recents, then rest
  { key = 'o', mods = 'ALT',
    action = wezterm.action_callback(function(win, pane)
      local repos = discover_repos()
      if #repos == 0 then return end
      local cfg     = load_repos_cfg()
      local choices = sorted_choices(repos, cfg)
      win:perform_action(act.InputSelector {
        title  = '\u{2605} favorites  ·  recent  ·  all repos',
        choices = choices,
        fuzzy   = true,
        action  = wezterm.action_callback(function(w, p, id, label)
          if not id then return end
          -- Extras (outside the repo root) open directly; no recent tracking needed.
          if not rel_under_repo(id) then
            local title = label:match('^~%s+(.+)$') or label
            make_tab(w:mux_window(), title, id)
            return
          end
          local rel = label:match('^[%s\u{2605}]*(.+)$') or label
          launch_repo(w, p, { path = id, rel = rel, ws = path_to_ws_name(rel) })
        end),
      }, pane)
    end) },

  -- Alt+P: toggle-pin current repo as favorite
  { key = 'p', mods = 'ALT',
    action = wezterm.action_callback(function(win, pane)
      local cwd_obj = pane:get_current_working_dir()
      local cwd = cwd_obj and cwd_obj.file_path or ''
      if cwd:match('^/[A-Za-z]:') then cwd = cwd:sub(2) end
      cwd = cwd:gsub('\\', '/'):gsub('/$', '')
      local rel = rel_under_repo(cwd)
      if not rel then
        win:toast_notification('Nexus', 'Not inside ' .. REPO_DIR, nil, 1500)
        return
      end
      local cfg = load_repos_cfg()
      local found, new_favs = false, {}
      for _, r in ipairs(cfg.favorites) do
        if r == rel then found = true else new_favs[#new_favs+1] = r end
      end
      if found then
        cfg.favorites = new_favs
        win:toast_notification('Nexus', 'Unpinned  ' .. rel, nil, 1500)
      else
        table.insert(cfg.favorites, 1, rel)
        win:toast_notification('Nexus', '\u{2605} Pinned  ' .. rel, nil, 1500)
      end
      save_repos_cfg(cfg)
    end) },
  { key = 'f', mods = 'ALT',
    action = act.ShowLauncherArgs { flags = 'WORKSPACES|FUZZY' } },
  { key = 'n', mods = 'ALT',
    action = act.PromptInputLine {
      description = 'Name workspace:',
      action = wezterm.action_callback(function(win, pane, line)
        if line and line ~= '' then
          win:perform_action(act.RenameWorkspace { name = line }, pane)
          -- Repaint the workspace name NOW so it doesn't linger on the old name
          -- until the next update-status tick (the flicker). Paint `line` directly
          -- — the name we just set — rather than re-reading active_workspace(),
          -- which may not have committed the rename yet on this same frame.
          win:set_left_status(wezterm.format(left_status_cells(line)))
        end
      end),
    }},
  -- Alt+R: rename the CURRENT TAB (persistent; blank input resets to default).
  -- Stores a display override keyed by the tab's identity (its repo-rel path, or
  -- 'Nexus' for home) — the title itself is left intact so session-restore and
  -- attention keep working. Re-setting the title to itself forces an in-place
  -- repaint so the new label shows immediately.
  { key = 'r', mods = 'ALT',
    action = act.PromptInputLine {
      description = 'Rename tab (blank = reset):',
      action = wezterm.action_callback(function(win, _pane, line)
        if line == nil then return end          -- Esc cancels — leave as-is
        local tab = win:active_tab()
        if not tab then return end
        local key = tab:get_title()             -- repo-rel path, or 'Nexus' (home)
        if key == nil or key == '' then return end
        if line == '' then tab_names[key] = nil else tab_names[key] = line end
        save_tab_names()
        tab:set_title(tab:get_title())          -- mark dirty → repaint with new label
      end),
    }},

  { key = '[', mods = 'ALT', action = act.SwitchWorkspaceRelative(-1) },
  { key = ']', mods = 'ALT', action = act.SwitchWorkspaceRelative(1)  },

  -- Alt+G: jump to the workspace/tab whose agent is waiting on you (the cross-
  -- workspace analogue of clicking an on-screen amber tab).
  { key = 'g', mods = 'ALT',
    action = wezterm.action_callback(function(win, pane)
      local target_ws, target_tab = attention_target()
      if not target_ws then return end
      if target_tab then pcall(function() target_tab:activate() end) end
      win:perform_action(act.SwitchToWorkspace { name = target_ws }, pane)
    end) },

  -- ── Scrollback ────────────────────────────────────────────────────────
  { key = 'u', mods = 'ALT', action = act.ScrollByPage(-0.5) },
  { key = 'i', mods = 'ALT', action = act.ScrollByPage(0.5)  },

  -- ── Clipboard ─────────────────────────────────────────────────────────
  { key = 'C', mods = 'CTRL|SHIFT', action = act.CopyTo 'Clipboard'    },
  { key = 'V', mods = 'CTRL|SHIFT', action = act.PasteFrom 'Clipboard' },

  -- ── Help: jump to Nexus tab (tab 0) where the keymap pane lives ──────
  { key = '/', mods = 'ALT', action = act.ActivateTab(0) },
}

-- ── Scrollback / defaults ─────────────────────────────────────────────────────
-- ── Clickable links over TUIs (Claude Code etc.) ────────────────────────────
-- A full-screen TUI enables mouse reporting, so plain clicks are delivered to
-- the app and never reach WezTerm's link opener — which is why links looked
-- dead. mouse_reporting = true lets these fire anyway: Ctrl+Click opens the URL
-- / OSC-8 file link under the cursor, and the Ctrl press-down is swallowed so it
-- doesn't begin a text selection. (With no TUI running, the built-in Ctrl+Click
-- rule already handles it.)
config.mouse_bindings = {
  { event = { Down = { streak = 1, button = 'Left' } }, mods = 'CTRL',
    mouse_reporting = true, action = act.Nop },
  { event = { Up = { streak = 1, button = 'Left' } }, mods = 'CTRL',
    mouse_reporting = true, action = act.OpenLinkAtMouseCursor },
}

-- Make bare Windows file paths (e.g. D:\repo\foo.ts:12) clickable too, on top of
-- the built-in URL rules. The matched text is handed verbatim to open-uri below.
config.hyperlink_rules = wezterm.default_hyperlink_rules()
table.insert(config.hyperlink_rules, {
  regex  = [[[A-Za-z]:[\\/](?:[^\s"'<>|:*?]+[\\/])*[^\s"'<>|:*?]+\.[A-Za-z0-9]+(?::\d+(?::\d+)?)?]],
  format = '$0',
})

-- Route opened links: web/mail use the OS default (browser); anything that looks
-- like a local file opens in Cursor at its line via open-in-cursor.ps1 (which
-- also flips markdown into preview mode).
wezterm.on('open-uri', function(_window, _pane, uri)
  if not (uri:match('^file:') or uri:match('^/?%a:[/\\]')) then
    return  -- not a local file → let WezTerm open it (browser, etc.)
  end
  local target = uri:gsub('^file://', ''):gsub('^/([A-Za-z]:)', '%1')  -- file:///D:/x → D:/x
  wezterm.background_child_process({
    'powershell.exe', '-NoProfile', '-WindowStyle', 'Hidden', '-File',
    wezterm.home_dir .. '/.claude/scripts/open-in-cursor.ps1', '-Target', target,
  })
  return false  -- handled; don't let WezTerm try to open the raw path
end)

config.scrollback_lines  = 10000
config.default_workspace = 'nexus'
-- Repaint the status bar 4x/s instead of the 1s default so a workspace
-- switch/rename converges fast (backstop to the immediate repaint in Alt+N).
-- update-status only scans the small attention dir + in-memory mux state, so
-- the extra ticks are cheap.
config.status_update_interval = 250

return config
