# Weekly context lifecycle cycle: projects_sweep.py --apply archives unread memory, snapshots and scratch, deletes what
# has sat in an archive past its cycle (cycles in upkeep_config.py), and commits only the fleet docs paths it moved.
# Any failed move or git step makes it exit 1, so the task shows a failure. Registered by register-context-sweep.ps1
# (\Claude\context-sweep, Sundays 06:00, hidden). Log: ~/.claude/logs/context-sweep/<date>.log.
$ErrorActionPreference = 'Continue'
$LogDir = Join-Path $env:USERPROFILE '.claude\logs\context-sweep'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir ("{0}.log" -f (Get-Date -Format 'yyyy-MM-dd'))
Add-Content -Path $Log -Value ("=== {0} start ===" -f (Get-Date -Format 's')) -Encoding utf8
& python (Join-Path $PSScriptRoot 'projects_sweep.py') --apply 2>&1 | ForEach-Object { Add-Content -Path $Log -Value $_ -Encoding utf8 }
$rc = $LASTEXITCODE
Add-Content -Path $Log -Value ("=== {0} exit {1} ===" -f (Get-Date -Format 's'), $rc) -Encoding utf8
exit $rc
