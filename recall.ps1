# recall.ps1
# Prints the recent distinct themes (reverse-chronological, up to 3) for the
# active Claude Code session in the CURRENT repo. Zero-token — reads the
# per-session telemetry state that log-prompt.ps1 maintains.
#
# Usage (from a Claude Code prompt):  ! powershell -NoProfile -File ~/.claude/recall.ps1
# Multi-tenancy: themes are keyed per (repo, session). This viewer filters state
# files by the current working directory, then picks the most recently active
# session in this repo. (Concurrent sessions in the SAME repo+terminal can't be
# disambiguated without the session_id, so the most-recent one wins.)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$E     = [char]27
$reset = "${E}[0m"; $cyan = "${E}[36m"; $dim = "${E}[2m"; $bold = "${E}[1m"

function Norm([string]$p) { if (-not $p) { return '' } ($p -replace '/', '\').TrimEnd('\').ToLower() }
$cwd = Norm((Get-Location).Path)
$dir = "$HOME\.claude\telemetry"

$candidates = Get-ChildItem "$dir\state-*.json" -ErrorAction SilentlyContinue | ForEach-Object {
    $s = try { Get-Content $_.FullName -Raw | ConvertFrom-Json -ErrorAction Stop } catch { $null }
    if ($s -and (Norm($s.cwd)) -eq $cwd) {
        [PSCustomObject]@{ state = $s; mtime = $_.LastWriteTime }
    }
} | Where-Object { $_ } | Sort-Object mtime -Descending

if (-not $candidates) {
    Write-Host "${dim}No recent themes recorded for this repo yet.${reset}"
    exit 0
}

$themes = @($candidates[0].state.themes)
if (-not $themes -or $themes.Count -eq 0) {
    Write-Host "${dim}No themes recorded yet this session.${reset}"
    exit 0
}

$labels = @('Last', '2nd last', '3rd last')
Write-Host "${bold}Recent themes (this repo):${reset}"
for ($i = 0; $i -lt [Math]::Min(3, $themes.Count); $i++) {
    $t = $themes[$i]
    $turns = if ($t.PSObject.Properties['turns'] -and [int]$t.turns -gt 1) { " ${dim}($($t.turns) turns)${reset}" } else { '' }
    Write-Host ("  ${cyan}- {0}:${reset} {1}{2}" -f $labels[$i], $t.label, $turns)
}
