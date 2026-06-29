# notify-attention.ps1 — cross-workspace "agent needs you" signal.
#
# Wired into the Stop and PermissionRequest hooks. Two jobs:
#   1. Drop a per-SESSION flag file that terminal.lua's status bar / tab bar
#      reads, so you can see WHICH repo alerted even when its tab is off-screen.
#      Keyed by cwd + session id so two sessions in the same repo stay distinct
#      (clearing one never clears the other).
#   2. Play the event sound — but THROTTLED to at most once per reason per
#      $window seconds across ALL sessions, so N sessions finishing at once
#      don't produce a ding-storm. (The visual flags are never throttled.)
#
# The agent's project dir + session id arrive in the hook's JSON payload on
# stdin. No Windows toast is raised here — the signal is in-terminal only.
param(
  [string]$Reason = 'stop',
  [string]$Sound  = 'ring-half.wav',
  [switch]$Silent          # flag-only: write the attention flag, play no sound
)

$ErrorActionPreference = 'SilentlyContinue'

# --- resolve cwd + session id from the hook payload (stdin JSON) --------------
$cwd = ''; $sid = ''
try {
  $raw = [Console]::In.ReadToEnd()
  if ($raw) {
    $o   = ConvertFrom-Json $raw
    $cwd = [string]$o.cwd
    $sid = [string]$o.session_id
  }
} catch {}

$wsDir = Join-Path $env:USERPROFILE '.claude/workspaces'

# --- drop the flag file -------------------------------------------------------
# Keyed by the WezTerm pane the session runs in ($WEZTERM_PANE, inherited from
# the pane's environment). The status bar matches a flag to its TAB by this pane
# id — reliable even when the pane's reported cwd is stale (PowerShell emits no
# OSC-7 while Claude's TUI is foreground). No pane => headless / cron / cloud
# agent with nowhere to navigate to, so we skip the flag. cwd/repo are kept only
# for the chip label.
$pane = $env:WEZTERM_PANE
if ($cwd) { $cwd = ($cwd -replace '\\', '/').TrimEnd('/') }

# Never flag a session running in the system temp dir / scratchpad — it's not a
# workspace anyone navigates to, and shouldn't light a tab.
$tmpNorm = ($env:TEMP -replace '\\', '/').TrimEnd('/').ToLower()
$inTemp  = ($cwd -and $tmpNorm -and ($cwd.ToLower() -eq $tmpNorm -or $cwd.ToLower().StartsWith("$tmpNorm/")))

if ($cwd -and $pane -and -not $inTemp) {
  $repo = ($cwd -split '/')[-1]
  $dir  = Join-Path $wsDir 'attention'
  New-Item -ItemType Directory -Force -Path $dir | Out-Null

  $flag = [ordered]@{
    cwd     = $cwd
    repo    = $repo
    reason  = $Reason
    session = $sid
    pane    = [int]$pane
    ts      = [int][DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
  } | ConvertTo-Json -Compress
  # One file per pane (BOM-less UTF8 so wezterm.json_parse is happy). A pane runs
  # one Claude session at a time; re-stops overwrite. Orphans (closed panes) are
  # reaped by the status bar.
  [System.IO.File]::WriteAllText((Join-Path $dir "pane-$pane.json"), $flag, (New-Object System.Text.UTF8Encoding $false))
}

# --- ding throttle: one sound per reason per $window seconds, shared across
#     every session via an on-disk stamp file (separate processes can't share
#     memory). Per-reason so a Stop chime never masks an urgent permission ding.
#     Skipped entirely in -Silent mode (Stop, where analyze-session.ps1 owns the
#     chime — see its matching throttle so the two never double up).
if (-not $Silent) {
  $window = 60
  $now    = [int][DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
  $stamp  = Join-Path $wsDir (".last-ding-" + ($Reason -replace '[^A-Za-z0-9]', '-'))
  $last   = 0
  try { $last = [int]((Get-Content $stamp -Raw).Trim()) } catch { $last = 0 }

  if (($now - $last) -ge $window) {
    [System.IO.File]::WriteAllText($stamp, "$now")
    $wav = Join-Path $env:USERPROFILE ".claude/sounds/$Sound"
    if (Test-Path $wav) { (New-Object System.Media.SoundPlayer $wav).PlaySync() }
  }
}
