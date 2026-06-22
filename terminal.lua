local wezterm = require 'wezterm'
local config  = wezterm.config_builder()
local act     = wezterm.action

-- Auto-reload on file save — no Ctrl+Shift+R needed after edits.
-- WezTerm watches the resolved symlink target, so saving terminal.lua
-- in ~/.claude/ triggers the reload directly.
config.automatically_reload_config = true

-- ── Appearance ────────────────────────────────────────────────────────────────
config.color_scheme              = 'Catppuccin Mocha'
config.font                      = wezterm.font('JetBrains Mono', { weight = 'Regular' })
config.font_size                 = 11.0
config.window_padding            = { left = 6, right = 6, top = 4, bottom = 4 }
config.window_background_opacity = 0.96

-- Left Alt = clean modifier (no special chars); Right Alt still composes é, ñ, etc.
config.send_composed_key_when_left_alt_is_pressed  = false
config.send_composed_key_when_right_alt_is_pressed = true

-- ── Tab bar ───────────────────────────────────────────────────────────────────
config.use_fancy_tab_bar              = false
config.tab_bar_at_bottom              = true
config.hide_tab_bar_if_only_one_tab   = false
config.tab_max_width                  = 28
config.show_new_tab_button_in_tab_bar = false

wezterm.on('format-tab-title', function(tab, _tabs, _panes, _conf, _hover, _max_width)
  local title  = tab.tab_title ~= '' and tab.tab_title or tab.active_pane.title
  local idx    = tostring(tab.tab_index + 1)
  local bullet = tab.is_active and '●' or '○'
  return { { Text = ' ' .. bullet .. ' ' .. idx .. ':' .. title .. ' ' } }
end)

-- ── Status bar ────────────────────────────────────────────────────────────────
wezterm.on('update-status', function(window, _pane)
  local ws = window:active_workspace()
  window:set_left_status(wezterm.format {
    { Foreground = { Color = '#a6e3a1' } },
    { Attribute = { Intensity = 'Bold'  } },
    { Text = '  ⬡ ' .. ws .. '  ' },
  })
  local task = _cached_agent_task ~= "" and ('  ·  ' .. _cached_agent_task:sub(1, 48)) or ""
  window:set_right_status(wezterm.format {
    { Foreground = { Color = '#585b70' } },
    { Text = os.date('%H:%M') .. task .. '   Alt+/  keys  ' },
  })
end)

-- ── Nexus sync: write active workspace on focus / tab change ─────────────────
-- Cached agent task shown in the right status bar. Updated here (on focus
-- change) rather than in update-status (every tick) to avoid hammering disk.
local _cached_agent_task = ""

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

  -- Read helm-status.json from the project root to show agent task in status bar.
  local status_file = cwd:gsub('/$', '') .. '/helm-status.json'
  local sf = io.open(status_file, 'r')
  if sf then
    local raw = sf:read('*a')
    sf:close()
    _cached_agent_task = raw:match('"currentTask"%s*:%s*"([^"]*)"') or ""
  else
    _cached_agent_task = ""
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
end

-- ── Default startup layout ────────────────────────────────────────────────────
-- Tab 1: persistent keys reference (always visible on launch)
-- Tab 2: shell in D:/repo (main working directory)
-- config.maximized is not valid in this WezTerm build; gui-startup is the
-- correct hook for window-state setup.
local keymap_file = wezterm.home_dir .. '/.claude/keymap.txt'
local REPO_DIR    = 'D:/repo'

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

wezterm.on('gui-startup', function(cmd)
  -- cmd is non-nil when WezTerm was launched with an explicit command;
  -- honour it and only maximise.
  if cmd then
    local _, _, window = wezterm.mux.spawn_window(cmd)
    window:gui_window():maximize()
    return
  end

  -- Default layout:
  --   Left (main): shell in D:/repo  ~72% width
  --   Right (strip): persistent keymap reference  ~28% width
  -- The keymap pane is always visible without any tab switching.
  local _, shell_pane, window = wezterm.mux.spawn_window({
    cwd = REPO_DIR,
  })

  shell_pane:split {
    direction = 'Right',
    size      = 0.28,
    args      = keymap_args(),
    cwd       = REPO_DIR,
  }

  -- Return focus to the shell (split activates the new pane by default)
  shell_pane:activate()

  window:gui_window():maximize()
end)

wezterm.on('window-focus-changed', write_active)
wezterm.on('window-activated',     write_active)

-- Toast when config hot-reloads so it's obvious the new bindings are live.
wezterm.on('window-config-reloaded', function(window, _pane)
  window:toast_notification('WezTerm', 'config reloaded', nil, 1500)
end)

-- ── Help: opens a persistent "keys" tab showing the keymap ──────────────────

local function show_keymap(win, pane)
  win:perform_action(
    act.SpawnCommandInNewTab { args = keymap_args() },
    pane
  )
end

-- ── Repo launcher ─────────────────────────────────────────────────────────────
-- Alt+O: fuzzy picker over all git repos under D:\repo.
-- Favorites (★) are pinned to the top; recently opened repos come next;
-- everything else is below but still fuzzy-searchable.
-- Alt+P: toggle-pin the current workspace's repo as a favorite.

local OPEN_WS_SCRIPT = (os.getenv('USERPROFILE') or '') .. '\\.claude\\scripts\\open-workspace.ps1'
local REPOS_CFG_PATH = wezterm.home_dir .. '/.claude/repos.json'
local REPOS_MAX_RECENTS = 10

local function path_to_ws_name(rel)
  return rel:lower()
    :gsub('[/\\%s]+', '-')
    :gsub('[^a-z0-9%-]', '')
    :gsub('%-+', '-')
    :gsub('^%-+', '')
    :gsub('%-+$', '')
end

local function load_repos_cfg()
  local f = io.open(REPOS_CFG_PATH, 'r')
  if not f then return { favorites = {}, recents = {} } end
  local raw = f:read('*a'); f:close()
  local ok, data = pcall(wezterm.json_parse, raw)
  if not ok or type(data) ~= 'table' then return { favorites = {}, recents = {} } end
  return { favorites = data.favorites or {}, recents = data.recents or {} }
end

local function save_repos_cfg(cfg)
  local function arr(t)
    local parts = {}
    for _, v in ipairs(t) do parts[#parts+1] = '"' .. v:gsub('"', '\\"') .. '"' end
    return '[' .. table.concat(parts, ',') .. ']'
  end
  local f = io.open(REPOS_CFG_PATH, 'w')
  if f then
    f:write('{"favorites":' .. arr(cfg.favorites) .. ',"recents":' .. arr(cfg.recents) .. '}\n')
    f:close()
  end
end

local function discover_repos()
  local ok, stdout = wezterm.run_child_process({
    'powershell.exe', '-NoProfile', '-NoLogo', '-NonInteractive', '-Command',
    'Get-ChildItem "D:\\repo" -Recurse -Depth 4 -Force -Filter ".git" ' ..
    '| Where-Object { $_.FullName -notmatch "[\\\\/]\\.worktrees[\\\\/]|[\\\\/]archive[\\\\/]" } ' ..
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
  local fav_idx, rec_idx = {}, {}
  for i, r in ipairs(cfg.favorites) do fav_idx[r] = i end
  for i, r in ipairs(cfg.recents)   do rec_idx[r] = i end

  table.sort(repos, function(a, b)
    local af = fav_idx[a.rel] or math.huge
    local bf = fav_idx[b.rel] or math.huge
    if af ~= bf then return af < bf end
    local ar = rec_idx[a.rel] or math.huge
    local br = rec_idx[b.rel] or math.huge
    if ar ~= br then return ar < br end
    return a.rel < b.rel
  end)

  local choices = {}
  for _, r in ipairs(repos) do
    local prefix = fav_idx[r.rel] and '\u{2605} ' or (rec_idx[r.rel] and '' or '  ')
    table.insert(choices, { id = r.path, label = prefix .. r.rel })
  end
  return choices
end

local function push_recent(rel)
  local cfg = load_repos_cfg()
  local next = { rel }
  for _, r in ipairs(cfg.recents) do
    if r ~= rel and #next < REPOS_MAX_RECENTS then next[#next+1] = r end
  end
  cfg.recents = next
  save_repos_cfg(cfg)
end

local function launch_repo(win, pane, repo)
  push_recent(repo.rel)
  -- Open as a new tab in the CURRENT workspace so Alt+W/S can cycle back.
  -- The tab title is set to the repo's relative path for easy identification.
  win:perform_action(
    act.SpawnCommandInNewTab {
      cwd   = repo.path,
      label = repo.rel,
    },
    pane
  )
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
config.keys = {

  -- ── Pane navigation (A/D horizontal only) ────────────────────────────
  { key = 'a', mods = 'ALT', action = act.ActivatePaneDirection 'Left'  },
  { key = 'd', mods = 'ALT', action = act.ActivatePaneDirection 'Right' },

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
  { key = 'c', mods = 'ALT', action = act.SplitHorizontal { domain = 'CurrentPaneDomain' } },
  { key = 'v', mods = 'ALT', action = act.SplitVertical   { domain = 'CurrentPaneDomain' } },
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
          -- Strip the visual prefix (★ or leading spaces) to recover rel
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

  -- ── Help: persistent keymap pane (Alt+X to close) ────────────────────
  { key = '/', mods = 'ALT',
    action = wezterm.action_callback(show_keymap) },
}

-- ── Scrollback / defaults ─────────────────────────────────────────────────────
config.scrollback_lines  = 10000
config.default_workspace = 'default'

return config
