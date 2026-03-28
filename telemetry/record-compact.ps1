# record-compact.ps1
# Fires on PostCompact. Captures the compaction summary so retrospection can
# reconstruct what happened across compaction boundaries within a session.
#
# Input JSON fields (PostCompact):
#   session_id   — current session UUID
#   summary      — the compaction summary text Claude generated
#   trigger      — "manual" or "auto"

$rawInput = [Console]::In.ReadToEnd()
$data = try { $rawInput | ConvertFrom-Json -ErrorAction Stop } catch { $null }
if (-not $data) { exit 0 }

$session_id = if ($data.session_id) { $data.session_id } else { 'unknown' }
$summary    = if ($data.summary)    { [string]$data.summary } else { '' }
$trigger    = if ($data.trigger)    { $data.trigger } else { 'unknown' }

$log_dir      = "C:\Users\Michael\.claude\telemetry\sessions"
$session_file = Join-Path $log_dir "$session_id.jsonl"

if (-not (Test-Path $log_dir)) { New-Item $log_dir -ItemType Directory -Force | Out-Null }

$entry = [PSCustomObject]@{
    ts         = (Get-Date -Format 'o')
    session_id = $session_id
    event      = 'compact'
    trigger    = $trigger
    summary    = $summary
} | ConvertTo-Json -Compress

Add-Content -Path $session_file -Value $entry
