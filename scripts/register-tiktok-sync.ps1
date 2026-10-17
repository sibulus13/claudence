# Registers \Claude\tiktok-sync (daily 21:30, hidden). Idempotent; -Unregister removes it.
# Interactive logon on purpose: the run drives the owner's signed-in Chrome, which only exists
# while they are logged on. StartWhenAvailable catches a run missed while the PC slept.
param([switch]$Unregister)
$ErrorActionPreference = 'Stop'
$Folder = '\Claude\'; $Name = 'tiktok-sync'
if ($Unregister) { Unregister-ScheduledTask -TaskPath $Folder -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue; "removed $Folder$Name"; return }
$Wscript = Join-Path $env:WINDIR 'System32\wscript.exe'
$Hidden = Join-Path $PSScriptRoot 'run-hidden.vbs'
$Runner = Join-Path $PSScriptRoot 'tiktok-sync-scheduled.ps1'
$args = @('//B', '//Nologo', "`"$Hidden`"", '"powershell.exe"', '"-NoProfile"', '"-ExecutionPolicy"', '"Bypass"', '"-File"', "`"$Runner`"") -join ' '
$action = New-ScheduledTaskAction -Execute $Wscript -Argument $args
$trigger = New-ScheduledTaskTrigger -Daily -At '21:30'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -Hidden -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskPath $Folder -TaskName $Name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
"registered $Folder$Name"
