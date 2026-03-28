# log-prompt.ps1
# Fires on UserPromptSubmit.
# Classifies each prompt based on two axes:
#   1. Timing context — was Claude still running? (last event = stop or not)
#   2. Prompt character — is this corrective or additive?
#
# Classifications:
#   first_prompt   — no prior events in session
#   followup       — Claude had finished (stop event preceded this), gap > 60s, OR
#                    the prompt is clearly additive even if gap < 60s
#   correction     — Claude had finished, gap < 60s, short/focused prompt
#   interrupt      — Claude was mid-run, short prompt (≤ 150 chars, ≤ 2 lines)
#                    → likely stopping or redirecting; high friction
#   enrichment     — Claude was mid-run, long or multi-topic prompt
#                    → intentionally adding context while work continues; low friction
#
# Friction scores (applied in analyze-session.ps1):
#   interrupt    +3   correction  +2   enrichment  +1   followup/first_prompt  0

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

# --- Detect prompt character (additive vs corrective) ---
# Heuristics: multi-topic prompts tend to be long, multi-line, or contain list markers
function Test-IsAdditive([string]$text) {
    if ([string]::IsNullOrWhiteSpace($text)) { return $false }
    $lines     = ($text -split "`n").Count
    $chars     = $text.Length
    $has_list  = $text -match '(?m)^\s*[\d]+\.|^\s*[-*]'   # numbered or bulleted list
    $has_multi = $text -match '\b(also|additionally|separately|furthermore|note that|and also)\b'
    $sentences = ([regex]::Matches($text, '[.!?]')).Count
    # Additive if: multi-line, long, has list markers, or has multi-topic language
    return ($lines -ge 3 -or $chars -gt 150 -or $has_list -or $has_multi -or $sentences -ge 3)
}

$is_additive = Test-IsAdditive $prompt_text

# --- Classify by preceding event ---
$classification = 'first_prompt'

if (Test-Path $session_file) {
    $prior = Get-Content $session_file -ErrorAction SilentlyContinue |
        Where-Object { $_ -ne '' } |
        ForEach-Object { try { $_ | ConvertFrom-Json -ErrorAction Stop } catch { $null } } |
        Where-Object { $_ -ne $null }

    if ($prior -and $prior.Count -gt 0) {
        # Compare last stop vs last prompt by timestamp — ignore tool_done events which
        # arrive asynchronously and can land in the JSONL after the stop event, causing
        # false mid-run detection when the user prompts shortly after Claude finishes.
        $last_stop   = @($prior | Where-Object { $_.event -eq 'stop'   }) | Select-Object -Last 1
        $last_prompt = @($prior | Where-Object { $_.event -eq 'prompt' }) | Select-Object -Last 1

        $claude_stopped = (
            $last_stop -ne $null -and
            ($last_prompt -eq $null -or
             [System.DateTime]::Parse($last_stop.ts) -gt [System.DateTime]::Parse($last_prompt.ts))
        )

        if ($claude_stopped) {
            $gap_sec = ([System.DateTime]::UtcNow - [System.DateTime]::Parse($last_stop.ts)).TotalSeconds
            if ($gap_sec -ge 60 -or $is_additive) {
                $classification = 'followup'      # deliberate next turn or rich context
            } else {
                $classification = 'correction'    # quick focused re-prompt after stop
            }
        } else {
            # Claude was still running (no stop, or last stop predates last prompt)
            if ($is_additive) {
                $classification = 'enrichment'    # intentional context addition mid-run
            } else {
                $classification = 'interrupt'     # short corrective inject mid-run
            }
        }
    }
}

# --- Append to session JSONL ---
# Store up to 1000 chars of prompt text for retrospection (full text for short prompts)
$prompt_excerpt = if ($prompt_text.Length -gt 1000) { $prompt_text.Substring(0, 1000) + '...' } else { $prompt_text }

$entry = [PSCustomObject]@{
    ts             = (Get-Date -Format 'o')
    session_id     = $session_id
    event          = 'prompt'
    classification = $classification
    is_additive    = $is_additive
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
        session_id   = $session_id
        prompts      = 0
        interrupts   = 0
        enrichments  = 0
        corrections  = 0
        perm_reqs    = 0
        perm_repeats = 0
        started_at   = (Get-Date -Format 'o')
    }
}

$state.prompts += 1
switch ($classification) {
    'interrupt'   { $state.interrupts  += 1 }
    'enrichment'  { $state.enrichments += 1 }
    'correction'  { $state.corrections += 1 }
}

$state | ConvertTo-Json | Set-Content $state_file
