local wezterm = require 'wezterm'
local config  = wezterm.config_builder()
local act     = wezterm.action

-- Platform switch. This config runs on both the Windows host it was written for
-- and macOS; everything that spawns a process or depends on path syntax branches
-- on IS_WIN, and everything else is identical on both.
local IS_WIN = (wezterm.target_triple:find('windows') ~= nil)
local SHELL  = os.getenv('SHELL') or '/bin/zsh'

-- Pure notification decision logic (unit-tested in tests/attention.test.lua).
-- terminal.lua does only the impure I/O; all the rules live in this module, so
-- the tested logic IS the runtime logic.
local A = dofile(wezterm.home_dir .. '/.claude/attention.lua')
local L = dofile(wezterm.home_dir .. '/.claude/linkrules.lua')

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
  wezterm.add_to_config_reload_watch_list(wezterm.home_dir .. '/.claude/linkrules.lua')
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
-- A fallback chain rather than a bare font(): JetBrains Mono is not installed on
-- every machine, and without a fallback WezTerm raises a missing-font error box
-- on startup. The first installed family wins, so the intended font is still
-- used wherever it is present.
config.font = wezterm.font_with_fallback {
  { family = 'JetBrains Mono', weight = 'Regular' },
  'SF Mono', 'Menlo', 'Consolas',
}
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
-- macOS needs no default_prog: WezTerm spawns the login shell, and zsh persists
-- history on its own — which is the whole point of the PowerShell branch, so
-- there is nothing to configure here.
if IS_WIN then
  config.default_prog = {
    'powershell.exe', '-NoProfile', '-NoLogo', '-NoExit', '-Command',
    'Set-PSReadLineOption -HistorySaveStyle SaveIncrementally -MaximumHistoryCount 10000',
  }
end

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
local TAB_FG = { focus = ACCENT_HI, attn = ATTN, running = RUNNING, idle = IDLE,
                 noclaude = NOCLAUDE, noclaude_hi = NOCLAUDE_HI }

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

-- Machine-specific values are NOT committed: repo root and the repo display
-- aliases both come from a gitignored terminal.local.lua, or fall back to a
-- sane default. Loaded here because the aliases below need it; REPO_DIR reads
-- the same table further down. See terminal.local.example.lua.
local function load_local_cfg()
  local ok, t = pcall(dofile, wezterm.home_dir .. '/.claude/terminal.local.lua')
  if ok and type(t) == 'table' then return t end
  return {}
end
local LOCAL = load_local_cfg()

-- Repo display aliases + leaf-only naming. Both are PURELY cosmetic: they change
-- only what format-tab-title PAINTS. The tab's real title (tab:get_title()) stays
-- the full rel, so session save (the ':find("/")' sentinel), restore (which
-- rebuilds the cwd as REPO_DIR/<title>), workspaces[title] config lookup, and
-- pane-id notification/Alt+G targeting are all untouched — none of them read the
-- rendered text. Keys are the repo path RELATIVE to the repo root, forward-
-- slashed + lowercased. No entry => the leaf folder name (last path segment).
-- The aliases themselves name private products, so they live in the gitignored
-- terminal.local.lua alongside repo_root rather than in a public repo.
local REPO_ALIASES = LOCAL.repo_aliases or {}

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
--   'web/old-name' -> 'Product'   (alias hit, verbatim)
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
      return p:sub(#REPO_DIR_NORM + 2)            -- repo-relative, e.g. web/my-app
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
  -- A.tab_paint picks the look AND applies no-Claude dimming in one tested call:
  -- a tab with no live Claude session is dimmed (low-contrast token) so agent
  -- tabs dominate; a flagged tab (amber ⬤) is never dimmed (attention stays loud).
  local flagged    = flagged_tabs[tab.tab_id] ~= nil
  local has_claude = claude_tabs[tab.tab_id] == true
  local st         = A.tab_paint(tab.is_active, flagged, has_claude, tab.active_pane.has_unseen_output)
  local title_fg   = TAB_FG[st.fg]

  local cells = { { Background = { Color = TAB_BG } } }
  if st.dot then
    cells[#cells + 1] = { Foreground = { Color = ATTN } }
    cells[#cells + 1] = { Attribute  = { Intensity = 'Bold' } }
    cells[#cells + 1] = { Text = ' ⬤ ' }
    cells[#cells + 1] = { Foreground = { Color = title_fg } }
    cells[#cells + 1] = { Attribute  = { Intensity = st.bold and 'Bold' or 'Normal' } }
    cells[#cells + 1] = { Text = idx .. ':' .. title .. ' ' }
  else
    cells[#cells + 1] = { Foreground = { Color = title_fg } }
    cells[#cells + 1] = { Attribute  = { Intensity = st.bold and 'Bold' or 'Normal' } }
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
        -- Detect by title-or-process (A.is_claude_pane): the process name alone
        -- reads bash/pwsh/cmd mid-tool, but Claude owns the title throughout.
        if do_claude_scan and not claude_seen[tid]
           and A.is_claude_pane(p:get_foreground_process_name(), p:get_title()) then
          claude_seen[tid] = true
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

  -- Left: just the workspace name (off-home only). Attention is already
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
  -- Preserve the WHOLE table (favorites/recents/workspaces + frequency/extras)
  -- so a save round-trips every field. The old whitelist rebuild silently
  -- dropped frequency (written by record_open, read by sorted_choices) and any
  -- extras, and — combined with the hand-rolled serializer — split geometry too.
  data.favorites  = data.favorites  or {}
  data.recents    = data.recents    or {}
  data.workspaces = data.workspaces or {}
  return data
end

-- Serialize the whole cfg with wezterm.json_encode (already used for
-- tab-names.json). The previous per-field hand-roller only wrote left/right,
-- silently dropping split_direction, split_size, frequency and extras — the
-- root cause of layout never restoring. json_encode emits every field, so the
-- recipe round-trips faithfully.
local function save_repos_cfg(cfg)
  local f = io.open(REPOS_CFG_PATH, 'w')
  if f then f:write(wezterm.json_encode(cfg) .. '\n'); f:close() end
end

-- ── Session persistence ───────────────────────────────────────────────────────
local SESSION_PATH  = wezterm.home_dir .. '/.claude/session.json'
local SESSION_MAX_H = 12
-- Command used to re-launch a detected Claude session on restore. --permission-mode
-- auto starts it in Auto mode (the classifier-driven mode, distinct from acceptEdits)
-- so restored agents don't sit in the normal ask-everything mode. Stored verbatim in
-- repos.json by save_session; any older 'claude --continue' value is rewritten to this
-- on the next save (so repos.json already holds the auto form by the next restart).
-- Fallback restore command when the pane's exact session id is unknown:
-- --continue resumes the cwd's MOST RECENT conversation (wrong when a repo has
-- several — see pane_session_id below for the precise path). --permission-mode
-- auto starts it in the classifier-driven Auto mode so restored agents don't
-- sit in ask-everything mode.
local CLAUDE_RESTORE_CMD = 'claude --continue --permission-mode auto'

-- The exact Claude session id bound to a pane, or nil. record-pane-session.ps1
-- (SessionStart hook) writes pane-sessions/pane-<WEZTERM_PANE>.json while the
-- session runs; here we read it back by the pane's id (p:pane_id() == the
-- WEZTERM_PANE the hook saw). This is what lets N tabs in the SAME repo each
-- resume THEIR conversation instead of all colliding on --continue's guess.
local PANE_SESSIONS_DIR = wezterm.home_dir .. '/.claude/workspaces/pane-sessions'
local function pane_session_id(pane)
  local ok, pid = pcall(function() return pane:pane_id() end)
  if not ok or not pid then return nil end
  local f = io.open(PANE_SESSIONS_DIR .. '/pane-' .. tostring(pid) .. '.json', 'r')
  if not f then return nil end
  local raw = f:read('*a'); f:close()
  raw = raw:gsub('^\239\187\191', '')                 -- strip UTF-8 BOM if present
  local ok2, data = pcall(wezterm.json_parse, raw)
  if not ok2 or type(data) ~= 'table' then return nil end
  local sid = data.session
  -- Only trust a UUID-shaped id (guards against a malformed file injecting shell
  -- text — the id is interpolated into the launch command).
  if type(sid) == 'string' and sid:match('^[%w%-]+$') then return sid end
  return nil
end

-- Programs worth re-launching on restore. Claude is matched by name (its
-- own --continue recipe below); everything here is a long-running dev process
-- whose exact invocation we reconstruct from argv. Keyed by the executable's
-- leaf name, lower-cased, sans .exe. The interactive SHELLS (pwsh/powershell/
-- cmd/bash) are deliberately absent — an idle prompt must NOT be captured as a
-- command, or restore would relaunch a shell inside a shell. Extend freely.
local RESUMABLE = {
  node = true, python = true, python3 = true, bun = true, deno = true,
  pnpm = true, npm = true, yarn = true, vite = true, next = true,
  vim = true, nvim = true, nano = true, jupyter = true, ssh = true,
  cargo = true, go = true, docker = true, ['docker-compose'] = true,
}

-- Quote a single argv token for the shell that will re-run it (only when it
-- contains whitespace, to keep the common case readable). PowerShell doubles an
-- embedded single quote; a POSIX shell has to close the quote, escape it, and
-- reopen.
local function quote_arg(a)
  if not a:find('%s') then return a end
  if IS_WIN then return "'" .. a:gsub("'", "''") .. "'" end
  return "'" .. a:gsub("'", "'\\''") .. "'"
end

-- The command to relaunch in a pane on restore, or nil if the pane holds an
-- idle shell / a transient command not worth resuming. Claude keeps its proven
-- name-based detection (its foreground name contains "claude" throughout the
-- session, even while shelling out mid-tool); other whitelisted programs are
-- reconstructed verbatim from argv. Wrapped in pcall so an unsupported build or
-- a dead pane degrades to "no command" instead of breaking the whole config.
local function pane_resume_cmd(pane)
  local name = (pane:get_foreground_process_name() or ''):lower()
  if name:find('claude') then
    -- Prefer the pane's exact session (claude --resume <id>); fall back to the
    -- most-recent guess only when no binding was captured (older session, hook
    -- not yet fired, or restore reaped the file).
    local sid = pane_session_id(pane)
    if sid then return 'claude --resume ' .. sid .. ' --permission-mode auto' end
    return CLAUDE_RESTORE_CMD
  end
  local ok, info = pcall(function() return pane:get_foreground_process_info() end)
  if not ok or type(info) ~= 'table' then return nil end
  local leaf = ((info.executable or info.name or ''):gsub('\\', '/')
                 :match('[^/]+$') or ''):lower():gsub('%.exe$', '')
  if not RESUMABLE[leaf] then return nil end
  local argv = info.argv
  if type(argv) ~= 'table' or #argv == 0 then return nil end
  local parts = {}
  for _, a in ipairs(argv) do parts[#parts + 1] = quote_arg(a) end
  return table.concat(parts, ' ')
end

-- Build the PowerShell spawn args for a restored pane: cd into the repo, then
-- run the saved command with -NoExit so the pane drops to an interactive shell
-- once the command exits (a dev server that crashes leaves a usable prompt, not
-- a dead pane). Returns nil for an empty command → caller spawns a plain shell.
-- Shared by both panes so quoting is handled uniformly by PowerShell (the old
-- right-pane path split on whitespace, which broke any quoted argument).
local function pane_launch_args(cmd, cwd)
  if not cmd or cmd == '' then return nil end
  if IS_WIN then
    local safe = cwd:gsub("'", "''")
    return {
      'powershell.exe', '-NoProfile', '-NoLogo', '-NoExit', '-Command',
      "Set-Location '" .. safe .. "'; " .. cmd,
    }
  end
  -- The POSIX equivalent of -NoExit: run the saved command, then hand the pane
  -- to an interactive login shell so a dev server that crashes leaves a usable
  -- prompt instead of a dead pane. `exec` replaces the wrapper, so no extra
  -- shell layer lingers in the process tree. Braces keep a compound command
  -- (`a && b`) from binding only its first clause to the `;`.
  local safe = cwd:gsub("'", "'\\''")
  return {
    SHELL, '-lc',
    "cd '" .. safe .. "' && { " .. cmd .. "; }; exec " .. SHELL .. " -l",
  }
end

save_session = function(window)
  local cfg     = load_repos_cfg()
  local changed = false
  local parts   = {}

  for _, tab in ipairs(window:mux_window():tabs()) do
    local title = tab:get_title()
    if not title:find('/') then goto continue end  -- skip Nexus/shell-named tabs
    parts[#parts + 1] = '"' .. title:gsub('"', '\\"') .. '"'

    -- panes_with_info gives per-pane geometry (cells) + the MuxPane handle.
    local pinfo = tab:panes_with_info()
    if #pinfo > 2 then
      -- Honest bound: the restore path rebuilds a single left/right split, so a
      -- 3+-pane tab loses its extra panes. Log it (no silent truncation) rather
      -- than pretend the whole layout came back.
      wezterm.log_info('nexus: tab "' .. title .. '" has ' .. #pinfo ..
        ' panes; only the first split is captured for restore')
    end

    -- Capture a FRESH recipe from live state each save, so closing Claude or a
    -- service, or resizing the split, is reflected on restore (the old code only
    -- ever ADDED fields, so stale commands lingered forever). left/right are
    -- each detected independently, so Claude in EITHER pane is now captured.
    local rec = { split = pinfo[2] ~= nil }
    if pinfo[1] then rec.left = pane_resume_cmd(pinfo[1].pane) end
    if pinfo[2] then
      rec.right = pane_resume_cmd(pinfo[2].pane)
      -- Direction + size from the actual pane rectangle. size = the new (second)
      -- pane's fraction of the split axis — exactly what pane:split{size=..}
      -- expects — so restore reproduces the real proportions, not a fixed 40%.
      if pinfo[2].top > pinfo[1].top then
        rec.split_direction = 'Down'
        local tot = pinfo[1].height + pinfo[2].height
        if tot > 0 then rec.split_size = math.floor(pinfo[2].height / tot * 100 + 0.5) / 100 end
      else
        rec.split_direction = 'Right'
        local tot = pinfo[1].width + pinfo[2].width
        if tot > 0 then rec.split_size = math.floor(pinfo[2].width / tot * 100 + 0.5) / 100 end
      end
    end

    -- Write only when the recipe actually changed, to keep the 30 s autosave
    -- from churning repos.json every tick.
    local prev = cfg.workspaces[title] or {}
    if prev.left ~= rec.left or prev.right ~= rec.right
       or prev.split ~= rec.split or prev.split_direction ~= rec.split_direction
       or prev.split_size ~= rec.split_size then
      changed = true
    end
    cfg.workspaces[title] = rec
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
-- Records the focused workspace/cwd/branch to active.json for external tooling.
local function write_active(window, pane)
  if not window:is_focused() then return end
  local workspace = window:active_workspace()
  local cwd_obj   = pane:get_current_working_dir()
  local cwd       = cwd_obj and cwd_obj.file_path or ''
  if cwd:match('^/[A-Za-z]:') then cwd = cwd:sub(2) end
  cwd = cwd:gsub('\\', '/')

  -- Resolve git branch for the current working directory.
  local branch = ""
  local git_cwd = IS_WIN and cwd:gsub('/', '\\') or cwd
  local ok, stdout = wezterm.run_child_process({
    'git', '-C', git_cwd, 'branch', '--show-current',
  })
  if ok then branch = stdout:match('^%s*(.-)%s*$') or "" end

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

-- Nexus keymap pop-up (Alt+/). Draws the cheat sheet, then blocks on a single
-- keypress and exits. WezTerm's default exit_behavior closes a pane when its
-- process exits, so the zoomed overlay dismisses itself on any key — no state
-- to track. No resize loop needed either: the pane is transient and spawned
-- zoomed (full tab), so every row already fits without wrapping.
local function keymap_popup_args()
  if wezterm.target_triple:find('windows') then
    local f = keymap_file:gsub('/', '\\')
    -- ESC[3J+2J+H = wipe scrollback+screen, home cursor. -NonInteractive is
    -- omitted so [Console]::ReadKey can block for the dismiss keypress.
    return {
      'powershell.exe', '-NoProfile', '-NoLogo', '-Command',
      '[Console]::OutputEncoding=[Text.Encoding]::UTF8; ' ..
      '$e=[char]27; $b=[char]7; ' ..
      -- OSC 1337 SetUserVar tags this pane keymap_popup=1 (MQ== is base64 "1")
      -- so the Alt+/ handler can find an already-open pop-up and toggle it shut
      -- instead of stacking another. BEL ($b) terminates the OSC string.
      'Write-Host "${e}]1337;SetUserVar=keymap_popup=MQ==${b}" -NoNewline; ' ..
      'Write-Host "${e}[3J${e}[2J${e}[H" -NoNewline; ' ..
      'Get-Content "' .. f .. '" -Encoding UTF8; ' ..
      'Write-Host "  ${e}[2mpress any key to close${e}[0m"; ' ..
      '$null = [Console]::ReadKey($true)',
    }
  end
  return { 'bash', '-c',
    'printf "\\033]1337;SetUserVar=keymap_popup=MQ==\\007"; ' ..
    'printf "\\033[3J\\033[2J\\033[H"; cat "' .. keymap_file .. '"; ' ..
    'printf "  \\033[2mpress any key to close\\033[0m\\n"; ' ..
    'read -rsn1' }
end

-- ── The project's live state document ────────────────────────────────────────
-- Same canonical name, aliases and search order as scripts/workspace-state.py
-- and scripts/open-workspace.sh, so the pane, the launcher and the SessionStart
-- hook can never disagree about which file is the state of a project.
local STATE_DOC_DIRS  = { 'docs', '.' }
local STATE_DOC_NAMES = { 'STATE.md', 'context.md', 'workflow_state.md', 'KNOWLEDGE.md' }

-- Returns a pager command for the state doc, or nil when the project has none.
-- ponytail: raw markdown in a pager; swap in glow/bat if either lands in PATH.
local function state_doc_cmd(cwd)
  for _, d in ipairs(STATE_DOC_DIRS) do
    for _, n in ipairs(STATE_DOC_NAMES) do
      local rel = d .. '/' .. n
      local f = io.open(cwd .. '/' .. rel, 'r')
      if f then
        f:close()
        return (IS_WIN and 'more "' or 'less -R "') .. rel .. '"'
      end
    end
  end
  return nil
end

-- ── Shared helper: create a repo tab (NO keymap — that's Nexus-only) ─────────
-- Left pane (60%): shell, or saved command (e.g. "claude --continue").
--   Wrapped in PS so a shell prompt survives after the command exits.
-- Right pane (40%): saved service command (e.g. "pnpm dev"), else the project's
--   live state document, else a plain shell. A recorded recipe always wins — the
--   state doc fills the pane that would otherwise open on an idle prompt.
local function make_tab(mux_win, title, cwd)
  local ws  = (load_repos_cfg().workspaces or {})[title] or {}

  -- Both panes go through pane_launch_args: cd + saved command under a -NoExit
  -- shell, so an exited command leaves a live prompt. nil command → plain shell.
  -- Quitting the pager therefore drops to a usable shell, not a dead pane.
  local left_args  = pane_launch_args(ws.left,  cwd)
  local right_args = pane_launch_args(ws.right or state_doc_cmd(cwd), cwd)

  local spawn_cfg = left_args and { cwd = cwd, args = left_args } or { cwd = cwd }
  local tab = mux_win:spawn_tab(spawn_cfg)
  if not tab then return nil end
  tab:set_title(title)
  local left_pane = tab:active_pane()

  -- Split unless the saved recipe explicitly recorded a single-pane tab
  -- (ws.split == false). A tab with no recipe yet (freshly opened via Alt+O)
  -- has ws.split == nil → still gets the default 60/40 work+service layout.
  -- Size + direction come from the recorded geometry, falling back to the
  -- shared defaults for a brand-new tab.
  if ws.split ~= false then
    left_pane:split {
      direction = ws.split_direction or 'Right',
      size      = ws.split_size or RIGHT_PANE_FRAC,
      args      = right_args,
      cwd       = cwd,
    }
  end
  left_pane:activate()
  return tab
end

wezterm.on('gui-startup', function(cmd)
  if cmd then
    local _, _, window = wezterm.mux.spawn_window(cmd)
    window:gui_window():maximize()
    return
  end

  -- Create the Nexus home tab (workspace name matches config.default_workspace).
  -- Home is a single maximized shell pane now: the keymap lives in the on-demand
  -- Alt+/ pop-up (a zoomed, self-dismissing pane) instead of a permanent column.
  local _, _, window = wezterm.mux.spawn_window({
    workspace = 'nexus',
    cwd       = REPO_DIR,
  })
  window:gui_window():maximize()
  window:active_tab():set_title('Nexus')

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

-- Directory names never worth walking into. Shared by both discovery paths so
-- the Windows walk and the macOS find return the same repo set.
local PRUNE_DIRS = {
  'node_modules', 'dist', '.next', 'build', 'out', '.worktrees', 'archive',
  '_Misc', 'example', 'examples', '.venv', 'venv', '__pycache__', 'target',
  'obj', '.turbo', '.cache',
}

-- `find` argv that prints every .git entry under the repo root, pruning the
-- noise directories at the door. The POSIX counterpart of the pruned walk in the
-- PowerShell branch below, and pruned for the same reason: an unpruned walk of a
-- repo root full of node_modules costs hundreds of milliseconds on every Alt+O.
--
-- Matching .git (rather than testing each directory for one) keeps it a single
-- pass. `-prune` after the match skips only .git's own internals, so the walk
-- still descends past a repo and nested repos are found — same as the original.
-- -maxdepth 5 = a .git at depth 5, i.e. repos up to 4 levels below the root,
-- matching the Windows walk's depth cap of 4.
local function find_repos_argv()
  local argv = { '/usr/bin/find', REPO_DIR, '-maxdepth', '5', '(', '-type', 'd', '(' }
  for i, name in ipairs(PRUNE_DIRS) do
    if i > 1 then argv[#argv + 1] = '-o' end
    argv[#argv + 1] = '-name'
    argv[#argv + 1] = name
  end
  argv[#argv + 1] = ')'
  argv[#argv + 1] = '-prune'
  argv[#argv + 1] = ')'
  -- No -type here: a worktree or submodule has .git as a FILE, and those are
  -- real repos the launcher should list.
  for _, token in ipairs({ '-o', '(', '-name', '.git', '-print', '-prune', ')' }) do
    argv[#argv + 1] = token
  end
  return argv
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
  local ok, stdout
  if IS_WIN then
    ok, stdout = wezterm.run_child_process({
      'powershell.exe', '-NoProfile', '-NoLogo', '-NonInteractive', '-Command', ps,
    })
  else
    ok, stdout = wezterm.run_child_process(find_repos_argv())
  end
  if not ok then return {} end
  local repos = {}
  for line in stdout:gmatch('[^\r\n]+') do
    line = line:match('^%s*(.-)%s*$')
    -- find prints the .git entry; the repo is its parent. Stripping it also maps
    -- REPO_DIR/.git back to REPO_DIR, so a repo root that is itself a repo is
    -- listed exactly like the PowerShell branch lists it.
    if not IS_WIN then line = line:gsub('/%.git$', '') end
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

-- Open a repo as a TAB in the window you're already in. Deliberately not a
-- workspace-per-repo launcher: mux.spawn_window opens a second OS window, and
-- SwitchToWorkspace then swaps the current window's whole tab set out of view,
-- so Alt+O read as "my layout vanished and a stray terminal appeared".
local function launch_repo(win, _pane, repo)
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

  -- ── Help: Alt+/ toggles the keymap as a zoomed, self-dismissing overlay ──
  -- Single instance: first scan every pane in the window for the keymap_popup
  -- user-var tag. If one is already open, close it (toggle off) instead of
  -- stacking another. Otherwise split a transient pane running the cheat sheet,
  -- activate + zoom it to fill the tab. Any keypress also exits its process, so
  -- it self-dismisses; zoom auto-releases back to where you were. Works from
  -- ANY tab, not just home.
  { key = '/', mods = 'ALT', action = wezterm.action_callback(function(win, pane)
      for _, tab in ipairs(win:mux_window():tabs()) do
        for _, p in ipairs(tab:panes()) do
          if p:get_user_vars()['keymap_popup'] == '1' then
            win:perform_action(act.CloseCurrentPane { confirm = false }, p)
            return
          end
        end
      end
      local popup = pane:split { direction = 'Right', size = 0.5, args = keymap_popup_args() }
      if popup then
        popup:activate()
        popup:tab():set_zoomed(true)
      end
    end) },
}

-- ── Scrollback / defaults ─────────────────────────────────────────────────────
-- ── Clickable links over TUIs (Claude Code etc.) ────────────────────────────
-- A full-screen TUI enables mouse reporting, so plain clicks are delivered to
-- the app and never reach WezTerm's link opener — which is why links looked
-- dead. mouse_reporting = true lets these fire anyway: Ctrl+Click opens the URL
-- / OSC-8 file link under the cursor, and the Ctrl press-down is swallowed so it
-- doesn't begin a text selection. (With no TUI running, the built-in Ctrl+Click
-- rule already handles it.)
-- Both CTRL and SUPER (Cmd) are bound. Cmd+Click is the macOS convention and is what
-- WezTerm's own built-in rule uses — but that built-in has no mouse_reporting = true, so
-- inside a TUI the app swallows it and the link looks dead. Binding CTRL alone left the
-- muscle-memory gesture broken; both are bound so either works, in or out of a TUI.
config.mouse_bindings = {
  { event = { Down = { streak = 1, button = 'Left' } }, mods = 'CTRL',
    mouse_reporting = true, action = act.Nop },
  { event = { Up = { streak = 1, button = 'Left' } }, mods = 'CTRL',
    mouse_reporting = true, action = act.OpenLinkAtMouseCursor },
  { event = { Down = { streak = 1, button = 'Left' } }, mods = 'SUPER',
    mouse_reporting = true, action = act.Nop },
  { event = { Up = { streak = 1, button = 'Left' } }, mods = 'SUPER',
    mouse_reporting = true, action = act.OpenLinkAtMouseCursor },

  -- ── Wheel scrolling inside a mouse-reporting TUI ──────────────────────────
  -- Same root cause as the Ctrl+Click rules above: a mouse-reporting app owns the
  -- wheel, so WezTerm neither synthesizes arrow keys (see
  -- alternate_buffer_wheel_scroll_speed) nor has scrollback to move — a fullscreen
  -- Claude Code pane holds ~14 lines of pre-TUI shell output and nothing else.
  -- Whatever the app does with a wheel event is all you get, and in Claude Code that
  -- is one line.
  --
  -- So intercept the wheel before the app sees it and send the app's own paging keys.
  -- PageUp/PageDown are used because they were verified to scroll the Claude Code
  -- transcript; arrow keys are deliberately NOT used, as Up recalls the previous
  -- prompt and would rewrite your input while you scrolled.
  --
  -- Scope: applies to every mouse-reporting TUI, not just Claude Code. A TUI that
  -- uses the wheel for something other than scrolling loses that here.
  { event = { Down = { streak = 1, button = { WheelUp = 1 } } }, mods = 'NONE',
    mouse_reporting = true, action = act.SendKey { key = 'PageUp' } },
  { event = { Down = { streak = 1, button = { WheelDown = 1 } } }, mods = 'NONE',
    mouse_reporting = true, action = act.SendKey { key = 'PageDown' } },
}

-- Make bare file paths clickable too, on top of the built-in URL rules. The
-- matched text is handed verbatim to open-uri below.
config.hyperlink_rules = wezterm.default_hyperlink_rules()
if IS_WIN then
  -- e.g. D:\repo\foo.ts:12
  table.insert(config.hyperlink_rules, {
    regex  = [[[A-Za-z]:[\\/](?:[^\s"'<>|:*?]+[\\/])*[^\s"'<>|:*?]+\.[A-Za-z0-9]+(?::\d+(?::\d+)?)?]],
    format = '$0',
  })
else
  -- e.g. /Users/me/repo/foo.ts:12 or ~/repo/foo.ts. Anchored on / or ~/ and
  -- required to carry a file extension, so ordinary prose containing a slash
  -- ("and/or", "TODO: 3/4 done") is not turned into a dead link.
  --
  -- The leading (?:^|[\s"'(\[<`]) is load-bearing and was missing. Without it the rule matched
  -- from ANY slash inside a word, so a repo-relative path printed by an agent --
  -- "docs/notes/harness/MAP.md" -- became the link "/notes/harness/MAP.md": the first segment
  -- sat outside the underline (clicking it did nothing) and what was handed over looked absolute
  -- and did not exist. The path is group 1 so the delimiter is not part of the target.
  table.insert(config.hyperlink_rules, {
    regex     = [[(?:^|[\s"'(\[<`])((?:~|\.{1,2})?/(?:[\w.\-+@]+/)*[\w.\-+@]+\.[A-Za-z0-9]+(?::\d+(?::\d+)?)?)]],
    format    = '$1',
    highlight = 1,
  })

  -- Repo-relative paths WITH a directory -- "docs/TODO.md", "4JIM/PROPOSAL.md:12". These are what
  -- agent output and this repo's own documents are full of, and no rule matched them whole. The
  -- extension allowlist keeps prose out, the same trade the bare-name rule below makes; a bare
  -- extension class here would turn "and/or" and "TODO: 3/4" into links.
  table.insert(config.hyperlink_rules, {
    regex     = [[(?:^|[\s"'(\[<`])((?:[\w.\-+@]+/)+[\w.\-+@]+\.(?:md|rb|lua|py|sh|zsh|ts|tsx|js|jsx|json|ya?ml|sql|css|scss|html|toml|rake|gemspec)(?::\d+(?::\d+)?)?)]],
    format    = '$1',
    highlight = 1,
  })
end

-- Bare filenames, e.g. OBSERVABILITY.md or create_corporation.rb:31. Agent output and
-- commit messages name files without a directory constantly, so anchoring only on / and ~/
-- left most file references dead. open-in-editor.sh resolves a bare name against
-- CLAUDENCE_LINK_ROOTS.
--
-- The extension list is an allowlist rather than \w+ on purpose: it keeps ordinary prose from
-- becoming clickable. "e.g." and version strings like "14.13.2" do not match, because "g" and
-- "2" are not in the list. Inserted LAST so the absolute-path rules above win on paths that
-- carry a directory.
table.insert(config.hyperlink_rules, {
  regex  = [[\b[\w\-+@]+\.(?:md|rb|lua|py|sh|zsh|ts|tsx|js|jsx|json|ya?ml|sql|css|scss|html|toml|rake|gemspec)(?::\d+(?::\d+)?)?\b]],
  format = '$0',
})

-- Route opened links: web/mail use the OS default (browser); anything that looks
-- like a local file opens in VS Code at its line via open-in-vscode.ps1 (which
-- also flips markdown into preview mode).
wezterm.on('open-uri', function(_window, pane, uri)
  -- The predicate lives in linkrules.lua because it was WRONG here for two days: its character
  -- class excluded '/' while anchored ^...$, so a repo-relative path -- the commonest shape in
  -- agent output, and the one the hyperlink rule above was fixed to match whole -- was routed to
  -- the browser. Inline logic in a config file has no test; the module has 21 cases.
  local is_local = L.is_local_target(uri, IS_WIN)
  if not is_local then
    return  -- not a local file → let WezTerm open it (browser, etc.)
  end
  local target = uri:gsub('^file://', ''):gsub('^/([A-Za-z]:)', '%1')  -- file:///D:/x → D:/x
  if IS_WIN then
    wezterm.background_child_process({
      'powershell.exe', '-NoProfile', '-WindowStyle', 'Hidden', '-File',
      wezterm.home_dir .. '/.claude/scripts/open-in-vscode.ps1', '-Target', target,
    })
  else
    target = target:gsub('^~', wezterm.home_dir)
    -- The PANE's cwd is the only thing that disambiguates a repo-relative link. "docs/TODO.md"
    -- exists in several checkouts, so resolving it by root order alone opens whichever repo comes
    -- first in the list rather than the one the line was printed in. background_child_process
    -- inherits the GUI app's cwd, never the pane's, so it has to be handed over explicitly.
    local cwd = ''
    local got, dir = pcall(function() return pane:get_current_working_dir() end)
    if got and dir then
      cwd = type(dir) == 'string' and (dir:gsub('^file://[^/]*', '')) or (dir.file_path or '')
    end
    wezterm.background_child_process({
      wezterm.home_dir .. '/.claude/scripts/open-in-editor.sh', target, cwd,
    })
  end
  return false  -- handled; don't let WezTerm try to open the raw path
end)

config.scrollback_lines  = 10000

-- Wheel scrolling inside a full-screen TUI (Claude Code, less, vim) does NOT move the
-- scrollback — the app owns the alternate screen, so WezTerm translates each wheel notch
-- into this many synthetic arrow-key presses and lets the app scroll itself. The default
-- is 3, which reads as "one or two lines" once the app coalesces them. Raising it is the
-- only knob for TUI scroll speed; scrollback_lines above is buffer depth, not speed.
--
-- Deliberately not overriding the primary-screen wheel bindings: WezTerm's default there
-- is ScrollByCurrentEventWheelDelta, which honours the trackpad's momentum. Replacing it
-- with a fixed ScrollByLine would make two-finger scrolling chunky to speed up a mouse
-- wheel nobody here uses.
config.alternate_buffer_wheel_scroll_speed = 6

config.default_workspace = 'nexus'
-- Repaint the status bar 4x/s instead of the 1s default so a workspace
-- switch/rename converges fast (backstop to the immediate repaint in Alt+N).
-- update-status only scans the small attention dir + in-memory mux state, so
-- the extra ticks are cheap.
config.status_update_interval = 250

-- Config-load fingerprint. The status bar shows a short-lived "✓ reloaded" pill, but that
-- is easy to miss and proves only that SOMETHING reloaded. This writes the load time and
-- the values most likely to be in question to the GUI log, so
-- `tail ~/.local/share/wezterm/wezterm-gui-log-<pid>.txt` answers "did my edit take
-- effect, and what is actually live?" without guessing.
wezterm.log_info(string.format(
  'nexus config loaded %s | alt_buffer_wheel_scroll_speed=%s scrollback_lines=%s',
  os.date('%Y-%m-%d %H:%M:%S'),
  tostring(config.alternate_buffer_wheel_scroll_speed),
  tostring(config.scrollback_lines)))

return config
