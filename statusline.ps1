# statusline.ps1
# Runs after each assistant message. Outputs session KPIs with rolling-average trend comparison.
#
# Layout (no history):   6p  1o  1a  |  69%  $3.45  34m
# Layout (with history): 6p  1o/11%  2a/22%  |  78%  $4.52  3h 54m
# Layout (retro needed): !  6p  1o/11%  2a/22%  |  78%  $4.52  3h 54m
#
#   Np      N prompts this session (cyan)
#   No/R%   N overrides / R% rate (red label; rate color = red if above avg, green if below)
#   Na/R%   N add/alt   / R% rate (yellow label; same rate coloring)
#   Nd/R%   N denied+ctx / R% rate (red; only shown when > 0)
#   !       retro threshold reached — run /retrospect (red prefix, reads cumulative.json)
#   |       separator before meta
#   %       context window used (green/yellow/red, no label)
#   $       session cost (dim)
#   Xm      elapsed time (dim)
#   |/-\    ASCII spinner — Claude is currently running (yellow)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding            = [System.Text.Encoding]::UTF8

$E      = [char]27
$reset  = "${E}[0m"
$cyan   = "${E}[36m"
$green  = "${E}[32m"
$yellow = "${E}[33m"
$red    = "${E}[31m"
$dim    = "${E}[2m"

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
$stdin_session_id = if ($ctx_data -and $ctx_data.session_id) { [string]$ctx_data.session_id } else { $null }
$model_name = if ($ctx_data -and $ctx_data.model -and $ctx_data.model.display_name) { [string]$ctx_data.model.display_name } else { $null }

# --- Read session KPIs ---
# Per-session state file (keyed by session_id) so parallel terminals don't collide.
$state_file = if ($stdin_session_id) { "$HOME\.claude\telemetry\state-$stdin_session_id.json" } else { $null }
$state = if ($state_file -and (Test-Path $state_file)) {
    try { Get-Content $state_file -Raw | ConvertFrom-Json -ErrorAction Stop } catch { $null }
} else { $null }

$p  = if ($state) { [int]$state.prompts         } else { 0 }
$o  = if ($state) { [int]$state.overrides       } else { 0 }
$a  = if ($state) { [int]$state.additions       } else { 0 }
$dc = if ($state -and $state.PSObject.Properties['denial_contexts']) { [int]$state.denial_contexts } else { 0 }

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
$avg_file = "$HOME\.claude\telemetry\rolling-averages.json"
$avg_data = if (Test-Path $avg_file) {
    try { Get-Content $avg_file -Raw | ConvertFrom-Json -ErrorAction Stop } catch { $null }
} else { $null }

$has_history = $avg_data -and ([int]$avg_data.session_count) -ge 2

# --- Retro check (reads cumulative without cost to context window) ---
$retro_needed = $false
$cum_file = "$HOME\.claude\telemetry\cumulative.json"
$cum_data = if (Test-Path $cum_file) {
    try { Get-Content $cum_file -Raw | ConvertFrom-Json -ErrorAction Stop } catch { $null }
} else { $null }
if ($cum_data) {
    $retro_needed = (
        ([int]$cum_data.sessions_since_review) -ge 3 -and
        ([int]$cum_data.total_score) -ge 6
    )
}

# --- Format friction stats ---
$friction_str = ''

if ($has_history -and $p -gt 0) {
    $o_rate  = $o  / $p
    $a_rate  = $a  / $p
    $dc_rate = $dc / $p
    $avg_o   = if ($avg_data.avg_o_rate)  { [double]$avg_data.avg_o_rate  } else { 0.0 }
    $avg_a   = if ($avg_data.avg_a_rate)  { [double]$avg_data.avg_a_rate  } else { 0.0 }
    $avg_dc  = if ($avg_data.avg_dc_rate) { [double]$avg_data.avg_dc_rate } else { 0.0 }

    $o_trend  = Get-Trend $o_rate  $avg_o
    $a_trend  = Get-Trend $a_rate  $avg_a
    $dc_trend = Get-Trend $dc_rate $avg_dc

    $o_pct  = [int]($o_rate  * 100)
    $a_pct  = [int]($a_rate  * 100)
    $dc_pct = [int]($dc_rate * 100)

    $o_col  = Color-By-Rate $o_rate
    $dc_col = Color-By-Rate $dc_rate

    # Rate color encodes trend: red = above avg (worse), green = below avg (better), reset = flat
    $o_rate_col  = if ($o_trend  -eq '+') { $red } elseif ($o_trend  -eq '-') { $green } else { $reset }
    $a_rate_col  = if ($a_trend  -eq '+') { $red } elseif ($a_trend  -eq '-') { $green } else { $reset }
    $dc_rate_col = if ($dc_trend -eq '+') { $red } elseif ($dc_trend -eq '-') { $green } else { $reset }

    if ($o  -gt 0) { $friction_str += "  ${red}${o} Overrides${reset}/${o_rate_col}${o_pct}%${reset}"   }
    if ($a  -gt 0) { $friction_str += "  ${yellow}${a} Add/Alt${reset}/${a_rate_col}${a_pct}%${reset}" }
    if ($dc -gt 0) { $friction_str += "  ${red}${dc} Denied+ctx${reset}/${dc_rate_col}${dc_pct}%${reset}" }
} else {
    if ($o  -gt 0) { $friction_str += "  ${red}${o} Overrides${reset}"    }
    if ($a  -gt 0) { $friction_str += "  ${yellow}${a} Add/Alt${reset}" }
    if ($dc -gt 0) { $friction_str += "  ${red}${dc} Denied+ctx${reset}"   }
}

# --- Format meta (ctx%, cost) ---
$meta_parts = @()
if ($null -ne $ctx_pct) {
    # Context zones (informed by context-rot research + proactive-compact practice):
    #   < 60%  green  — healthy
    #   60-79% yellow — warning: compact at the next logical boundary
    #   >= 80% red    — red zone: compact now (shows "ctx" label)
    if ($ctx_pct -ge 80) {
        $meta_parts += "${red}ctx ${ctx_pct}% COMPACT${reset}"
    } elseif ($ctx_pct -ge 60) {
        $meta_parts += "${yellow}ctx ${ctx_pct}%${reset}"
    } else {
        $meta_parts += "${green}ctx ${ctx_pct}%${reset}"
    }
}
if ($null -ne $cost_usd) {
    $cost_str = '$' + ([Math]::Round($cost_usd, 2).ToString('F2'))
    $meta_parts += "${dim}${cost_str}${reset}"
}
$meta = if ($meta_parts.Count -gt 0) { "  ${dim}|${reset}  " + ($meta_parts -join '  ') } else { '' }

# --- Spinner when Claude is running ---
$running_flag = if ($stdin_session_id) { "$HOME\.claude\telemetry\running-$stdin_session_id.flag" } else { "$HOME\.claude\telemetry\running.flag" }
$spinner = ''
if (Test-Path $running_flag) {
    $frames = @('|', '/', '-', '\')
    $frame  = $frames[[int](([datetime]::Now.Second * 4 + [int]([datetime]::Now.Millisecond / 250)) % $frames.Length)]
    $spinner = "  ${yellow}${frame}${reset}"
}

$retro_pfx = if ($retro_needed) { "${red}!retro${reset}  " } else { '' }
# Only show the prompt count when we have a real positive number for THIS session;
# otherwise omit it rather than display a misleading 0.
$p_str     = if ($p -gt 0) { "${cyan}${p} Prompts${reset}" } else { '' }

# Effort: stdin `effort` is a string or {level:"high"} object (live, per-session); fall back to settings.json.
# IMPORTANT: capture values by assignment — never put `$ctx_data.effort` bare in a condition,
# or PowerShell 5.1 emits it to the success stream (leaked "@{level=high}" into the bar).
$effort  = $null
$eff_val = $null
if ($ctx_data -and $ctx_data.PSObject.Properties['effort']) { $eff_val = $ctx_data.effort }
if ($null -ne $eff_val) {
    if ($eff_val -is [string]) { $effort = $eff_val }
    elseif ($eff_val.PSObject.Properties['level']) { $effort = [string]$eff_val.level }
}
if (-not $effort) {
    $cfg = try { Get-Content "$HOME\.claude\settings.json" -Raw | ConvertFrom-Json -ErrorAction Stop } catch { $null }
    $cfg_eff = if ($cfg) { $cfg.effortLevel } else { $null }
    if ($null -ne $cfg_eff) {
        if ($cfg_eff -is [string]) { $effort = $cfg_eff }
        elseif ($cfg_eff.PSObject.Properties['level']) { $effort = [string]$cfg_eff.level }
    }
}
# Abbreviate effort: low=L med=M high=H xhigh=XH max=MX auto=A
$eff_abbr = $null
if ($effort) {
    $el = $effort.ToString().ToLower()
    $eff_abbr = switch -Exact ($el) {
        'low' { 'L' } 'medium' { 'M' } 'high' { 'H' } 'xhigh' { 'XH' } 'max' { 'MX' } 'auto' { 'A' }
        default { $el.Substring(0, [Math]::Min(2, $el.Length)).ToUpper() }
    }
}

# Short model label: tier code + version, with effort suffix (e.g. "OP 4.8-high")
$model_str = ''
if ($model_name) {
    $tier = if ($model_name -match 'Opus') { 'OP' } elseif ($model_name -match 'Sonnet') { 'SN' } elseif ($model_name -match 'Haiku') { 'HK' } elseif ($model_name -match 'Fable') { 'FB' } else { ($model_name.Substring(0, [Math]::Min(2, $model_name.Length))).ToUpper() }
    $mcol = if ($model_name -match 'Opus') { "${E}[35m" } elseif ($model_name -match 'Sonnet') { "${E}[34m" } elseif ($model_name -match 'Haiku') { $green } else { $cyan }
    $ver  = if ($model_name -match '(\d+(?:\.\d+)?)') { $Matches[1] } else { '' }
    $eff_str = if ($eff_abbr) { "${dim} ${eff_abbr}${reset}" } else { '' }
    $model_str = "${mcol}${tier}${ver}${reset}${eff_str}  "
}

# --- Agent breadcrumb (2nd row): currentTask from THIS session's helm-status.json ---
# stdin carries the session's own cwd, so this is inherently per-session/per-tab —
# no staleness or wrong-project bug like a shared terminal status bar had. Gets its
# own full-width row (multi-line statusLine), so the full task text fits.
$HELM_FRESH_HOURS = 24   # hide tasks older than this (tune to taste)
$task_line = ''
$cwd = if ($ctx_data -and $ctx_data.workspace -and $ctx_data.workspace.current_dir) {
    [string]$ctx_data.workspace.current_dir
} elseif ($ctx_data -and $ctx_data.cwd) { [string]$ctx_data.cwd } else { $null }

if ($cwd) {
    $helm_file = Join-Path $cwd 'helm-status.json'
    if (Test-Path $helm_file) {
        # try/catch: the file may be mid-write by an agent — a partial read just skips this tick.
        $helm = try { Get-Content $helm_file -Raw | ConvertFrom-Json -ErrorAction Stop } catch { $null }
        if ($helm -and $helm.currentTask) {
            $fresh = $true
            if ($helm.updatedAt) {
                try {
                    $age_h = ([DateTime]::UtcNow - [DateTimeOffset]::Parse([string]$helm.updatedAt).UtcDateTime).TotalHours
                    $fresh = $age_h -lt $HELM_FRESH_HOURS
                } catch { $fresh = $true }
            }
            if ($fresh) {
                $task = ([string]$helm.currentTask) -replace '\s+', ' '
                # Size to the terminal width (Claude Code sets $env:COLUMNS) so the row never wraps.
                $cols = 100
                if ($env:COLUMNS) { $tmp = 0; if ([int]::TryParse($env:COLUMNS, [ref]$tmp)) { $cols = $tmp } }
                $max = [Math]::Max(20, $cols - 4)
                if ($task.Length -gt $max) { $task = $task.Substring(0, $max - 1) + [char]0x2026 }
                $task_line = "${dim}" + [char]0x25B8 + " ${task}${reset}"
            }
        }
    }
}

Write-Host "${model_str}${retro_pfx}${p_str}${friction_str}${meta}${runtime_str}${spinner}"
if ($task_line) { Write-Host $task_line }
