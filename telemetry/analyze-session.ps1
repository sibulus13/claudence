# analyze-session.ps1
# Fires on Stop (synchronous). First logs the stop event so subsequent prompts
# can detect it, then scores session friction and manages cumulative tracking.
#
# Friction scoring per session:
#   +3  interrupt     - prompt injected while Claude was mid-run (no preceding stop)
#   +2  correction    - prompt submitted < 60s after a stop (escape + re-prompt)
#   +1  enrichment    - mid-run multi-topic context addition (low friction)
#   +1  permission_req - tool not pre-approved; generates allow-rule suggestion
#   +2  perm_repeat   - same tool blocked again this session
#
# Sound logic (single unified decision - do NOT play sound in the async Stop hook):
#   elapsed > 30s OR score >= 5 OR retrospect_needed -> ring
#   otherwise                                         -> notify
#   score < 2 AND elapsed <= 30s                      -> notify (soft)
#
# Cumulative retrospection threshold:
#   When (sessions_since_review >= 3 AND cumulative_score >= 6):
#     -> notify user to run /retrospect
#     -> reset cumulative counter
#
# Per-turn breakdown:
#   Each turn (prompt -> next prompt) includes tool_done events and perm_req events.
#   Inferred approve: perm_req for tool X followed by tool_done for tool X in same turn.
#   Inferred deny:    perm_req for tool X with no subsequent tool_done for tool X.

$rawInput = [Console]::In.ReadToEnd()
$data = try { $rawInput | ConvertFrom-Json -ErrorAction Stop } catch { $null }

$session_id = if ($data -and $data.session_id) { $data.session_id } else { $null }
if (-not $session_id) { exit 0 }

$log_dir      = "C:\Users\Michael\.claude\telemetry\sessions"
$session_file = Join-Path $log_dir "$session_id.jsonl"

# --- Log the stop event FIRST so the next prompt can detect it ---
if (-not (Test-Path $log_dir)) { New-Item $log_dir -ItemType Directory -Force | Out-Null }
$stop_entry = [PSCustomObject]@{
    ts         = (Get-Date -Format 'o')
    session_id = $session_id
    event      = 'stop'
} | ConvertTo-Json -Compress
Add-Content -Path $session_file -Value $stop_entry

# --- Read elapsed time for sound decision ---
$ts_file = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), 'claude_start.txt')
$elapsed = if (Test-Path $ts_file) {
    ([System.DateTime]::UtcNow.Ticks - [long](Get-Content $ts_file)) / 1e7
} else { 0 }

if (-not (Test-Path $session_file)) { exit 0 }

# --- Load all events ---
$events = Get-Content $session_file -ErrorAction SilentlyContinue |
    Where-Object { $_ -ne '' } |
    ForEach-Object { try { $_ | ConvertFrom-Json -ErrorAction Stop } catch { $null } } |
    Where-Object { $_ -ne $null }

if ($events.Count -eq 0) { exit 0 }

# --- Score friction ---
$score              = 0
$friction_notes     = [System.Collections.Generic.List[string]]::new()
$allow_suggestions  = [System.Collections.Generic.List[string]]::new()

$prompts      = @($events | Where-Object { $_.event -eq 'prompt' })
$perm_reqs    = @($events | Where-Object { $_.event -eq 'permission_req' })
$perm_repeats = @($events | Where-Object { $_.event -eq 'perm_req_repeat' })

foreach ($p in $prompts) {
    switch ($p.classification) {
        'interrupt' {
            $score += 3
            $friction_notes.Add("Mid-run interrupt (+3): short prompt injected while Claude was executing")
        }
        'enrichment' {
            $score += 1
            $friction_notes.Add("Mid-run enrichment (+1): multi-topic context added while Claude was executing")
        }
        'correction' {
            $score += 2
            $friction_notes.Add("Quick correction (+2): re-prompted within 60s of stop")
        }
        # first_prompt and followup score 0
    }
}

foreach ($req in $perm_reqs) {
    $score += 1
    $friction_notes.Add("Permission needed (+1): $($req.tool) - $($req.input_preview)")

    if ($req.tool -eq 'Bash' -and $req.input_preview) {
        $cmd_prefix = ($req.input_preview -split '\s+')[0]
        $suggestion = "Bash(${cmd_prefix}:*)"
        if (-not $allow_suggestions.Contains($suggestion)) { $allow_suggestions.Add($suggestion) }
    } elseif ($req.tool -and $req.tool -ne 'unknown') {
        if (-not $allow_suggestions.Contains($req.tool)) { $allow_suggestions.Add($req.tool) }
    }
}

foreach ($req in $perm_repeats) {
    $score += 2
    $friction_notes.Add("Repeat block (+2): $($req.tool) blocked again - add to allow list: $($req.input_preview)")

    if ($req.tool -eq 'Bash' -and $req.input_preview) {
        $cmd_prefix = ($req.input_preview -split '\s+')[0]
        $suggestion = "Bash(${cmd_prefix}:*)"
        if (-not $allow_suggestions.Contains($suggestion)) { $allow_suggestions.Add($suggestion) }
    } elseif ($req.tool -and $req.tool -ne 'unknown') {
        if (-not $allow_suggestions.Contains($req.tool)) { $allow_suggestions.Add($req.tool) }
    }
}

# --- Build per-turn breakdown ---
# A turn is the span of events between two consecutive prompt events.
# We group: [prompt_i .. prompt_{i+1}) and analyze tool_done + perm_req within each span.
$turns = [System.Collections.Generic.List[object]]::new()

for ($ti = 0; $ti -lt $prompts.Count; $ti++) {
    $turn_prompt = $prompts[$ti]
    $turn_start  = [System.DateTime]::Parse($turn_prompt.ts)
    $turn_end    = if ($ti + 1 -lt $prompts.Count) {
        [System.DateTime]::Parse($prompts[$ti + 1].ts)
    } else {
        [System.DateTime]::MaxValue
    }

    # Events in this turn window (after prompt, before next prompt)
    $turn_events = @($events | Where-Object {
        $_.ts -and
        [System.DateTime]::Parse($_.ts) -gt $turn_start -and
        [System.DateTime]::Parse($_.ts) -lt $turn_end
    })

    $turn_tool_dones = @($turn_events | Where-Object { $_.event -eq 'tool_done' })
    $turn_perm_reqs  = @($turn_events | Where-Object { $_.event -in @('permission_req', 'perm_req_repeat') })

    # Infer approve/deny per perm_req: approve if a tool_done for same tool follows
    $decisions = [System.Collections.Generic.List[object]]::new()
    foreach ($req in $turn_perm_reqs) {
        $req_ts    = [System.DateTime]::Parse($req.ts)
        $approved  = $turn_tool_dones | Where-Object {
            $_.tool -eq $req.tool -and [System.DateTime]::Parse($_.ts) -gt $req_ts
        }
        $decisions.Add([PSCustomObject]@{
            tool     = $req.tool
            preview  = $req.input_preview
            repeat   = ($req.event -eq 'perm_req_repeat')
            decision = if ($approved) { 'approve' } else { 'deny' }
        })
    }

    $turns.Add([PSCustomObject]@{
        classification = $turn_prompt.classification
        prompt_chars   = $turn_prompt.prompt_chars
        tool_calls     = $turn_tool_dones.Count
        decisions      = $decisions.ToArray()
    })
}

# --- Write per-session report ---
$report_dir = "C:\Users\Michael\.claude\telemetry\reports"
if (-not (Test-Path $report_dir)) { New-Item $report_dir -ItemType Directory -Force | Out-Null }

$cwd         = if ($prompts.Count -gt 0 -and $prompts[0].cwd) { $prompts[0].cwd } else { '' }
$short_id    = $session_id.Substring(0, [Math]::Min(8, $session_id.Length))
$interrupts  = @($prompts | Where-Object { $_.classification -eq 'interrupt' }).Count
$enrichments = @($prompts | Where-Object { $_.classification -eq 'enrichment' }).Count
$corrections = @($prompts | Where-Object { $_.classification -eq 'correction' }).Count

# Locate Claude Code's own transcript for this session (history.jsonl is global;
# per-session transcript entries have a matching session_id field)
$transcript_path = "C:\Users\Michael\.claude\history.jsonl"
$compacts = @($events | Where-Object { $_.event -eq 'compact' })

$report = [PSCustomObject]@{
    ts                = (Get-Date -Format 'o')
    session_id        = $session_id
    cwd               = $cwd
    elapsed_sec       = [Math]::Round($elapsed, 1)
    score             = $score
    total_events      = $events.Count
    prompt_count      = $prompts.Count
    interrupts        = $interrupts
    enrichments       = $enrichments
    corrections       = $corrections
    perm_req_count    = $perm_reqs.Count
    perm_repeat_count = $perm_repeats.Count
    compact_count     = $compacts.Count
    transcript_path   = $transcript_path
    session_jsonl     = $session_file
    friction_notes    = $friction_notes.ToArray()
    allow_suggestions = $allow_suggestions.ToArray()
    turns             = $turns.ToArray()
} | ConvertTo-Json -Depth 5
$report | Set-Content (Join-Path $report_dir "${short_id}.json")

# --- Update rolling averages (I/P and B/P rates per session, window=5) ---
# I rate = pure interrupts only (enrichments excluded - they are not friction)
# B rate = all blocks including repeats (repeats are higher-signal friction)
$avg_file = "C:\Users\Michael\.claude\telemetry\rolling-averages.json"
$window   = 5

if ($prompts.Count -gt 0) {
    $all_blocks = $perm_reqs.Count + $perm_repeats.Count
    $i_rate = [Math]::Round($interrupts  / $prompts.Count, 4)
    $b_rate = [Math]::Round($all_blocks  / $prompts.Count, 4)

    $avg_data = if (Test-Path $avg_file) {
        try { Get-Content $avg_file -Raw | ConvertFrom-Json -ErrorAction Stop } catch { $null }
    } else { $null }

    if (-not $avg_data) {
        $avg_data = [PSCustomObject]@{ window = $window; sessions = @(); avg_i_rate = 0.0; avg_b_rate = 0.0; session_count = 0 }
    }

    $sessions_list = [System.Collections.Generic.List[object]]::new()
    if ($avg_data.sessions) { foreach ($s in $avg_data.sessions) { $sessions_list.Add($s) } }

    $sessions_list.Add([PSCustomObject]@{
        id           = $short_id
        ts           = (Get-Date -Format 'o')
        cwd          = $cwd
        prompts      = $prompts.Count
        interrupts   = $interrupts
        enrichments  = $enrichments
        perm_reqs    = $perm_reqs.Count
        perm_repeats = $perm_repeats.Count
        i_rate       = $i_rate
        b_rate       = $b_rate
    })
    while ($sessions_list.Count -gt $window) { $sessions_list.RemoveAt(0) }

    $total_i = 0.0; $total_b = 0.0
    foreach ($s in $sessions_list) { $total_i += $s.i_rate; $total_b += $s.b_rate }
    $n = $sessions_list.Count

    $avg_data.sessions      = $sessions_list.ToArray()
    $avg_data.avg_i_rate    = [Math]::Round($total_i / $n, 4)
    $avg_data.avg_b_rate    = [Math]::Round($total_b / $n, 4)
    $avg_data.session_count = $n
    $avg_data | ConvertTo-Json -Depth 5 | Set-Content $avg_file
}

# --- Update cumulative tracker ---
$cumulative_file = "C:\Users\Michael\.claude\telemetry\cumulative.json"
$cum = if (Test-Path $cumulative_file) {
    try { Get-Content $cumulative_file | ConvertFrom-Json -ErrorAction Stop } catch { $null }
} else { $null }

if (-not $cum) {
    $cum = [PSCustomObject]@{ total_score = 0; sessions_since_review = 0; last_review_ts = '' }
}

if ($score -gt 0) {
    $cum.total_score          += $score
    $cum.sessions_since_review += 1
}
$cum | ConvertTo-Json | Set-Content $cumulative_file

# --- Determine output and play sound (single unified decision) ---
$retrospect_needed = ($cum.sessions_since_review -ge 3 -and $cum.total_score -ge 6)
$play_ring = ($elapsed -gt 30 -or $score -ge 5 -or $retrospect_needed)

$suggest_str = if ($allow_suggestions.Count -gt 0) {
    " Suggested allow rules: $($allow_suggestions -join ', ')."
} else { '' }

# Play sound before outputting systemMessage to minimize perceived delay
Start-Sleep -Milliseconds 400
$snd_dir = 'C:/Users/Michael/.claude/sounds/'
if ($play_ring) {
    (New-Object System.Media.SoundPlayer "${snd_dir}ring-half.wav").PlaySync()
} elseif ($score -ge 2) {
    (New-Object System.Media.SoundPlayer "${snd_dir}notify-half.wav").PlaySync()
} else {
    (New-Object System.Media.SoundPlayer "${snd_dir}notify-half.wav").PlaySync()
}

if ($retrospect_needed) {
    # Reset cumulative counter now that we're notifying
    $cum.total_score           = 0
    $cum.sessions_since_review = 0
    $cum.last_review_ts        = (Get-Date -Format 'o')
    $cum | ConvertTo-Json | Set-Content $cumulative_file

    [PSCustomObject]@{
        systemMessage = "Friction has accumulated across recent sessions (score: $score this session).${suggest_str} Run /retrospect to review friction points, update allow rules, and refresh memory context."
    } | ConvertTo-Json -Compress
    exit 0
}

if ($score -ge 5) {
    [PSCustomObject]@{
        systemMessage = "Friction score $score this session ($interrupts interrupt(s), $corrections correction(s), $($perm_reqs.Count) permission request(s)).${suggest_str} Report: ~\.claude\telemetry\reports\${short_id}.json"
    } | ConvertTo-Json -Compress
    exit 0
}

if ($score -ge 2) {
    [PSCustomObject]@{
        systemMessage = "Friction score $score this session ($interrupts interrupt(s), $corrections correction(s), $($perm_reqs.Count) permission request(s)). Report: ~\.claude\telemetry\reports\${short_id}.json"
    } | ConvertTo-Json -Compress
}
