# log-tool-done.ps1
# Fires on PostToolUse (all tools). Logs completions so analyze-session.ps1
# can correlate them with preceding PermissionRequest events to infer
# approve vs deny decisions per turn.

$rawInput = [Console]::In.ReadToEnd()
$data = try { $rawInput | ConvertFrom-Json -ErrorAction Stop } catch { $null }
if (-not $data) { exit 0 }

$session_id = if ($data.session_id) { $data.session_id } else { 'unknown' }
$tool_name  = if ($data.tool_name)  { $data.tool_name  } else { 'unknown' }

$input_preview = ''
if ($data.tool_input) {
    if ($data.tool_input.command)        { $input_preview = $data.tool_input.command.Substring(0, [Math]::Min(80, $data.tool_input.command.Length)) }
    elseif ($data.tool_input.file_path)  { $input_preview = $data.tool_input.file_path }
    elseif ($data.tool_input.pattern)    { $input_preview = $data.tool_input.pattern }
    elseif ($data.tool_input.query)      { $input_preview = $data.tool_input.query }
}

$log_dir = "C:\Users\Michael\.claude\telemetry\sessions"
if (-not (Test-Path $log_dir)) { New-Item $log_dir -ItemType Directory -Force | Out-Null }

$entry = [PSCustomObject]@{
    ts            = (Get-Date -Format 'o')
    session_id    = $session_id
    event         = 'tool_done'
    tool          = $tool_name
    input_preview = $input_preview
} | ConvertTo-Json -Compress

Add-Content -Path (Join-Path $log_dir "$session_id.jsonl") -Value $entry
