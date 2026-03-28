# statusline.ps1
# Runs after each assistant message. Outputs session KPIs with rolling-average trend comparison.
#
# Layout (no history):   Prompts:4  Overrides:1  Blocked:2  |  ctx 12%  $0.08  5m
# Layout (with history): Prompts:4  Overrides:1 25%+  Additions:2 50%  Blocked:1 25%-  |  ctx 67%  $0.13  12m
#
#   Prompts    prompts sent this session (cyan)
#   Overrides  user replaced direction — high friction (red label, yellow/red by rate)
#   Additions  user injected context — low friction (yellow label, shown only if > 0)
#   Blocked    tool calls that needed approval (red label); repeats always red
#   ctx        context window used % (green/yellow/red)
#   $          session cost (dim)
#   Xm / Xh Xm session elapsed time (dim)
#
#   With >=2 sessions of history: Overrides and Blocked show rate% and trend
#   Trend: + worse than avg, - better than avg (only when non-zero)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding            = [System.Text.Encoding]::UTF8

$E      = [char]27
$reset  = "${E}[0m"
$cyan   = "${E}[36m"
$green  = "${E}[32m"
$yellow = "${E}[33m"
$red    = "${E}[31m"
$dim    = "${E}[2m"

function Color-By-Count([int]$val, [int]$warn, [int]$crit) {
    if ($val -ge $crit) { return $red }
    if ($val -ge $warn) { return $yellow }
    return $reset
}

function Color-By-Rate([double]$rate) {
    if ($rate -ge 0.5)  { return $red }
    if ($rate -ge 0.25) { return $yellow }
    return $reset
}

# Trend relative to rolling average. Threshold: 10 percentage points.
# Returns: '+' worse, '-' better, '' flat (not shown)
function Get-Trend([double]$cur, [double]$avg) {
    $diff = $cur - $avg
    if ($diff -gt 0.10)  { return '+' }
    if ($diff -lt -0.10) { return '-' }
    return ''
}

function Trend-Color([string]$t) {
    if ($t -eq '+') { return $red   }
    if ($t -eq '-') { return $green }
    return $reset
}

# --- Read statusLine stdin (context window, cost) ---
$stdin_raw = [Console]::In.ReadToEnd()
$ctx_data  = try { $stdin_raw | ConvertFrom-Json -ErrorAction Stop } catch { $null }

$ctx_pct  = if ($ctx_data -and $ctx_data.context_window -and ($null -ne $ctx_data.context_window.used_percentage)) {
    [int]$ctx_data.context_window.used_percentage
} else { $null }
$cost_usd = if ($ctx_data -and $ctx_data.cost -and ($null -ne $ctx_data.cost.total_cost_usd)) {
    $ctx_data.cost.total_cost_usd
} else { $null }

# --- Read session KPIs ---
$state_file = "C:\Users\Michael\.claude\telemetry\current-session.json"
$state = if (Test-Path $state_file) {
    try { Get-Content $state_file -Raw | ConvertFrom-Json -ErrorAction Stop } catch { $null }
} else { $null }

$p  = if ($state) { [int]$state.prompts      } else { 0 }
$o  = if ($state) { [int]$state.overrides    } else { 0 }
$a  = if ($state) { [int]$state.additions    } else { 0 }
$b  = if ($state) { [int]$state.perm_reqs    } else { 0 }
$br = if ($state) { [int]$state.perm_repeats } else { 0 }

# --- Session runtime ---
$runtime_str = ''
if ($state -and $state.started_at) {
    $elapsed_min = [int](([DateTime]::Now - [DateTime]::Parse($state.started_at)).TotalMinutes)
    $runtime_str = if ($elapsed_min -ge 60) {
        $h = [int]($elapsed_min / 60); $m = $elapsed_min % 60
        "  ${dim}${h}h ${m}m${reset}"
    } else {
        "  ${dim}${elapsed_min}m${reset}"
    }
}

# --- Read rolling averages ---
$avg_file = "C:\Users\Michael\.claude\telemetry\rolling-averages.json"
$avg_data = if (Test-Path $avg_file) {
    try { Get-Content $avg_file -Raw | ConvertFrom-Json -ErrorAction Stop } catch { $null }
} else { $null }

$has_history = $avg_data -and ([int]$avg_data.session_count) -ge 2

# --- Format Overrides, Additions, Blocked ---
$all_b = $b + $br

if ($has_history -and $p -gt 0) {
    $o_rate = $o     / $p
    $a_rate = $a     / $p
    $b_rate = $all_b / $p
    $avg_o  = if ($avg_data.avg_o_rate) { [double]$avg_data.avg_o_rate } else { 0.0 }
    $avg_a  = if ($avg_data.avg_a_rate) { [double]$avg_data.avg_a_rate } else { 0.0 }
    $avg_b  = if ($avg_data.avg_b_rate) { [double]$avg_data.avg_b_rate } else { 0.0 }

    $o_trend = Get-Trend $o_rate $avg_o
    $b_trend = Get-Trend $b_rate $avg_b
    $o_pct   = [int]($o_rate * 100)
    $a_pct   = [int]($a_rate * 100)
    $b_pct   = [int]($b_rate * 100)
    $ot_col  = Trend-Color $o_trend
    $bt_col  = Trend-Color $b_trend
    $o_val   = Color-By-Rate $o_rate
    $b_val   = Color-By-Rate $b_rate

    # Rate% and trend only shown when non-zero
    $o_rate_str = if ($o -gt 0) { " ${o_pct}%${reset}${ot_col}${o_trend}" } else { '' }
    $a_rate_str = if ($a -gt 0) { " ${a_pct}%" } else { '' }
    $b_rate_str = if ($all_b -gt 0) { " ${b_pct}%${reset}${bt_col}${b_trend}" } else { '' }
    $br_col     = if ($br -gt 0) { $red } else { $reset }

    $o_str  = "${red}Overrides:${reset}${o_val}${o}${o_rate_str}${reset}"
    $a_str  = if ($a -gt 0) { "  ${yellow}Additions:${reset}${a}${a_rate_str}${reset}" } else { '' }
    $b_str  = "${red}Blocked:${reset}${b_val}${all_b}${b_rate_str}${reset}"
    $br_str = if ($br -gt 0) { " ${br_col}(${br}x repeats)${reset}" } else { '' }
} else {
    $o_val = Color-By-Count $o 1 3
    $b_val = Color-By-Count $all_b 1 3

    $o_str  = "${red}Overrides:${reset}${o_val}${o}${reset}"
    $a_str  = if ($a -gt 0) { "  ${yellow}Additions:${reset}${a}${reset}" } else { '' }
    $b_str  = "${red}Blocked:${reset}${b_val}${all_b}${reset}"
    $br_str = if ($br -gt 0) { " ${red}(${br}x repeats)${reset}" } else { '' }
}

# --- Format Prompts ---
$p_str = "${cyan}Prompts:${reset}${p}"

# --- Format meta (ctx, cost) ---
$meta_parts = @()
if ($null -ne $ctx_pct) {
    $ctx_val = if ($ctx_pct -ge 80) { $red } elseif ($ctx_pct -ge 50) { $yellow } else { $green }
    $meta_parts += "${green}ctx ${reset}${ctx_val}${ctx_pct}%${reset}"
}
if ($null -ne $cost_usd) {
    $cost_str = '$' + ([Math]::Round($cost_usd, 2).ToString('F2'))
    $meta_parts += "${dim}${cost_str}${reset}"
}
$meta = if ($meta_parts.Count -gt 0) { "  ${dim}|${reset}  " + ($meta_parts -join '  ') } else { '' }

Write-Host "${p_str}  ${o_str}${a_str}  ${b_str}${br_str}${meta}${runtime_str}"
