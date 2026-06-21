# analyze-session.ps1
# Fires on Stop (synchronous). Logs the stop event, scores session friction,
# manages rolling averages, cumulative tracking, and plays a completion sound.
#
# Friction scoring per session:
#   +3  override           - user exited the flow post-stop to redirect direction
#   +1  addition           - user queued context or a parallel task while Claude was running
#   +1  denial_context     - user denied a tool call and provided a reason
#   +0  followup           - clean next step post-stop (including post-stop additive language)
#   +0  perm_req approved  - tool not pre-approved but user allowed it; generates allow-rule suggestion only
#   +1  perm_req denied    - tool blocked and denied; real friction
#   +1  perm_repeat approved - same tool approved again; suggest adding to allow list
#   +2  perm_repeat denied   - same tool blocked and denied again; high friction
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

$cost_usd = if ($data -and $data.cost -and ($null -ne $data.cost.total_cost_usd)) {
    [double]$data.cost.total_cost_usd
} else { $null }
$ctx_pct = if ($data -and $data.context_window -and ($null -ne $data.context_window.used_percentage)) {
    [int]$data.context_window.used_percentage
} else { $null }

# Clear running flag — Claude has stopped
$running_flag = "C:\Users\Michael\.claude\telemetry\running.flag"
if (Test-Path $running_flag) { Remove-Item $running_flag -Force -ErrorAction SilentlyContinue }

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
$denied_perm_count = 0
$friction_notes    = [System.Collections.Generic.List[string]]::new()
$allow_suggestions = [System.Collections.Generic.List[string]]::new()

$prompts      = @($events | Where-Object { $_.event -eq 'prompt' })
$perm_reqs    = @($events | Where-Object { $_.event -eq 'permission_req' })
$perm_repeats = @($events | Where-Object { $_.event -eq 'perm_req_repeat' })
$tool_dones   = @($events | Where-Object { $_.event -eq 'tool_done' })

# Pre-compute which permission requests were subsequently approved (tool ran after the request)
$approved_req_ts = [System.Collections.Generic.HashSet[string]]::new()
foreach ($req in (@($perm_reqs) + @($perm_repeats))) {
    $req_ts = [System.DateTime]::Parse($req.ts)
    $was_approved = $tool_dones | Where-Object {
        $_.tool -eq $req.tool -and [System.DateTime]::Parse($_.ts) -gt $req_ts
    }
    if ($was_approved) { $approved_req_ts.Add($req.ts) | Out-Null }
}

foreach ($p in $prompts) {
    switch ($p.classification) {
        'override' {
            $score += 3
            $friction_notes.Add("Override (+3): user redirected post-stop - $($p.prompt_text.Substring(0, [Math]::Min(80, $p.prompt_text.Length)))")
        }
        'addition' {
            $score += 1
            $friction_notes.Add("Add/Alt (+1): queued while running - $($p.prompt_text.Substring(0, [Math]::Min(80, $p.prompt_text.Length)))")
        }
        'denial_context' {
            $score += 1
            $friction_notes.Add("Denied+ctx (+1): tool denied with reason - $($p.prompt_text.Substring(0, [Math]::Min(80, $p.prompt_text.Length)))")
        }
        # first_prompt and followup score 0
    }
}

foreach ($req in $perm_reqs) {
    $approved = $approved_req_ts.Contains($req.ts)
    if ($approved) {
        # Approved — suggest adding to allow list, no friction score
        $friction_notes.Add("Permission approved (suggest allowing): $($req.tool) - $($req.input_preview)")
        if ($req.tool -eq 'Bash' -and $req.input_preview) {
            $cmd_prefix = ($req.input_preview -split '\s+')[0]
            $suggestion = "Bash(${cmd_prefix}:*)"
            if (-not $allow_suggestions.Contains($suggestion)) { $allow_suggestions.Add($suggestion) }
        } elseif ($req.tool -and $req.tool -ne 'unknown') {
            if (-not $allow_suggestions.Contains($req.tool)) { $allow_suggestions.Add($req.tool) }
        }
    } else {
        # Denied — real friction
        $denied_perm_count += 1
        $score += 1
        $friction_notes.Add("Permission denied (+1): $($req.tool) - $($req.input_preview)")
    }
}

foreach ($req in $perm_repeats) {
    $approved = $approved_req_ts.Contains($req.ts)
    if ($approved) {
        # Approved again — still mild friction (had to approve twice), strongly suggest allow list
        $score += 1
        $friction_notes.Add("Repeat approved (+1, strongly suggest allowing): $($req.tool) - $($req.input_preview)")
        if ($req.tool -eq 'Bash' -and $req.input_preview) {
            $cmd_prefix = ($req.input_preview -split '\s+')[0]
            $suggestion = "Bash(${cmd_prefix}:*)"
            if (-not $allow_suggestions.Contains($suggestion)) { $allow_suggestions.Add($suggestion) }
        } elseif ($req.tool -and $req.tool -ne 'unknown') {
            if (-not $allow_suggestions.Contains($req.tool)) { $allow_suggestions.Add($req.tool) }
        }
    } else {
        # Denied again — high friction
        $denied_perm_count += 1
        $score += 2
        $friction_notes.Add("Repeat denied (+2): $($req.tool) blocked again - $($req.input_preview)")
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
        $decisions.Add([PSCustomObject]@{
            tool     = $req.tool
            preview  = $req.input_preview
            repeat   = ($req.event -eq 'perm_req_repeat')
            decision = if ($approved_req_ts.Contains($req.ts)) { 'approve' } else { 'deny' }
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
$overrides     = @($prompts | Where-Object { $_.classification -eq 'override'       }).Count
$additions     = @($prompts | Where-Object { $_.classification -eq 'addition'       }).Count
$denial_ctxs   = @($prompts | Where-Object { $_.classification -eq 'denial_context' }).Count
$compacts    = @($events  | Where-Object { $_.event -eq 'compact' })

$report = [PSCustomObject]@{
    ts                = (Get-Date -Format 'o')
    session_id        = $session_id
    cwd               = $cwd
    elapsed_sec       = [Math]::Round($elapsed, 1)
    cost_usd          = $cost_usd
    ctx_pct           = $ctx_pct
    score             = $score
    total_events      = $events.Count
    prompt_count      = $prompts.Count
    overrides         = $overrides
    additions         = $additions
    denial_ctx_count  = $denial_ctxs
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

# --- Append to cost ledger (time-series, one line per session) ---
$ledger_file = "C:\Users\Michael\.claude\telemetry\cost-ledger.jsonl"
$ledger_entry = [PSCustomObject]@{
    ts           = (Get-Date -Format 'o')
    session_id   = $short_id
    cwd          = $cwd
    cost_usd     = if ($null -ne $cost_usd) { [Math]::Round($cost_usd, 4) } else { $null }
    ctx_pct      = $ctx_pct
    elapsed_sec  = [Math]::Round($elapsed, 1)
    prompt_count = $prompts.Count
    score        = $score
} | ConvertTo-Json -Compress
Add-Content -Path $ledger_file -Value $ledger_entry

# --- Update rolling averages (O/P and A/P and B/P rates, window=5) ---
$avg_file = "C:\Users\Michael\.claude\telemetry\rolling-averages.json"
$window   = 5

if ($prompts.Count -gt 0) {
    $o_rate  = [Math]::Round($overrides         / $prompts.Count, 4)
    $a_rate  = [Math]::Round($additions         / $prompts.Count, 4)
    $dc_rate = [Math]::Round($denial_ctxs       / $prompts.Count, 4)
    $b_rate  = [Math]::Round($denied_perm_count / $prompts.Count, 4)

    $avg_data = if (Test-Path $avg_file) {
        try { Get-Content $avg_file -Raw | ConvertFrom-Json -ErrorAction Stop } catch { $null }
    } else { $null }

    if (-not $avg_data) {
        $avg_data = [PSCustomObject]@{
            window        = $window
            sessions      = @()
            avg_o_rate    = 0.0
            avg_a_rate    = 0.0
            avg_dc_rate   = 0.0
            avg_b_rate    = 0.0
            session_count = 0
        }
    } else {
        # Migrate: add avg_dc_rate if loading an older file that predates this field
        if (-not $avg_data.PSObject.Properties['avg_dc_rate']) {
            $avg_data | Add-Member -NotePropertyName 'avg_dc_rate' -NotePropertyValue 0.0
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
        denial_ctxs  = $denial_ctxs
        perm_reqs    = $perm_reqs.Count
        perm_repeats = $perm_repeats.Count
        o_rate       = $o_rate
        a_rate       = $a_rate
        dc_rate      = $dc_rate
        b_rate       = $b_rate
        cost_usd     = if ($null -ne $cost_usd) { [Math]::Round($cost_usd, 4) } else { $null }
        elapsed_sec  = [Math]::Round($elapsed, 1)
    })
    while ($sessions_list.Count -gt $window) { $sessions_list.RemoveAt(0) }

    $total_o = 0.0; $total_a = 0.0; $total_dc = 0.0; $total_b = 0.0
    foreach ($s in $sessions_list) {
        $total_o  += if ($s.o_rate)  { $s.o_rate  } else { 0.0 }
        $total_a  += if ($s.a_rate)  { $s.a_rate  } else { 0.0 }
        $total_dc += if ($s.dc_rate) { $s.dc_rate } else { 0.0 }
        $total_b  += if ($s.b_rate)  { $s.b_rate  } else { 0.0 }
    }
    $n = $sessions_list.Count

    $avg_data.sessions      = $sessions_list.ToArray()
    $avg_data.avg_o_rate    = [Math]::Round($total_o  / $n, 4)
    $avg_data.avg_a_rate    = [Math]::Round($total_a  / $n, 4)
    $avg_data.avg_dc_rate   = [Math]::Round($total_dc / $n, 4)
    $avg_data.avg_b_rate    = [Math]::Round($total_b  / $n, 4)
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

