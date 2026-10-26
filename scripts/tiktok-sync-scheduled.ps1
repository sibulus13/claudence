# Daily post review for @chase.ride: runs the tiktok-sync skill headless with Claude in Chrome.
# Registered by register-tiktok-sync.ps1 (Task Scheduler \Claude\tiktok-sync, 21:30 daily, hidden).
# The skill exits early ("nothing to review" / "chrome not connected"), so a quiet day costs little.
$ErrorActionPreference = 'Continue'
$MaxBudgetUsd = 3
$LogDir = Join-Path $env:USERPROFILE '.claude\logs\tiktok-sync'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir ("{0}.log" -f (Get-Date -Format 'yyyy-MM-dd'))
$Claude = Join-Path $env:USERPROFILE '.local\bin\claude.exe'
$Tools = @(
  'mcp__plugin_Notion_notion__notion-fetch',
  'mcp__plugin_Notion_notion__notion-query-data-sources',
  'mcp__plugin_Notion_notion__notion-update-page',
  'mcp__claude-in-chrome',
  'Bash(python:*)', 'Read', 'Write', 'Skill'
)
Add-Content -Path $Log -Value ("=== {0} start ===" -f (Get-Date -Format 's')) -Encoding utf8
Set-Location 'D:\repo\SaaS\nuwa\docs\work\own-style-analysis'
# Unattended run: hooks/guard.py skips its interactive-only rules (Notion write = ask) for this job only.
$env:CLAUDE_UNATTENDED = '1'
& $Claude -p '/tiktok-sync scheduled' --chrome --model sonnet --max-budget-usd $MaxBudgetUsd --allowedTools ($Tools -join ',') 2>&1 |
  ForEach-Object { Add-Content -Path $Log -Value $_ -Encoding utf8 }
$rc = $LASTEXITCODE
Add-Content -Path $Log -Value ("=== {0} exit {1} ===" -f (Get-Date -Format 's'), $rc) -Encoding utf8
exit $rc
