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

# --- fix-friction-system-prompts: injected prompts are not the owner's (docs/work/fix-friction-system-prompts) ---

# Claude Code injects these through UserPromptSubmit; the hook input names no origin, so the live label reads the
# text. The Stop-time score uses the transcript's promptSource instead (Get-FrictionScore).
$SystemPromptMarkers = @('<task-notification', '<agent-message', '<cross-session-message')
$OwnerPromptSources  = @('typed', 'queued', 'suggestion_accepted')
$JoinWindowSeconds   = 5
$JoinPrefixChars     = 200

function Test-IsSystemPrompt {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $false }
    $head = $Text.TrimStart()
    foreach ($m in $SystemPromptMarkers) { if ($head.StartsWith($m, [System.StringComparison]::Ordinal)) { return $true } }
    return $false
}

function Test-CountsAsPrompt { param([string]$Classification) return $Classification -ne 'system' }

function Test-UpdatesTheme { param([string]$Classification) return $Classification -ne 'system' }

function Get-JoinKey {
    param([string]$Text)
    $t = if ($null -eq $Text) { '' } else { $Text }
    if ($t.EndsWith('...')) { $t = $t.Substring(0, $t.Length - 3) }   # log-prompt cuts at 1,000 chars and appends '...'
    $t = $t.Trim()
    return $t.Substring(0, [Math]::Min($JoinPrefixChars, $t.Length))
}

function Join-TranscriptSource {
    # Returns one promptSource (or $null when unmatched) per prompt event, in order. An event joins the unused,
    # non-sidechain entry with the same text prefix whose UTC time is nearest and within the window.
    param([array]$PromptEvents, [array]$Entries)
    $pool = @($Entries | Where-Object { -not $_.isSidechain -and $_.promptSource })
    $used = [System.Collections.Generic.HashSet[int]]::new()
    $out = [System.Collections.Generic.List[object]]::new()
    foreach ($e in $PromptEvents) {
        $key = Get-JoinKey $e.prompt_text
        $t = [DateTimeOffset]::Parse($e.ts).UtcDateTime
        $best = -1; $bestGap = [double]::MaxValue
        for ($i = 0; $i -lt $pool.Count; $i++) {
            if ($used.Contains($i)) { continue }
            $entryKey = Get-JoinKey $pool[$i].text
            if (-not ($entryKey.StartsWith($key) -or $key.StartsWith($entryKey))) { continue }
            $gap = [Math]::Abs(([DateTimeOffset]::Parse($pool[$i].timestamp).UtcDateTime - $t).TotalSeconds)
            if ($gap -le $JoinWindowSeconds -and $gap -lt $bestGap) { $best = $i; $bestGap = $gap }
        }
        if ($best -ge 0) { [void]$used.Add($best); $out.Add($pool[$best].promptSource) } else { $out.Add($null) }
    }
    return , $out.ToArray()
}

function Get-FrictionScore {
    # The Stop-time prompt score: only owner prompts count. Returns the owner prompts for the per-turn report.
    param([array]$PromptEvents, [array]$Entries)
    $sources = Join-TranscriptSource $PromptEvents $Entries
    $owner = [System.Collections.Generic.List[object]]::new()
    $notes = [System.Collections.Generic.List[string]]::new()
    $score = 0; $unlabelled = 0; $misses = 0
    for ($i = 0; $i -lt $PromptEvents.Count; $i++) {
        $p = $PromptEvents[$i]; $src = $sources[$i]
        if ($null -eq $src) {
            $unlabelled += 1
            if ($p.classification -eq 'system') { continue }
        } elseif ($OwnerPromptSources -notcontains $src) {
            if ($p.classification -ne 'system') { $misses += 1 }
            continue
        }
        $owner.Add($p)
        $excerpt = if ($p.prompt_text) { $p.prompt_text.Substring(0, [Math]::Min(80, $p.prompt_text.Length)) } else { '' }
        switch ($p.classification) {
            'override'       { $score += 3; $notes.Add("Override (+3): user redirected post-stop - $excerpt") }
            'addition'       { $score += 1; $notes.Add("Add/Alt (+1): queued while running - $excerpt") }
            'denial_context' { $score += 1; $notes.Add("Denied+ctx (+1): tool denied with reason - $excerpt") }
        }
    }
    return [PSCustomObject]@{
        score           = $score
        notes           = $notes.ToArray()
        owner_prompts   = $owner.ToArray()
        prompt_count    = $owner.Count
        overrides       = @($owner | Where-Object { $_.classification -eq 'override' }).Count
        additions       = @($owner | Where-Object { $_.classification -eq 'addition' }).Count
        denial_contexts = @($owner | Where-Object { $_.classification -eq 'denial_context' }).Count
        unlabelled      = $unlabelled
        marker_misses   = $misses
    }
}

function Read-TranscriptPrompts {
    # Prompt entries only. Lines are pre-filtered on the literal "promptSource" before JSON parsing, so a large
    # transcript costs one streaming read (the Stop hook is time-bounded).
    param([string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return @() }
    $out = [System.Collections.Generic.List[object]]::new()
    foreach ($line in [System.IO.File]::ReadLines($Path)) {
        if ($line.IndexOf('"promptSource"', [System.StringComparison]::Ordinal) -lt 0) { continue }
        $d = try { $line | ConvertFrom-Json -ErrorAction Stop } catch { $null }
        if (-not $d -or $d.type -ne 'user' -or -not $d.promptSource) { continue }
        $c = $d.message.content
        $text = if ($c -is [string]) { $c } else { (@($c | Where-Object { $_.type -eq 'text' } | ForEach-Object { $_.text }) -join "`n") }
        $out.Add([PSCustomObject]@{ timestamp = $d.timestamp; text = $text; promptSource = $d.promptSource; isSidechain = [bool]$d.isSidechain })
    }
    return , $out.ToArray()
}

function Get-PromptClassification {
    param(
        [string]$PromptText,
        [array]$PriorEvents      # parsed objects from session JSONL
    )

    if (Test-IsSystemPrompt $PromptText) { return 'system' }

    # Owner prompts only: an injected prompt is neither the owner's first prompt nor the one they reply to.
    $owner_prior = @($PriorEvents | Where-Object { $_.event -ne 'prompt' -or $_.classification -ne 'system' })
    if (-not $owner_prior -or $owner_prior.Count -eq 0) {
        return 'first_prompt'
    }

    $last_stop   = @($owner_prior | Where-Object { $_.event -eq 'stop'   }) | Select-Object -Last 1
    $last_prompt = @($owner_prior | Where-Object { $_.event -eq 'prompt' }) | Select-Object -Last 1

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
