local wezterm = require 'wezterm'
local config  = wezterm.config_builder()
local act     = wezterm.action

-- Auto-reload on file save — no Ctrl+Shift+R needed after edits.
-- WezTerm watches the resolved symlink target, so saving terminal.lua
-- in ~/.claude/ triggers the reload directly.
config.automatically_reload_config = true
-- This file is dofile'd from ~/.wezterm.lua, so WezTerm's reload watcher never
-- sees it on its own. Register it explicitly so saving terminal.lua reloads.
if wezterm.add_to_config_reload_watch_list then
  wezterm.add_to_config_reload_watch_list(wezterm.home_dir .. '/.claude/terminal.lua')
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

-- Left Alt = clean modifier (no special chars); Right Alt still composes é, ñ, etc.
config.send_composed_key_when_left_alt_is_pressed  = false
config.send_composed_key_when_right_alt_is_pressed = true

-- Bell drives the tab attention indicator (amber ⬤) via the 'bell' event below.
-- Disabled here only silences WezTerm's own beep — the event still fires.
config.audible_bell = 'Disabled'

-- ── Tab bar ───────────────────────────────────────────────────────────────────
config.use_fancy_tab_bar              = false
config.tab_bar_at_bottom              = true
config.hide_tab_bar_if_only_one_tab   = false
config.tab_max_width                  = 28
config.show_new_tab_button_in_tab_bar = false

-- Tab states — color carries focus; the ● appears ONLY when a tab needs you:
--   focused   → bold accent text     you are here (no dot, no bg highlight)
--   attention → amber ⬤ + bold       bell/Stop hook fired: agent done, awaiting input
--   running   → muted (has output)   agent still working in the background
--   idle      → dim                  nothing happening
-- bell_tabs[tab_id] = true is set by the 'bell' handler and cleared the moment
-- you focus that tab. This is the semantic "agent finished" signal — distinct
-- from has_unseen_output, which flips on every line of continuous output.
local bell_tabs = {}

wezterm.on('bell', function(window, pane)
  local tab = pane:tab()
  if not tab then return end
  -- Don't flag the tab you're already looking at.
  local active = window:active_tab()
  if active and active:tab_id() == tab:tab_id() then return end
  bell_tabs[tab:tab_id()] = true
end)

wezterm.on('format-tab-title', function(tab, _tabs, _panes, _conf, _hover, _max_width)
  local title = tab.tab_title ~= '' and tab.tab_title or tab.active_pane.title
  local idx   = tostring(tab.tab_index + 1)

  -- Arriving at a tab clears its attention flag.
  if tab.is_active then bell_tabs[tab.tab_id] = nil end

  -- Attention: fill the whole tab amber so it's impossible to miss. A glyph is
  -- capped at one cell, so a filled background is the only way to make it bigger.
  if not tab.is_active and bell_tabs[tab.tab_id] then
    return {
      { Background = { Color = ATTN } },
      { Foreground = { Color = '#11111b' } },
      { Attribute  = { Intensity = 'Bold' } },
      { Text = ' ⬤ ' .. idx .. ':' .. title .. ' ' },
    }
  end

  local fg, intensity
  if tab.is_active then
    fg, intensity = ACCENT_HI, 'Bold'
  elseif tab.active_pane.has_unseen_output then
    fg, intensity = RUNNING, 'Normal'
  else
    fg, intensity = IDLE, 'Normal'
  end

  return {
    { Background = { Color = '#181825' } },
    { Foreground = { Color = fg } },
    { Attribute  = { Intensity = intensity } },
    { Text = '  ' .. idx .. ':' .. title .. ' ' },
  }
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

wezterm.on('update-status', function(window, _pane)
  local ws = window:active_workspace()

  -- Clear the attention flag for whatever tab is now active. format-tab-title
  -- also clears it, but doing it here guarantees it on every focus change and
  -- ~1s tick — independent of when the tab title happens to repaint.
  local _at = window:active_tab()
  if _at then bell_tabs[_at:tab_id()] = nil end

  -- Left: workspace name (line 1); active agent task (line 2, only when present)
  local left_cells = {
    { Foreground = { Color = ACCENT } },
    { Attribute = { Intensity = 'Bold' } },
    { Text = '  ⬡ ' .. ws .. '  ' },
  }
  if _cached_agent_task ~= "" then
    table.insert(left_cells, { Foreground = { Color = '#585b70' } })
    table.insert(left_cells, { Attribute = { Intensity = 'Normal' } })
    table.insert(left_cells, { Text = '\n  · ' .. _cached_agent_task:sub(1, 60) .. '  ' })
  end
  window:set_left_status(wezterm.format(left_cells))

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
  local now = os.time()
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
        if cfg.workspaces[title].left ~= 'claude --continue' then
          cfg.workspaces[title].left = 'claude --continue'
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
-- Tab 2: shell in D:/repo (main working directory)
-- config.maximized is not valid in this WezTerm build; gui-startup is the
-- correct hook for window-state setup.
local keymap_file = wezterm.home_dir .. '/.claude/keymap.txt'
local REPO_DIR    = 'D:/repo'

-- Right-pane width, shared by the Nexus home tab and every repo tab so the
-- layout is consistent. WezTerm sizes the NEW (right) pane as this fraction of
-- the pane being split; the ratio is preserved across later window resizes.
local RIGHT_PANE_FRAC = 0.40

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
  shell_pane:split { direction = 'Right', size = RIGHT_PANE_FRAC, args = keymap_args(), cwd = REPO_DIR }
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
-- Alt+O: fuzzy picker over all git repos under D:\repo.
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
  local ok, stdout = wezterm.run_child_process({
    'powershell.exe', '-NoProfile', '-NoLogo', '-NonInteractive', '-Command',
    'Get-ChildItem "D:\\repo" -Recurse -Depth 4 -Force -Filter ".git" ' ..
    '| Where-Object { $_.FullName -notmatch ' ..
    '"[\\\\/](\\.worktrees|archive|_Misc|example[s]?)[\\\\/]" } ' ..
    '| ForEach-Object { $_.Parent.FullName } ' ..
    '| Sort-Object -Unique',
  })
  if not ok then return {} end
  local repos = {}
  for line in stdout:gmatch('[^\r\n]+') do
    line = line:match('^%s*(.-)%s*$')
    if line ~= '' then
      local rel = line:gsub('D:\\repo\\', ''):gsub('D:/repo/', ''):gsub('\\', '/')
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
  -- Extras (paths outside D:/repo) pinned above favorites with ~ prefix
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
--  TAB NAV    W=prev  S=next
--  PANE OPS   Z=zoom  X=close  C=split-H  V=split-V  T=new-tab
--  WORKSPACES F=fuzzy  R=rename  [/]=cycle  G=repo launcher
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
          -- Extras (outside D:/repo) open directly; no recent tracking needed.
          if not id:match('^[Dd]:[/\\]repo') then
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
      local rel = cwd:match('^[Dd]:/repo/(.+)$')
      if not rel then
        win:toast_notification('Nexus', 'Not inside D:/repo', nil, 1500)
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
        end
      end),
    }},
  { key = '[', mods = 'ALT', action = act.SwitchWorkspaceRelative(-1) },
  { key = ']', mods = 'ALT', action = act.SwitchWorkspaceRelative(1)  },

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
config.scrollback_lines  = 10000
config.default_workspace = 'nexus'

return config
