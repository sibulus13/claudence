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
$cwd         = if ($data -and $data.cwd) { [string]$data.cwd } elseif ($env:PWD) { $env:PWD } else { (Get-Location).Path }

# Refresh elapsed-time file (Stop sound hook reads this)
$ts_file = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), 'claude_start.txt')
[System.DateTime]::UtcNow.Ticks | Set-Content $ts_file

$log_dir      = "$HOME\.claude\telemetry\sessions"
$session_file = Join-Path $log_dir "$session_id.jsonl"
$state_file   = "$HOME\.claude\telemetry\state-$session_id.json"

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

# Track cwd so the recall viewer can scope themes to this repo
if ($state.PSObject.Properties['cwd']) { $state.cwd = $cwd } else { $state | Add-Member -NotePropertyName 'cwd' -NotePropertyValue $cwd }

# --- Recent distinct themes (ZERO-TOKEN, reverse-chronological, max 3) ---
# A "different thing" = a direction change. The classifier already labels that as 'override'
# (and the session's first prompt as 'first_prompt'). So: push a new theme on those;
# follow-ups/additions continue the current theme (bump turn count, keep the anchor label).
$theme_label = (($prompt_text -split "`n") | Where-Object { $_.Trim() -ne '' } | Select-Object -First 1)
if ($null -eq $theme_label) { $theme_label = '' }
$theme_label = $theme_label.Trim()
if ($theme_label.Length -gt 60) { $theme_label = $theme_label.Substring(0, 60).TrimEnd() + '...' }

if (-not $state.PSObject.Properties['themes']) { $state | Add-Member -NotePropertyName 'themes' -NotePropertyValue @() }
$themes = [System.Collections.Generic.List[object]]::new()
foreach ($t in @($state.themes)) { if ($t) { $themes.Add($t) } }

$is_new = ($classification -eq 'override') -or ($classification -eq 'first_prompt') -or ($themes.Count -eq 0)
# Topic-shift safety net (zero-token): if not already flagged new and not a mid-run
# addition, start a new theme when the prompt shares little vocabulary with the current
# theme. Catches genuine new scopes the classifier didn't label as an explicit override.
if (-not $is_new -and $classification -ne 'addition' -and $themes.Count -gt 0 -and $theme_label -ne '') {
    $cur = @(($themes[0].label).ToLower() -split '\W+' | Where-Object { $_.Length -gt 2 })
    $new = @($theme_label.ToLower()       -split '\W+' | Where-Object { $_.Length -gt 2 })
    if ($new.Count -gt 0 -and $cur.Count -gt 0) {
        $inter = @($cur | Where-Object { $new -contains $_ }).Count
        $union = @($cur + $new | Select-Object -Unique).Count
        $jac   = if ($union -gt 0) { $inter / $union } else { 0 }
        if ($jac -lt 0.2) { $is_new = $true }
    }
}
if ($is_new -and $theme_label -ne '') {
    $themes.Insert(0, [PSCustomObject]@{ label = $theme_label; ts = (Get-Date -Format 'o'); turns = 1 })
    while ($themes.Count -gt 3) { $themes.RemoveAt(3) }
} elseif ($themes.Count -gt 0) {
    $themes[0].turns = [int]$themes[0].turns + 1
}
$state.themes = $themes.ToArray()

$state | ConvertTo-Json -Depth 5 | Set-Content $state_file

# Signal that Claude is now running (statusline spinner reads this) — per-session
"$([datetime]::UtcNow.ToString('o'))" | Set-Content "$HOME\.claude\telemetry\running-$session_id.flag"

# Opportunistic cleanup so per-session files don't accumulate:
#   - state files older than 7 days (ended sessions)
#   - running flags older than 6 hours (crashed sessions that never cleared → stuck spinner)
Get-ChildItem "$HOME\.claude\telemetry\state-*.json" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
    Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem "$HOME\.claude\telemetry\running-*.flag" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddHours(-6) } |
    Remove-Item -Force -ErrorAction SilentlyContinue
