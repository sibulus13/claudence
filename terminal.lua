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
  window:set_right_status(wezterm.format {
    { Foreground = { Color = '#585b70' } },
    { Text = os.date('%H:%M') .. '   Alt+/  keys  ' },
  })
end)

-- ── Nexus sync: write active workspace on focus / tab change ─────────────────
local function write_active(window, pane)
  if not window:is_focused() then return end
  local workspace = window:active_workspace()
  local cwd_obj   = pane:get_current_working_dir()
  local cwd       = cwd_obj and cwd_obj.file_path or ''
  if cwd:match('^/[A-Za-z]:') then cwd = cwd:sub(2) end
  cwd = cwd:gsub('\\', '/')
  local path = wezterm.home_dir .. '/.claude/workspaces/active.json'
  local f = io.open(path, 'w')
  if f then
    f:write(string.format(
      '{"workspace":"%s","cwd":"%s","updatedAt":"%s"}\n',
      workspace:gsub('"', '\\"'),
      cwd:gsub('"', '\\"'),
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
local REPO_DIR = 'D:/repo'

local function keymap_args()
  if wezterm.target_triple:find('windows') then
    local f = keymap_file:gsub('/', '\\')
    return {
      'powershell.exe', '-NoProfile', '-Command',
      '[Console]::OutputEncoding=[Text.Encoding]::UTF8; ' ..
      'while ($true) { Clear-Host; Get-Content "' .. f .. '"; Start-Sleep -Seconds 86400 }',
    }
  end
  return { 'bash', '-c',
    'while true; do clear; cat "' .. keymap_file .. '"; sleep 86400; done' }
end

wezterm.on('gui-startup', function(cmd)
  -- cmd is non-nil when WezTerm was launched with an explicit command;
  -- in that case honour it and only maximise.
  if cmd then
    local _, _, window = wezterm.mux.spawn_window(cmd)
    window:gui_window():maximize()
    return
  end

  -- Default layout: keys tab first, then a shell in D:/repo
  local _, _, window = wezterm.mux.spawn_window({
    args = keymap_args(),
    cwd  = REPO_DIR,
  })
  -- Second tab: plain shell, lands in D:/repo
  window:spawn_tab({ cwd = REPO_DIR })
  -- Stay on tab 1 (keys) so it's the first thing the user sees
  window:gui_window():maximize()
end)

wezterm.on('window-focus-changed', write_active)
wezterm.on('window-activated',     write_active)

-- ── Help: opens a persistent "keys" tab showing the keymap ──────────────────
-- Uses SpawnCommandInNewTab (supported in all WezTerm versions) rather than
-- SplitPane{command=...} which requires a newer build. The keymap uses ASCII
-- art only — no Unicode box chars — so PowerShell reads it without encoding
-- issues regardless of system locale.
local keymap_file = wezterm.home_dir .. '/.claude/keymap.txt'

local function show_keymap(win, pane)
  win:perform_action(
    act.SpawnCommandInNewTab { args = keymap_args() },
    pane
  )
end

-- ── Keybindings ───────────────────────────────────────────────────────────────
--
--  Nominal usage: 1–3 horizontal panes per tab, 1–3 tabs per workspace.
--
--  PANE NAV   A=left  D=right       (horizontal only — panes are side by side)
--  TAB NAV    W=prev  S=next        (W/S traverse the tab list up/down)
--  PANE OPS   Z=zoom  X=close  C=split-H  V=split-V  T=new-tab
--  WORKSPACES F=fuzzy  R=rename  [/]=cycle
--  HELP       /=persistent overlay (Alt+X to close)
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
  { key = 'f', mods = 'ALT',
    action = act.ShowLauncherArgs { flags = 'WORKSPACES|FUZZY' } },
  { key = 'r', mods = 'ALT',
    action = act.PromptInputLine {
      description = 'Rename workspace:',
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
