# check-keymap-conflicts.ps1 — validate the NEXUS terminal keymap against
# itself and against hotkeys that other software steals before WezTerm sees them.
#
# WHY THIS EXISTS
# ---------------
# Alt+R (rename tab, terminal.lua) silently stopped working because NVIDIA's
# overlay ("NVIDIA Share") registers Alt+R as a GLOBAL low-level keyboard hook
# for its performance overlay / recording toggle. A global hook intercepts the
# keystroke at the OS level, so WezTerm never receives a key event at all —
# there is no error, no log line, nothing to grep. The binding simply does
# nothing, and the only signal is a human noticing months later.
#
# That failure mode is invisible by construction, so it needs a mechanical
# check. This script is that check.
#
# SEVERITY MODEL
# --------------
#   CONFLICT (exit 1) — the combo is bound in terminal.lua AND its thief is
#                       running right now, or is a permanent Windows shell
#                       reservation. The key is dead on this machine today.
#   WARNING  (exit 0) — the thief is known but not currently running (app
#                       closed, or not installed on this machine). The binding
#                       works now and breaks the moment that app launches.
#   DUPLICATE (exit 1) — the same combo is bound twice inside config.keys.
#                        WezTerm silently takes the LAST one, so the earlier
#                        binding is dead code that reads as live.
#
# Usage:  powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/check-keymap-conflicts.ps1
#         -Quiet   suppress the OK listing, print only problems
# Exit:   0 = clean (warnings allowed), 1 = conflict or duplicate

[CmdletBinding()]
param(
    [string]$ConfigPath = (Join-Path $env:USERPROFILE '.claude\terminal.lua'),
    [string]$CheatSheetPath = (Join-Path $env:USERPROFILE '.claude\keymap.txt'),
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Reserved-hotkey table — the single source of truth for "who else wants this".
#
# Detect field semantics:
#   Process = <name>  -> ACTIVE only while that process is running
#   Always  = $true   -> permanent OS reservation, always ACTIVE
#
# Only combos that can actually be defended belong here. A speculative entry
# ("Discord might bind this") turns the gate into noise, and a gate that cries
# wolf gets ignored — which is the exact outcome this script exists to prevent.
# ---------------------------------------------------------------------------
$Reserved = @(
    @{ Combo = 'ALT+r'; Owner = 'NVIDIA overlay - perf overlay / recording toggle'
       Process = 'NVIDIA Share'
       Fix = 'NVIDIA App > Settings > Keyboard shortcuts (or GeForce Experience > Settings > In-Game Overlay > Keyboard shortcuts) - rebind or disable the overlay' }

    @{ Combo = 'ALT+z'; Owner = 'NVIDIA overlay - open overlay'
       Process = 'NVIDIA Share'
       Fix = 'Same NVIDIA shortcut panel as Alt+R - both come from the in-game overlay switch' }

    @{ Combo = 'ALT+f1'; Owner = 'NVIDIA overlay - screenshot'
       Process = 'NVIDIA Share'
       Fix = 'NVIDIA shortcut panel' }

    @{ Combo = 'ALT+f9'; Owner = 'NVIDIA overlay - start/stop record'
       Process = 'NVIDIA Share'
       Fix = 'NVIDIA shortcut panel' }

    @{ Combo = 'ALT+f10'; Owner = 'NVIDIA overlay - instant replay save'
       Process = 'NVIDIA Share'
       Fix = 'NVIDIA shortcut panel' }

    @{ Combo = 'ALT+tab';    Owner = 'Windows shell - task switcher';  Always = $true
       Fix = 'Not reclaimable - pick a different key' }
    @{ Combo = 'ALT+escape'; Owner = 'Windows shell - cycle windows';  Always = $true
       Fix = 'Not reclaimable - pick a different key' }
    @{ Combo = 'ALT+space';  Owner = 'Windows shell - window menu';    Always = $true
       Fix = 'Not reclaimable - pick a different key' }
    @{ Combo = 'ALT+f4';     Owner = 'Windows shell - close window';   Always = $true
       Fix = 'Not reclaimable - pick a different key' }
)

# ---------------------------------------------------------------------------
# Parse terminal.lua
#
# Only entries carrying BOTH `key =` and `mods =` are global bindings in
# config.keys. Entries inside config.key_tables (the Alt+B split submenu) have
# no `mods` field and are deliberately excluded: they are only live while their
# key table is pushed, so they cannot collide with a global hotkey.
# ---------------------------------------------------------------------------
function Get-LuaBindings {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        throw "terminal.lua not found at $Path"
    }

    $bindings = @()
    $lineNo = 0
    foreach ($line in (Get-Content -LiteralPath $Path)) {
        $lineNo++
        # Skip commented-out bindings - a Lua comment is documentation, not config.
        if ($line -match '^\s*--') { continue }

        $m = [regex]::Match($line, "key\s*=\s*'([^']+)'\s*,\s*mods\s*=\s*'([^']+)'")
        if (-not $m.Success) { continue }

        $key  = $m.Groups[1].Value
        $mods = $m.Groups[2].Value

        # Normalise: mods sorted + uppercased, key lowercased.
        # ALT+w and ALT|SHIFT+w stay DISTINCT because SHIFT is part of the mod
        # set - lowercasing the key alone would wrongly merge Alt+w with Alt+Shift+W.
        $modSet = ($mods.ToUpper() -split '\|' | Sort-Object) -join '|'
        $combo  = "$modSet+$($key.ToLower())"

        # Best-effort action label for the report.
        $action = ''
        $am = [regex]::Match($line, 'action\s*=\s*(.+?)\s*$')
        if ($am.Success) { $action = ($am.Groups[1].Value -replace '[,{]\s*$', '').Trim() }

        $bindings += [pscustomobject]@{
            Combo  = $combo
            Key    = $key
            Mods   = $modSet
            Line   = $lineNo
            Action = $action
        }
    }
    return $bindings
}

# ---------------------------------------------------------------------------
# Cheat-sheet coverage (Alt+/ overlay, keymap.txt)
#
# The overlay is the surface you actually consult, so a key printed there that
# isn't bound is worse than an undocumented binding: you press it, nothing
# happens, and the doc says it should work - the same "silently does nothing"
# signature as a stolen hotkey, from a different cause. This caught the Lua
# header comment advertising "V=split-V" with no Alt+V binding anywhere.
#
# Deliberately conservative: only SINGLE-LETTER key cells (the \e[97mX\e[0m
# pattern) are checked. Multi-key cells - "A / D", "1 - 5", "[ / ]", the shifted
# "^W ^S" pair - are skipped rather than parsed with a fragile heuristic. A
# check that guesses produces false positives, and a gate that cries wolf is
# the thing this script exists to avoid becoming.
# ---------------------------------------------------------------------------
function Get-UndocumentedCheatSheetKeys {
    param([string]$Path, [object[]]$Bindings)

    if (-not (Test-Path $Path)) { return @() }

    $bound = @{}
    foreach ($b in $Bindings) { if ($b.Mods -eq 'ALT') { $bound[$b.Key.ToLower()] = $true } }

    # -Raw returns $null (not '') for a zero-byte file, and regex on $null throws.
    # An empty cheat sheet documents nothing, so it has no orphans to report.
    $raw = Get-Content -LiteralPath $Path -Raw
    if ([string]::IsNullOrEmpty($raw)) { return @() }

    $esc = [char]27
    $orphans = @()
    foreach ($m in [regex]::Matches($raw, "$esc\[97m([A-Za-z])$esc\[0m")) {
        $k = $m.Groups[1].Value.ToLower()
        if (-not $bound.ContainsKey($k)) { $orphans += $k }
    }
    return ($orphans | Select-Object -Unique)
}

# ---------------------------------------------------------------------------
# Is a reservation's owner live on this machine right now?
# ---------------------------------------------------------------------------
function Test-OwnerActive {
    param([hashtable]$Reservation)

    if ($Reservation.Always) { return $true }
    if (-not $Reservation.Process) { return $false }
    $p = Get-Process -Name $Reservation.Process -ErrorAction SilentlyContinue
    return [bool]$p
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
$bindings = Get-LuaBindings -Path $ConfigPath

$conflicts  = @()
$warnings   = @()
$duplicates = @()

# --- Check 1: duplicate bindings inside config.keys ---
# WezTerm keeps the LAST definition for a combo. An earlier duplicate is dead
# code that still reads as a live binding when you scan the file.
foreach ($g in ($bindings | Group-Object Combo | Where-Object { $_.Count -gt 1 })) {
    $lines = ($g.Group | ForEach-Object { $_.Line }) -join ', '
    $duplicates += [pscustomobject]@{
        Combo = $g.Name
        Detail = "bound $($g.Count)x at lines $lines - WezTerm keeps the last; the earlier one(s) are dead"
    }
}

# --- Check 3: cheat sheet advertises a key that isn't bound ---
$orphanKeys = Get-UndocumentedCheatSheetKeys -Path $CheatSheetPath -Bindings $bindings

# --- Check 2: collisions with hotkeys owned by other software ---
foreach ($b in $bindings) {
    foreach ($r in $Reserved) {
        if ($r.Combo.ToUpper() -ne $b.Combo.ToUpper()) { continue }

        $rec = [pscustomobject]@{
            Combo = $b.Combo
            Line  = $b.Line
            Owner = $r.Owner
            Fix   = $r.Fix
        }
        if (Test-OwnerActive -Reservation $r) { $conflicts += $rec } else { $warnings += $rec }
    }
}

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
Write-Host ''
Write-Host "NEXUS keymap conflict check" -ForegroundColor Cyan
Write-Host "  config:   $ConfigPath"
Write-Host "  bindings: $($bindings.Count) global (config.keys)"
Write-Host ''

if ($duplicates.Count -gt 0) {
    Write-Host "DUPLICATE  $($duplicates.Count) combo(s) bound more than once" -ForegroundColor Red
    foreach ($d in $duplicates) {
        Write-Host ("  {0,-16} {1}" -f $d.Combo, $d.Detail) -ForegroundColor Red
    }
    Write-Host ''
}

if ($conflicts.Count -gt 0) {
    Write-Host "CONFLICT   $($conflicts.Count) binding(s) stolen by software running NOW" -ForegroundColor Red
    foreach ($c in $conflicts) {
        Write-Host ("  {0,-16} line {1,-5} <- {2}" -f $c.Combo, $c.Line, $c.Owner) -ForegroundColor Red
        Write-Host ("  {0,-16} fix: {1}" -f '', $c.Fix) -ForegroundColor DarkGray
    }
    Write-Host ''
}

if ($warnings.Count -gt 0) {
    Write-Host "WARNING    $($warnings.Count) binding(s) collide with software not currently running" -ForegroundColor Yellow
    foreach ($w in $warnings) {
        Write-Host ("  {0,-16} line {1,-5} <- {2}" -f $w.Combo, $w.Line, $w.Owner) -ForegroundColor Yellow
    }
    Write-Host ''
}

if ($orphanKeys.Count -gt 0) {
    Write-Host "ORPHAN     $($orphanKeys.Count) key(s) on the Alt+/ cheat sheet are not bound" -ForegroundColor Red
    foreach ($k in $orphanKeys) {
        Write-Host ("  {0,-16} documented in keymap.txt, absent from config.keys" -f "ALT+$k") -ForegroundColor Red
    }
    Write-Host ''
}

$failed = $conflicts.Count + $duplicates.Count + $orphanKeys.Count
if (-not $Quiet -and $failed -eq 0) {
    Write-Host "OK         no active conflicts, no duplicates, cheat sheet matches config" -ForegroundColor Green
    Write-Host ''
}

if ($failed -gt 0) { exit 1 }
exit 0
