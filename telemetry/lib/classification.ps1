# lib/classification.ps1
# Pure classification functions — no I/O, no side effects, no hardcoded paths.
# Dot-source this file in log-prompt.ps1 and in Pester tests.
#
# Classifications:
#   first_prompt    — no prior events in session
#   followup        — Claude had stopped; prompt is a clean next step (including post-stop additive language)
#   override        — Claude had stopped; user explicitly redirects the current direction
#   addition        — Claude is running; user queues additional context or a parallel task
#   denial_context  — Claude is running; user denied a tool call and is providing context/reason
#
# Friction scores (applied in analyze-session.ps1):
#   override +3    addition +1    denial_context +1    followup/first_prompt 0

function Test-IsOverride {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $false }
    # Start-anchored patterns — these words redirect meaning only when leading the prompt
    $start_patterns = @(
        '(?i)^\s*actually\b',
        '(?i)^\s*no[,\s!]',
        '(?i)^\s*wait[,\s]',
        '(?i)^\s*stop\b',
        '(?i)^\s*undo\b'
    )
    foreach ($p in $start_patterns) { if ($Text -match $p) { return $true } }
    # Anywhere patterns — these unambiguously signal replacement regardless of position
    $any_patterns = @(
        '(?i)\bforget\s+(that|this|it)\b',
        '(?i)\binstead\b',
        '(?i)\bscratch\s+that\b',
        '(?i)\bstart\s+over\b',
        '(?i)\bnever\s+mind\b',
        '(?i)\bcancel\s+(that|this)\b',
        '(?i)\bignore\s+(that|this|previous|the\s+previous)\b',
        '(?i)\bdisregard\b',
        '(?i)\blet.s\s+\w+\s+instead\b'
    )
    foreach ($p in $any_patterns) { if ($Text -match $p) { return $true } }
    return $false
}

function Test-IsAddition {
    # Detects additive language patterns.
    # NOTE: No longer called from Get-PromptClassification — post-stop additive prompts
    # now classify as 'followup'. This function is kept for direct unit testing.
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $false }
    $patterns = @(
        '(?i)\balso\b',
        '(?i)\badditionally\b',
        '(?i)\bnote\s+that\b',
        '(?i)\bdon.t\s+forget\b',
        '(?i)\bby\s+the\s+way\b',
        '(?i)\boh\s+and\b',
        '(?i)\bone\s+more\s+thing\b',
        '(?i)\bforgot\s+to\s+(mention|add|say|include)\b',
        '(?i)\bwhile\s+you.re\s+at\s+it\b',
        '(?i)\bfurthermore\b',
        '(?i)\bseparately\b'
    )
    foreach ($p in $patterns) { if ($Text -match $p) { return $true } }
    return $false
}

function Get-IsDenialContext {
    # Returns $true if there is an unmatched permission_req in the current turn —
    # meaning a tool was denied and the user is now providing context/reason for it.
    param([array]$PriorEvents)
    if (-not $PriorEvents -or $PriorEvents.Count -eq 0) { return $false }

    # Scope to events since the most recent prompt (the current running turn only)
    $last_prompt = @($PriorEvents | Where-Object { $_.event -eq 'prompt' }) | Select-Object -Last 1
    $turn_events = if ($last_prompt) {
        $lp_ts = [datetime]::Parse($last_prompt.ts)
        @($PriorEvents | Where-Object { $_.ts -and [datetime]::Parse($_.ts) -gt $lp_ts })
    } else {
        $PriorEvents
    }

    $perm_events = @($turn_events | Where-Object { $_.event -in @('permission_req', 'perm_req_repeat') })
    if (-not $perm_events -or $perm_events.Count -eq 0) { return $false }

    $tool_dones = @($turn_events | Where-Object { $_.event -eq 'tool_done' })

    foreach ($req in $perm_events) {
        $req_ts  = [datetime]::Parse($req.ts)
        $matched = $tool_dones | Where-Object {
            $_.tool -eq $req.tool -and [datetime]::Parse($_.ts) -gt $req_ts
        }
        if (-not $matched) { return $true }  # Unmatched perm_req = denied
    }
    return $false
}

function Get-PromptClassification {
    param(
        [string]$PromptText,
        [array]$PriorEvents      # parsed objects from session JSONL
    )

    if (-not $PriorEvents -or $PriorEvents.Count -eq 0) {
        return 'first_prompt'
    }

    $last_stop   = @($PriorEvents | Where-Object { $_.event -eq 'stop'   }) | Select-Object -Last 1
    $last_prompt = @($PriorEvents | Where-Object { $_.event -eq 'prompt' }) | Select-Object -Last 1

    # No prior prompt at all — treat as first
    if (-not $last_prompt) { return 'first_prompt' }

    $claude_stopped = (
        $last_stop -ne $null -and
        [datetime]::Parse($last_stop.ts) -gt [datetime]::Parse($last_prompt.ts)
    )

    if (-not $claude_stopped) {
        # Claude is still generating — check for tool denial context first
        if (Get-IsDenialContext $PriorEvents) { return 'denial_context' }
        return 'addition'
    }

    if (Test-IsOverride $PromptText) { return 'override' }
    return 'followup'
}
