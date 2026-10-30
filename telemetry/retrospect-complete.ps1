# retrospect-complete.ps1
# Called by /retrospect (step 4) once a run has finished: archives the analyzed friction reports and resets the
# cumulative counters. This is the ONLY place the counters reset; the Stop-hook nag (analyze-session.ps1) never does.
param(
    [string]$ReportsDir     = "$HOME\.claude\telemetry\reports",
    [string]$CumulativeFile = "$HOME\.claude\telemetry\cumulative.json"
)
$ErrorActionPreference = 'Stop'

$archive = Join-Path $ReportsDir 'archived'
New-Item -ItemType Directory -Path $archive -Force | Out-Null
$reports = @(Get-ChildItem -Path $ReportsDir -Filter '*.json' -File)
foreach ($r in $reports) { Move-Item -LiteralPath $r.FullName -Destination $archive -Force }

[PSCustomObject]@{
    total_score           = 0
    sessions_since_review = 0
    last_review_ts        = (Get-Date -Format 'o')
} | ConvertTo-Json | Set-Content $CumulativeFile

Write-Output "retrospect complete: archived $($reports.Count) reports, counters reset"
