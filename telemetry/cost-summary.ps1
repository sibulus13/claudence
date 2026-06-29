# cost-summary.ps1
# Reads cost-ledger.jsonl and prints per-project cost, session counts, friction,
# and hourly/daily breakdowns. Useful for understanding benefit-to-cost ratio
# across projects and spotting expensive sessions.
#
# Usage:
#   powershell.exe -NoProfile -File cost-summary.ps1              # all time
#   powershell.exe -NoProfile -File cost-summary.ps1 -Days 7      # last 7 days
#   powershell.exe -NoProfile -File cost-summary.ps1 -Days 1      # today
#   powershell.exe -NoProfile -File cost-summary.ps1 -Hourly      # hourly buckets

param(
    [int]$Days   = 0,
    [switch]$Hourly
)

$E      = [char]27
$reset  = "${E}[0m"
$cyan   = "${E}[36m"
$green  = "${E}[32m"
$yellow = "${E}[33m"
$red    = "${E}[31m"
$dim    = "${E}[2m"
$bold   = "${E}[1m"

function Fmt-Cost([double]$c) {
    '$' + ('{0:F4}' -f $c)
}

function Short-Path([string]$p) {
    if (-not $p) { return '(unknown)' }
    $s = $p -replace '^[A-Za-z]:[/\\]Users[/\\]Michael[/\\]', '~/'
    $s = $s -replace '^[A-Za-z]:[/\\]repo[/\\]', 'repo/'
    return $s
}

$ledger_file = "C:\Users\Michael\.claude\telemetry\cost-ledger.jsonl"
if (-not (Test-Path $ledger_file)) {
    Write-Host "${yellow}No cost-ledger.jsonl found yet. Cost tracking begins after the next session ends.${reset}"
    exit 0
}

$entries = Get-Content $ledger_file -ErrorAction SilentlyContinue |
    Where-Object { $_ -ne '' } |
    ForEach-Object { try { $_ | ConvertFrom-Json -ErrorAction Stop } catch { $null } } |
    Where-Object { $_ -ne $null }

if ($entries.Count -eq 0) {
    Write-Host "${yellow}Cost ledger is empty.${reset}"
    exit 0
}

$cutoff   = if ($Days -gt 0) { [DateTime]::Now.AddDays(-$Days) } else { [DateTime]::MinValue }
$filtered = @($entries | Where-Object {
    $ts = try { [DateTime]::Parse($_.ts) } catch { [DateTime]::MinValue }
    $ts -ge $cutoff
})

if ($filtered.Count -eq 0) {
    Write-Host "${yellow}No sessions found in the last $Days day(s).${reset}"
    exit 0
}

$known_cost   = @($filtered | Where-Object { $null -ne $_.cost_usd })
$unknown_cost = @($filtered | Where-Object { $null -eq $_.cost_usd })
$total_cost   = if ($known_cost.Count -gt 0) { ($known_cost | Measure-Object -Property cost_usd -Sum).Sum } else { 0.0 }
$total_sess   = $filtered.Count
$period_label = if ($Days -gt 0) { "last $Days day(s)" } else { "all time" }
$missing_note = if ($unknown_cost.Count -gt 0) { "  ($($unknown_cost.Count) missing cost data)" } else { '' }

Write-Host ''
Write-Host "${bold}${cyan}=== Cost Summary -- $period_label ===${reset}"
Write-Host "${dim}$total_sess sessions  |  $(Fmt-Cost $total_cost) total${missing_note}${reset}"
Write-Host ''

# -- Per-project breakdown -----------------------------------------------------
$col_w = 45
Write-Host "${bold}By Project${reset}"
Write-Host "${dim}$('Project'.PadRight($col_w))  Sessions     Total   Avg/sess  AvgFriction  AvgElapsed${reset}"
Write-Host "${dim}$('-' * $col_w)  --------  --------  ---------  -----------  ----------${reset}"

$by_project = $filtered |
    Group-Object { if ($_.cwd) { $_.cwd } else { '(unknown)' } } |
    Sort-Object {
        $s = ($_.Group | Where-Object { $null -ne $_.cost_usd } | Measure-Object -Property cost_usd -Sum).Sum
        if ($null -eq $s) { 0.0 } else { [double]$s }
    } -Descending

foreach ($proj in $by_project) {
    $sessions    = $proj.Group
    $proj_n      = $sessions.Count
    $proj_known  = @($sessions | Where-Object { $null -ne $_.cost_usd })
    $proj_cost   = if ($proj_known.Count -gt 0) { ($proj_known | Measure-Object -Property cost_usd -Sum).Sum } else { 0.0 }
    $avg_cost    = if ($proj_known.Count -gt 0) { $proj_cost / $proj_known.Count } else { 0.0 }

    $score_vals  = @($sessions | Where-Object { $null -ne $_.score } | ForEach-Object { [double]$_.score })
    $avg_score   = if ($score_vals.Count -gt 0) { ($score_vals | Measure-Object -Sum).Sum / $score_vals.Count } else { 0.0 }

    $elapsed_vals = @($sessions | Where-Object { $null -ne $_.elapsed_sec } | ForEach-Object { [double]$_.elapsed_sec })
    $avg_elapsed  = if ($elapsed_vals.Count -gt 0) { ($elapsed_vals | Measure-Object -Sum).Sum / $elapsed_vals.Count } else { $null }

    $label = Short-Path $proj.Name
    if ($label.Length -gt ($col_w - 1)) { $label = '...' + $label.Substring($label.Length - ($col_w - 4)) }

    $cost_col    = if ($proj_cost -ge 5) { $red } elseif ($proj_cost -ge 1) { $yellow } else { $reset }
    $score_col   = if ($avg_score -ge 5) { $red } elseif ($avg_score -ge 2) { $yellow } else { $green }
    $elapsed_str = if ($null -ne $avg_elapsed) { "$([int]($avg_elapsed / 60))m $([int]($avg_elapsed % 60))s" } else { 'n/a' }
    $score_str   = [Math]::Round($avg_score, 1).ToString()

    Write-Host ($label.PadRight($col_w) + '  ' + $proj_n.ToString().PadLeft(8) + '  ' +
        $cost_col + (Fmt-Cost $proj_cost).PadLeft(8) + $reset + '  ' +
        (Fmt-Cost $avg_cost).PadLeft(9) + '  ' +
        $score_col + $score_str.PadLeft(11) + $reset + '  ' +
        $elapsed_str.PadLeft(10))
}

# -- Timeline ------------------------------------------------------------------
Write-Host ''
if ($Hourly) {
    Write-Host "${bold}Hourly Distribution${reset}"
    Write-Host "${dim}$('Hour'.PadRight(20))  Sessions       Cost  Bar${reset}"
    Write-Host "${dim}$('-' * 20)  --------  ---------  ---${reset}"

    $buckets = $known_cost |
        Group-Object { [DateTime]::Parse($_.ts).ToString('yyyy-MM-dd HH:00') } |
        Sort-Object Name

    $max_cost = ($buckets | ForEach-Object { ($_.Group | Measure-Object -Property cost_usd -Sum).Sum } |
        Measure-Object -Maximum).Maximum
    if (-not $max_cost -or $max_cost -le 0) { $max_cost = 0.01 }

    foreach ($b in $buckets) {
        $bc       = ($b.Group | Measure-Object -Property cost_usd -Sum).Sum
        $bn       = $b.Group.Count
        $bar      = '#' * [Math]::Max([int]($bc / $max_cost * 30), 1)
        $cost_col = if ($bc -ge 2) { $red } elseif ($bc -ge 0.5) { $yellow } else { $dim }
        Write-Host ($b.Name.PadRight(20) + '  ' + $bn.ToString().PadLeft(8) + '  ' +
            $cost_col + (Fmt-Cost $bc).PadLeft(9) + $reset + '  ' + $bar)
    }
} else {
    Write-Host "${bold}Daily Distribution${reset}"
    Write-Host "${dim}$('Date'.PadRight(12))  Sessions       Cost  Bar${reset}"
    Write-Host "${dim}$('-' * 12)  --------  ---------  ---${reset}"

    $buckets = $known_cost |
        Group-Object { [DateTime]::Parse($_.ts).ToString('yyyy-MM-dd') } |
        Sort-Object Name

    $max_cost = ($buckets | ForEach-Object { ($_.Group | Measure-Object -Property cost_usd -Sum).Sum } |
        Measure-Object -Maximum).Maximum
    if (-not $max_cost -or $max_cost -le 0) { $max_cost = 0.01 }

    foreach ($b in $buckets) {
        $bc       = ($b.Group | Measure-Object -Property cost_usd -Sum).Sum
        $bn       = $b.Group.Count
        $bar      = '#' * [Math]::Max([int]($bc / $max_cost * 30), 1)
        $cost_col = if ($bc -ge 5) { $red } elseif ($bc -ge 1) { $yellow } else { $dim }
        Write-Host ($b.Name.PadRight(12) + '  ' + $bn.ToString().PadLeft(8) + '  ' +
            $cost_col + (Fmt-Cost $bc).PadLeft(9) + $reset + '  ' + $bar)
    }
}

# -- Top expensive sessions ----------------------------------------------------
Write-Host ''
Write-Host "${bold}Top 5 Most Expensive Sessions${reset}"
Write-Host "${dim}$('Session'.PadRight(10))  $('Project'.PadRight(32))      Cost  Prompts  Score  Elapsed${reset}"
Write-Host "${dim}$('-' * 10)  $('-' * 32)  --------  -------  -----  -------${reset}"

$top5 = @($known_cost | Sort-Object cost_usd -Descending | Select-Object -First 5)
foreach ($s in $top5) {
    $label = Short-Path $s.cwd
    if ($label.Length -gt 31) { $label = '...' + $label.Substring($label.Length - 28) }
    $elapsed_str = if ($null -ne $s.elapsed_sec) { "$([int]($s.elapsed_sec / 60))m $([int]($s.elapsed_sec % 60))s" } else { 'n/a' }
    $score_col   = if ($s.score -ge 5) { $red } elseif ($s.score -ge 2) { $yellow } else { $green }
    $sid         = if ($s.session_id) { $s.session_id } else { '?' }

    Write-Host ($sid.PadRight(10) + '  ' + $label.PadRight(32) + '  ' +
        (Fmt-Cost $s.cost_usd).PadLeft(8) + '  ' +
        $s.prompt_count.ToString().PadLeft(7) + '  ' +
        $score_col + $s.score.ToString().PadLeft(5) + $reset + '  ' +
        $elapsed_str)
}

Write-Host ''
