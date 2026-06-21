# log-prompt.ps1
# Fires on UserPromptSubmit (synchronous — must complete before Claude responds).
# Classifies each prompt using lib/classification.ps1 and updates session state.
#
# Classifications:
#   first_prompt  — no prior events in session
#   followup      — clean next step after Claude stopped
#   addition      — user injects context (mid-run OR additive language post-stop)
#   override      — user replaces the current direction entirely
#
# Friction scores (applied in analyze-session.ps1):
#   override +3    addition +1    followup/first_prompt 0

. "$PSScriptRoot\lib\classification.ps1"

$rawInput = [Console]::In.ReadToEnd()
$data = try { $rawInput | ConvertFrom-Json -ErrorAction Stop } catch { $null }

$session_id  = if ($data -and $data.session_id) { $data.session_id } else { 'unknown' }
$prompt_text = if ($data -and $data.prompt)      { [string]$data.prompt } else { '' }
$cwd         = if ($env:PWD) { $env:PWD } else { (Get-Location).Path }

# Refresh elapsed-time file (Stop sound hook reads this)
$ts_file = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), 'claude_start.txt')
[System.DateTime]::UtcNow.Ticks | Set-Content $ts_file

$log_dir      = "C:\Users\Michael\.claude\telemetry\sessions"
$session_file = Join-Path $log_dir "$session_id.jsonl"
$state_file   = "C:\Users\Michael\.claude\telemetry\current-session.json"

if (-not (Test-Path $log_dir)) { New-Item $log_dir -ItemType Directory -Force | Out-Null }

# --- Load prior events and classify ---
$prior = if (Test-Path $session_file) {
    Get-Content $session_file -ErrorAction SilentlyContinue |
        Where-Object { $_ -ne '' } |
        ForEach-Object { try { $_ | ConvertFrom-Json -ErrorAction Stop } catch { $null } } |
        Where-Object { $_ -ne $null }
} else { @() }

$classification = Get-PromptClassification $prompt_text $prior

# --- Append to session JSONL ---
$prompt_excerpt = if ($prompt_text.Length -gt 1000) { $prompt_text.Substring(0, 1000) + '...' } else { $prompt_text }

$entry = [PSCustomObject]@{
    ts             = (Get-Date -Format 'o')
    session_id     = $session_id
    event          = 'prompt'
    classification = $classification
    prompt_chars   = $prompt_text.Length
    prompt_text    = $prompt_excerpt
    cwd            = $cwd
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

$state.prompts += 1
switch ($classification) {
    'override'        { $state.overrides        += 1 }
    'addition'        { $state.additions        += 1 }
    'denial_context'  { $state.denial_contexts  += 1 }
}

$state | ConvertTo-Json | Set-Content $state_file

# Signal that Claude is now running (statusline spinner reads this)
"$([datetime]::UtcNow.ToString('o'))" | Set-Content "C:\Users\Michael\.claude\telemetry\running.flag"
