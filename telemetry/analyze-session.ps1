# analyze-session.ps1
# Fires on Stop (synchronous). Logs the stop event, scores session friction,
# manages rolling averages, cumulative tracking, and plays a completion sound.
#
# Friction scoring per session:
#   +3  override      - user replaced the current direction entirely
#   +1  addition      - user injected context (mid-run or additive language post-stop)
#   +1  permission_req - tool not pre-approved; generates allow-rule suggestion
#   +2  perm_repeat   - same tool blocked again this session
#
# Sound logic (single unified decision):
#   elapsed > 30s OR score >= 5 OR retrospect_needed -> ring (chimes)
#   otherwise                                         -> notify
#
# Retrospection threshold:
#   sessions_since_review >= 3 AND cumulative_score >= 6 -> prompt /retrospect

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
$score             = 0
$friction_notes    = [System.Collections.Generic.List[string]]::new()
$allow_suggestions = [System.Collections.Generic.List[string]]::new()

$prompts      = @($events | Where-Object { $_.event -eq 'prompt' })
$perm_reqs    = @($events | Where-Object { $_.event -eq 'permission_req' })
$perm_repeats = @($events | Where-Object { $_.event -eq 'perm_req_repeat' })

foreach ($p in $prompts) {
    switch ($p.classification) {
        'override' {
            $score += 3
            $friction_notes.Add("Override (+3): user replaced direction - $($p.prompt_text.Substring(0, [Math]::Min(80, $p.prompt_text.Length)))")
        }
        'addition' {
            $score += 1
            $friction_notes.Add("Addition (+1): user injected context - $($p.prompt_text.Substring(0, [Math]::Min(80, $p.prompt_text.Length)))")
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
$turns = [System.Collections.Generic.List[object]]::new()

for ($ti = 0; $ti -lt $prompts.Count; $ti++) {
    $turn_prompt = $prompts[$ti]
    $turn_start  = [System.DateTime]::Parse($turn_prompt.ts)
    $turn_end    = if ($ti + 1 -lt $prompts.Count) {
        [System.DateTime]::Parse($prompts[$ti + 1].ts)
    } else {
        [System.DateTime]::MaxValue
    }

    $turn_events = @($events | Where-Object {
        $_.ts -and
        [System.DateTime]::Parse($_.ts) -gt $turn_start -and
        [System.DateTime]::Parse($_.ts) -lt $turn_end
    })

    $turn_tool_dones = @($turn_events | Where-Object { $_.event -eq 'tool_done' })
    $turn_perm_reqs  = @($turn_events | Where-Object { $_.event -in @('permission_req', 'perm_req_repeat') })

    $decisions = [System.Collections.Generic.List[object]]::new()
    foreach ($req in $turn_perm_reqs) {
        $req_ts   = [System.DateTime]::Parse($req.ts)
        $approved = $turn_tool_dones | Where-Object {
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
$overrides   = @($prompts | Where-Object { $_.classification -eq 'override' }).Count
$additions   = @($prompts | Where-Object { $_.classification -eq 'addition' }).Count
$compacts    = @($events  | Where-Object { $_.event -eq 'compact' })

$report = [PSCustomObject]@{
    ts                = (Get-Date -Format 'o')
    session_id        = $session_id
    cwd               = $cwd
    elapsed_sec       = [Math]::Round($elapsed, 1)
    score             = $score
    total_events      = $events.Count
    prompt_count      = $prompts.Count
    overrides         = $overrides
    additions         = $additions
    perm_req_count    = $perm_reqs.Count
    perm_repeat_count = $perm_repeats.Count
    compact_count     = $compacts.Count
    transcript_path   = "C:\Users\Michael\.claude\history.jsonl"
    session_jsonl     = $session_file
    friction_notes    = $friction_notes.ToArray()
    allow_suggestions = $allow_suggestions.ToArray()
    turns             = $turns.ToArray()
} | ConvertTo-Json -Depth 5
$report | Set-Content (Join-Path $report_dir "${short_id}.json")

# --- Update rolling averages (O/P and A/P and B/P rates, window=5) ---
$avg_file = "C:\Users\Michael\.claude\telemetry\rolling-averages.json"
$window   = 5

if ($prompts.Count -gt 0) {
    $all_blocks = $perm_reqs.Count + $perm_repeats.Count
    $o_rate = [Math]::Round($overrides   / $prompts.Count, 4)
    $a_rate = [Math]::Round($additions   / $prompts.Count, 4)
    $b_rate = [Math]::Round($all_blocks  / $prompts.Count, 4)

    $avg_data = if (Test-Path $avg_file) {
        try { Get-Content $avg_file -Raw | ConvertFrom-Json -ErrorAction Stop } catch { $null }
    } else { $null }

    if (-not $avg_data) {
        $avg_data = [PSCustomObject]@{
            window        = $window
            sessions      = @()
            avg_o_rate    = 0.0
            avg_a_rate    = 0.0
            avg_b_rate    = 0.0
            session_count = 0
        }
    }

    $sessions_list = [System.Collections.Generic.List[object]]::new()
    if ($avg_data.sessions) { foreach ($s in $avg_data.sessions) { $sessions_list.Add($s) } }

    $sessions_list.Add([PSCustomObject]@{
        id           = $short_id
        ts           = (Get-Date -Format 'o')
        cwd          = $cwd
        prompts      = $prompts.Count
        overrides    = $overrides
        additions    = $additions
        perm_reqs    = $perm_reqs.Count
        perm_repeats = $perm_repeats.Count
        o_rate       = $o_rate
        a_rate       = $a_rate
        b_rate       = $b_rate
    })
    while ($sessions_list.Count -gt $window) { $sessions_list.RemoveAt(0) }

    $total_o = 0.0; $total_a = 0.0; $total_b = 0.0
    foreach ($s in $sessions_list) {
        $total_o += if ($s.o_rate) { $s.o_rate } else { 0.0 }
        $total_a += if ($s.a_rate) { $s.a_rate } else { 0.0 }
        $total_b += if ($s.b_rate) { $s.b_rate } else { 0.0 }
    }
    $n = $sessions_list.Count

    $avg_data.sessions      = $sessions_list.ToArray()
    $avg_data.avg_o_rate    = [Math]::Round($total_o / $n, 4)
    $avg_data.avg_a_rate    = [Math]::Round($total_a / $n, 4)
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
    $cum.total_score           += $score
    $cum.sessions_since_review += 1
}
$cum | ConvertTo-Json | Set-Content $cumulative_file

# --- Determine output and play sound ---
$retrospect_needed = ($cum.sessions_since_review -ge 3 -and $cum.total_score -ge 6)
$play_ring = ($elapsed -gt 30 -or $score -ge 5 -or $retrospect_needed)

$suggest_str = if ($allow_suggestions.Count -gt 0) {
    " Suggested allow rules: $($allow_suggestions -join ', ')."
} else { '' }

Start-Sleep -Milliseconds 400
$snd_dir = 'C:/Users/Michael/.claude/sounds/'
if ($play_ring) {
    (New-Object System.Media.SoundPlayer "${snd_dir}ring-half.wav").PlaySync()
} else {
    (New-Object System.Media.SoundPlayer "${snd_dir}notify-half.wav").PlaySync()
}

if ($retrospect_needed) {
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
        systemMessage = "Friction score $score this session ($overrides override(s), $additions addition(s), $($perm_reqs.Count) permission request(s)).${suggest_str} Report: ~\.claude\telemetry\reports\${short_id}.json"
    } | ConvertTo-Json -Compress
    exit 0
}

if ($score -ge 2) {
    [PSCustomObject]@{
        systemMessage = "Friction score $score this session ($overrides override(s), $additions addition(s), $($perm_reqs.Count) permission request(s)). Report: ~\.claude\telemetry\reports\${short_id}.json"
    } | ConvertTo-Json -Compress
}
