# keymap.tests.ps1
# Regression tests for the NEXUS terminal keymap and its conflict checker.
#
# Two things are under test, and the second matters more than the first:
#
#   1. The LIVE config is clean (no stolen keys, no duplicates, cheat sheet
#      matches). This is the state assertion.
#   2. The CHECKER actually fails when it should. A guard that has only ever
#      returned green is indistinguishable from a guard that cannot fail —
#      the failure mode is the whole reason Alt+R went unnoticed. Each check
#      therefore gets a synthetic BAD config proving it trips.
#
# The negative cases use Alt+Tab (a permanent Windows-shell reservation) rather
# than Alt+R (NVIDIA), so they are deterministic on any machine regardless of
# which apps happen to be running.
#
# Run via: tests/run-tests.ps1
# Or manually: Invoke-Pester tests/keymap.tests.ps1 -Output Detailed

BeforeAll {
    $script:ClaudeRoot = "$HOME\.claude"
    $script:Checker    = "$script:ClaudeRoot\scripts\check-keymap-conflicts.ps1"
    $script:LuaConfig  = "$script:ClaudeRoot\terminal.lua"
    $script:CheatSheet = "$script:ClaudeRoot\keymap.txt"
    $script:TmpDir     = Join-Path $env:TEMP "keymap-tests-$PID"

    New-Item -ItemType Directory -Force -Path $script:TmpDir | Out-Null

    # Run the checker out-of-process: it calls `exit`, which would terminate the
    # Pester host if dot-sourced or called in-process.
    function script:Invoke-Checker {
        param([string]$Config, [string]$Sheet)
        if (-not $Sheet) { $Sheet = Join-Path $script:TmpDir 'empty-sheet.txt' }
        if (-not (Test-Path $Sheet)) { Set-Content -LiteralPath $Sheet -Value '' -NoNewline }
        $out = & powershell.exe -NoProfile -ExecutionPolicy Bypass `
                   -File $script:Checker -ConfigPath $Config -CheatSheetPath $Sheet 2>&1
        return [pscustomobject]@{ Output = ($out -join "`n"); Exit = $LASTEXITCODE }
    }

    function script:New-LuaConfig {
        param([string]$Name, [string]$Body)
        $path = Join-Path $script:TmpDir "$Name.lua"
        Set-Content -LiteralPath $path -Value $Body -Encoding UTF8
        return $path
    }
}

AfterAll {
    if (Test-Path $script:TmpDir) { Remove-Item $script:TmpDir -Recurse -Force -ErrorAction SilentlyContinue }
}

# ---------------------------------------------------------------------------

Describe "Keymap checker: detects problems (negative cases)" {

    It "FAILS when a binding collides with a permanent Windows reservation" {
        $cfg = script:New-LuaConfig -Name 'stolen' -Body @"
config.keys = {
  { key = 'Tab', mods = 'ALT', action = act.SpawnTab 'CurrentPaneDomain' },
}
"@
        $r = script:Invoke-Checker -Config $cfg
        $r.Exit   | Should -Be 1
        $r.Output | Should -Match 'CONFLICT'
        $r.Output | Should -Match 'Windows shell'
    }

    It "FAILS when the same combo is bound twice (WezTerm silently keeps the last)" {
        $cfg = script:New-LuaConfig -Name 'dupe' -Body @"
config.keys = {
  { key = 'y', mods = 'ALT', action = act.TogglePaneZoomState },
  { key = 'y', mods = 'ALT', action = act.CloseCurrentPane { confirm = true } },
}
"@
        $r = script:Invoke-Checker -Config $cfg
        $r.Exit   | Should -Be 1
        $r.Output | Should -Match 'DUPLICATE'
    }

    It "FAILS when the cheat sheet advertises a key that is not bound" {
        $cfg = script:New-LuaConfig -Name 'orphan' -Body @"
config.keys = {
  { key = 'y', mods = 'ALT', action = act.TogglePaneZoomState },
}
"@
        # A cheat-sheet cell for Alt+J, which the config above never binds.
        $esc   = [char]27
        $sheet = Join-Path $script:TmpDir 'orphan-sheet.txt'
        Set-Content -LiteralPath $sheet -Value "$esc[97mJ$esc[0m   do a thing" -Encoding UTF8
        $r = script:Invoke-Checker -Config $cfg -Sheet $sheet
        $r.Exit   | Should -Be 1
        $r.Output | Should -Match 'ORPHAN'
    }

    It "does NOT flag key_table entries, which are scoped and cannot collide globally" {
        # Entries inside config.key_tables carry no `mods` field. Alt+Tab here is
        # a sub-mode key, live only while the table is pushed — not a global hook.
        $cfg = script:New-LuaConfig -Name 'keytable' -Body @"
config.key_tables = {
  split_dir = {
    { key = 'Tab', action = act.SplitPane { direction = 'Right' } },
  },
}
config.keys = {
  { key = 'y', mods = 'ALT', action = act.TogglePaneZoomState },
}
"@
        $r = script:Invoke-Checker -Config $cfg
        $r.Exit | Should -Be 0
    }

    It "does NOT flag a commented-out binding" {
        $cfg = script:New-LuaConfig -Name 'commented' -Body @"
config.keys = {
  -- { key = 'Tab', mods = 'ALT', action = act.SpawnTab 'CurrentPaneDomain' },
  { key = 'y', mods = 'ALT', action = act.TogglePaneZoomState },
}
"@
        $r = script:Invoke-Checker -Config $cfg
        $r.Exit | Should -Be 0
    }
}

# ---------------------------------------------------------------------------

Describe "Keymap: live config state" {

    It "passes the conflict checker with no active conflicts" {
        $r = script:Invoke-Checker -Config $script:LuaConfig -Sheet $script:CheatSheet
        if ($r.Exit -ne 0) { Write-Host $r.Output }
        $r.Exit | Should -Be 0
    }

    It "binds no hotkey owned by the NVIDIA overlay" {
        # Regression lock for the 2026-08-08 incident: Alt+R (rename tab) and
        # Alt+Z (zoom) were both consumed by NVIDIA Share's global keyboard hook,
        # so WezTerm received no key event and the bindings silently did nothing.
        $lua = Get-Content -LiteralPath $script:LuaConfig | Where-Object { $_ -notmatch '^\s*--' }
        foreach ($k in @('r', 'z')) {
            ($lua -join "`n") | Should -Not -Match "key\s*=\s*'$k'\s*,\s*mods\s*=\s*'ALT'"
        }
    }

    It "still binds rename-tab and zoom-pane under their new keys" {
        $lua = (Get-Content -LiteralPath $script:LuaConfig) -join "`n"
        $lua | Should -Match "key\s*=\s*'m'\s*,\s*mods\s*=\s*'ALT'"   # zoom (maximize)
        $lua | Should -Match "key\s*=\s*'l'\s*,\s*mods\s*=\s*'ALT'"   # rename (label)
    }

    It "loads in WezTerm without a config error" {
        # The regex checker reads the file as text; only WezTerm proves the Lua
        # actually parses and the key table is well formed.
        $wez = Get-Command wezterm -ErrorAction SilentlyContinue
        if (-not $wez) { Set-ItResult -Skipped -Because 'wezterm is not on PATH'; return }

        $out = & $wez.Source --config-file $script:LuaConfig show-keys 2>&1
        $LASTEXITCODE | Should -Be 0
        ($out -join "`n") | Should -Match 'ALT\s+m\s+->\s+TogglePaneZoomState'
    }
}
