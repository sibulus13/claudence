# Weekly context lifecycle cycle: archives unread memory, snapshots and scratch, deletes what has sat in an archive
# past its cycle (projects_sweep.py --apply; cycles in upkeep_config.py), then commits only the fleet docs paths it
# moved, never other work in progress. Registered by register-context-sweep.ps1 (\Claude\context-sweep, Sundays 06:00).
$ErrorActionPreference = 'Continue'
$LogDir = Join-Path $env:USERPROFILE '.claude\logs\context-sweep'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir ("{0}.log" -f (Get-Date -Format 'yyyy-MM-dd'))
$Fleet = if ($env:FLEET_DOCS) { $env:FLEET_DOCS } else { 'D:\repo\docs' }
$FleetKey = ($Fleet -replace '\\', '/').TrimEnd('/').ToLower() + '/'
Add-Content -Path $Log -Value ("=== {0} start ===" -f (Get-Date -Format 's')) -Encoding utf8
$out = & python (Join-Path $PSScriptRoot 'projects_sweep.py') --apply 2>&1 | Out-String
$rc = $LASTEXITCODE
Add-Content -Path $Log -Value $out -Encoding utf8
if ($rc -eq 0) {
  $report = $out | ConvertFrom-Json
  $paths = @($report.actions | ForEach-Object { $_.path; $_.dest } | Where-Object { $_ -and $_.ToLower().StartsWith($FleetKey) })
  if ($paths.Count -gt 0) {
    git -C $Fleet add -A -- $paths 2>&1 | ForEach-Object { Add-Content -Path $Log -Value $_ -Encoding utf8 }
    git -C $Fleet commit -q -m ("chore: weekly context sweep moved {0} fleet docs" -f $paths.Count) -- $paths 2>&1 |
      ForEach-Object { Add-Content -Path $Log -Value $_ -Encoding utf8 }
    git -C $Fleet push -q 2>&1 | ForEach-Object { Add-Content -Path $Log -Value $_ -Encoding utf8 }
  }
}
Add-Content -Path $Log -Value ("=== {0} exit {1} ===" -f (Get-Date -Format 's'), $rc) -Encoding utf8
exit $rc
