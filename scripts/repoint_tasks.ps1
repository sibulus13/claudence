# Rewrite scheduled-task actions after a move batch: every D:\repo\<from> becomes D:\repo\<to>.
#   powershell -NoProfile -File repoint_tasks.ps1 -Map <moves.json> [-DryRun]
# Triggers, settings and principal are untouched (Set-ScheduledTask -Action only).
param([Parameter(Mandatory)][string]$Map, [switch]$DryRun)
# PS 5.1's ConvertFrom-Json emits a JSON array as ONE pipeline object; unroll it before sorting/filtering.
$moves = (Get-Content $Map -Raw | ConvertFrom-Json) | ForEach-Object { $_ } | Sort-Object { - $_.from.Length }
function Repoint([string]$s) {
  if (-not $s) { return $s }
  foreach ($m in $moves) {
    $old = 'D:\repo\' + ($m.from -replace '/', '\')
    $new = 'D:\repo\' + ($m.to -replace '/', '\')
    $rx = [regex]::Escape($old) + '(?![A-Za-z0-9_\-])'
    $s = [regex]::Replace($s, $rx, $new.Replace('$', '$$'), 'IgnoreCase')
  }
  return $s
}
foreach ($t in Get-ScheduledTask) {
  $text = ($t.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments) $($_.WorkingDirectory)" }) -join ' '
  if ((Repoint $text) -eq $text) { continue }   # cheap pre-check; also skips COM-handler actions
  $changed = $false
  $acts = foreach ($a in $t.Actions) {
    $e = Repoint $a.Execute; $g = Repoint $a.Arguments; $w = Repoint $a.WorkingDirectory
    if ($e -ne [string]$a.Execute -or $g -ne [string]$a.Arguments -or $w -ne [string]$a.WorkingDirectory) { $changed = $true }
    $p = @{ Execute = $e }
    if ($g) { $p.Argument = $g }
    if ($w) { $p.WorkingDirectory = $w }
    New-ScheduledTaskAction @p
  }
  if (-not $changed) { continue }
  "{0}{1}" -f $t.TaskPath, $t.TaskName
  foreach ($a in $acts) { "    -> {0} {1} @{2}" -f $a.Execute, $a.Arguments, $a.WorkingDirectory }
  if (-not $DryRun) {
    try { Set-ScheduledTask -TaskName $t.TaskName -TaskPath $t.TaskPath -Action $acts -ErrorAction Stop | Out-Null; "    updated" }
    catch { "    FAILED: $($_.Exception.Message)" }
  }
}
