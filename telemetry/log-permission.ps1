# log-permission.ps1
# Fires on PermissionRequest.
# Distinguishes first-time blocks from repeats:
#   perm_req        — first time this tool type needs approval this session (+1)
#   perm_req_repeat — same tool type blocked again (+2); should be in allow list by now

$rawInput = [Console]::In.ReadToEnd()
$data = try { $rawInput | ConvertFrom-Json -ErrorAction Stop } catch { $null }
if (-not $data) { exit 0 }

$session_id = if ($data.session_id) { $data.session_id } else { 'unknown' }
$tool_name  = if ($data.tool_name)  { $data.tool_name  } else { 'unknown' }
$cwd        = if ($env:PWD) { $env:PWD } else { (Get-Location).Path }

$input_preview = ''
if ($data.tool_input) {
    if ($data.tool_input.command)        { $input_preview = $data.tool_input.command.Substring(0, [Math]::Min(120, $data.tool_input.command.Length)) }
    elseif ($data.tool_input.file_path)  { $input_preview = $data.tool_input.file_path }
    elseif ($data.tool_input.pattern)    { $input_preview = $data.tool_input.pattern }
}

$log_dir      = "C:\Users\Michael\.claude\telemetry\sessions"
$session_file = Join-Path $log_dir "$session_id.jsonl"
$state_file   = "C:\Users\Michael\.claude\telemetry\current-session.json"

if (-not (Test-Path $log_dir)) { New-Item $log_dir -ItemType Directory -Force | Out-Null }

# --- Detect if this tool has been blocked before this session ---
$is_repeat = $false
if (Test-Path $session_file) {
    $prior_perms = Get-Content $session_file -ErrorAction SilentlyContinue |
        Where-Object { $_ -ne '' } |
        ForEach-Object { try { $_ | ConvertFrom-Json -ErrorAction Stop } catch { $null } } |
        Where-Object { $_ -ne $null -and $_.event -eq 'permission_req' -and $_.tool -eq $tool_name }
    $is_repeat = $prior_perms -and @($prior_perms).Count -gt 0
}

$event_type = if ($is_repeat) { 'perm_req_repeat' } else { 'perm_req' }

# --- Append to session JSONL ---
$entry = [PSCustomObject]@{
    ts            = (Get-Date -Format 'o')
    session_id    = $session_id
    event         = $event_type
    tool          = $tool_name
    input_preview = $input_preview
    cwd           = $cwd
} | ConvertTo-Json -Compress
Add-Content -Path $session_file -Value $entry

# --- Update status bar state ---
$state = if (Test-Path $state_file) {
    try { Get-Content $state_file -Raw | ConvertFrom-Json -ErrorAction Stop } catch { $null }
} else { $null }

if (-not $state -or $state.session_id -ne $session_id) {
    $state = [PSCustomObject]@{
        session_id      = $session_id
        prompts         = 0
        overrides       = 0
        additions       = 0
        denial_contexts = 0
        perm_reqs       = 0
        perm_repeats    = 0
        started_at      = (Get-Date -Format 'o')
    }
}

if ($is_repeat) { $state.perm_repeats += 1 } else { $state.perm_reqs += 1 }
$state | ConvertTo-Json | Set-Content $state_file
