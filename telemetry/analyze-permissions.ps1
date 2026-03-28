# analyze-permissions.ps1
# Reads permission-log.jsonl and surfaces patterns for settings optimization.
# Run manually: powershell.exe -NoProfile -File C:\Users\Michael\.claude\telemetry\analyze-permissions.ps1

$log = "C:\Users\Michael\.claude\telemetry\permission-log.jsonl"

if (-not (Test-Path $log)) {
    Write-Host "No permission log found at $log"
    exit
}

$entries = Get-Content $log | Where-Object { $_ -ne '' } | ForEach-Object {
    try { $_ | ConvertFrom-Json } catch { $null }
} | Where-Object { $_ -ne $null }

if ($entries.Count -eq 0) {
    Write-Host "Permission log is empty — no data yet."
    exit
}

Write-Host ""
Write-Host "=== Permission Request Analysis ===" -ForegroundColor Cyan
Write-Host "Total recorded requests: $($entries.Count)"
Write-Host ""

# Group by tool name
$byTool = $entries | Group-Object -Property tool_name | Sort-Object Count -Descending
Write-Host "--- Requests by Tool ---" -ForegroundColor Yellow
foreach ($g in $byTool) {
    Write-Host ("  {0,-25} {1} requests" -f $g.Name, $g.Count)
}

# Group Bash commands by prefix (first token)
$bashEntries = $entries | Where-Object { $_.tool -eq 'Bash' }
if ($bashEntries.Count -gt 0) {
    Write-Host ""
    Write-Host "--- Bash Command Prefixes (top 15) ---" -ForegroundColor Yellow
    $prefixes = $bashEntries | ForEach-Object {
        $cmd = $_.input.command -replace '^\s+',''
        ($cmd -split '\s+')[0]
    } | Group-Object | Sort-Object Count -Descending | Select-Object -First 15
    foreach ($p in $prefixes) {
        Write-Host ("  {0,-25} {1} occurrences" -f $p.Name, $p.Count)
    }

    # Suggest allow rules for frequent Bash patterns
    Write-Host ""
    Write-Host "--- Suggested allow rules for .claude/settings.json ---" -ForegroundColor Green
    $frequent = $prefixes | Where-Object { $_.Count -ge 3 }
    if ($frequent.Count -gt 0) {
        Write-Host '  "allow": ['
        foreach ($p in $frequent) {
            Write-Host ("    `"Bash({0}:*)`"," -f $p.Name)
        }
        Write-Host '  ]'
    } else {
        Write-Host "  No command runs 3+ times yet — check back after more sessions."
    }
}

# Project breakdown
Write-Host ""
Write-Host "--- Requests by Working Directory ---" -ForegroundColor Yellow
$byCwd = $entries | Group-Object -Property cwd | Sort-Object Count -Descending
foreach ($g in $byCwd) {
    Write-Host ("  {0,-50} {1} requests" -f $g.Name, $g.Count)
}

Write-Host ""
Write-Host "Log file: $log  ($($entries.Count) entries)"
Write-Host "To clear: Remove-Item '$log'; New-Item '$log' -ItemType File"
Write-Host ""
