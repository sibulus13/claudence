# Registers \Claude\context-sweep (Sundays 06:00, hidden): the weekly context lifecycle cycle.
# Idempotent; -Unregister removes it. StartWhenAvailable catches a run missed while the PC slept.
param([switch]$Unregister)
$ErrorActionPreference = 'Stop'
$Folder = '\Claude\'; $Name = 'context-sweep'
if ($Unregister) { Unregister-ScheduledTask -TaskPath $Folder -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue; "removed $Folder$Name"; return }
$Wscript = Join-Path $env:WINDIR 'System32\wscript.exe'
$Hidden = Join-Path $PSScriptRoot 'run-hidden.vbs'
$Runner = Join-Path $PSScriptRoot 'context-sweep-scheduled.ps1'
$args = @('//B', '//Nologo', "`"$Hidden`"", '"powershell.exe"', '"-NoProfile"', '"-ExecutionPolicy"', '"Bypass"', '"-File"', "`"$Runner`"") -join ' '
$action = New-ScheduledTaskAction -Execute $Wscript -Argument $args -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At '06:00'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -Hidden -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskPath $Folder -TaskName $Name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
"registered $Folder$Name"
