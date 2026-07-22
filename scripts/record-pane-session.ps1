# record-pane-session.ps1 — bind a WezTerm pane to the Claude session running
# in it, so terminal.lua can restore the EXACT conversation on restart
# (`claude --resume <id>`) instead of guessing the cwd's most-recent one
# (`claude --continue`). The guess is wrong whenever a repo holds more than one
# session — which is the norm here (some repos have 100+).
#
# Wired into SessionStart (fires on startup / resume / clear — every point the
# session id for a pane is established or changes). The session id + cwd arrive
# as the hook's JSON payload on stdin; the pane comes from $WEZTERM_PANE,
# inherited from the pane's environment (same signal notify-attention.ps1 uses).
# Writes one file per pane: ~/.claude/workspaces/pane-sessions/pane-<pane>.json.
# No pane (headless / cron / cloud agent) => nothing to restore into, so skip.
$ErrorActionPreference = 'SilentlyContinue'

# --- resolve session id + cwd from the hook payload (stdin JSON) -------------
$sid = ''; $cwd = ''
try {
  $raw = [Console]::In.ReadToEnd()
  if ($raw) {
    $o   = ConvertFrom-Json $raw
    $sid = [string]$o.session_id
    $cwd = [string]$o.cwd
  }
} catch {}

$pane = $env:WEZTERM_PANE
if (-not $sid -or -not $pane) { return }   # headless, or no session id: nothing to bind
if ($cwd) { $cwd = ($cwd -replace '\\', '/').TrimEnd('/') }

$dir = Join-Path $env:USERPROFILE '.claude/workspaces/pane-sessions'
New-Item -ItemType Directory -Force -Path $dir | Out-Null

$rec = [ordered]@{
  session = $sid
  cwd     = $cwd
  pane    = [int]$pane
  ts      = [int][DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
} | ConvertTo-Json -Compress
# BOM-less UTF8 so wezterm.json_parse is happy (matches notify-attention.ps1).
[System.IO.File]::WriteAllText((Join-Path $dir "pane-$pane.json"), $rec, (New-Object System.Text.UTF8Encoding $false))

# Reap orphaned mappings (panes closed long ago). 7 days is generous: an active
# pane rewrites its file on every SessionStart, so only truly dead panes expire —
# and a missing file just degrades restore to `claude --continue`, never a crash.
$cutoff = (Get-Date).AddDays(-7)
Get-ChildItem $dir -Filter 'pane-*.json' -ErrorAction SilentlyContinue |
  Where-Object { $_.LastWriteTime -lt $cutoff } | Remove-Item -Force -ErrorAction SilentlyContinue
