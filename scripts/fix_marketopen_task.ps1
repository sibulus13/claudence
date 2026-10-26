# Repoint Crucible's MarketOpen_WakeAndStartServices task to Finance\crucible and launch it through
# run_hidden.vbs (no console flash). The task runs whether you are logged on or not, so Windows needs
# your account password to save it; it is read as a secure prompt and never written anywhere.
#   Admin PowerShell:  powershell -NoProfile -ExecutionPolicy Bypass -File $HOME\.claude\scripts\fix_marketopen_task.ps1
$ErrorActionPreference = "Stop"
$name = "MarketOpen_WakeAndStartServices"
$root = "D:\repo\Finance\crucible"
$t = Get-ScheduledTask -TaskName $name
$action = New-ScheduledTaskAction -Execute "wscript.exe" -WorkingDirectory $root `
    -Argument "//B //Nologo `"$root\scripts\run_hidden.vbs`" `"$root\scripts\market_wake_start.ps1`""
$secure = Read-Host -AsSecureString "Windows password for $($t.Principal.UserId)"
$plain = [Net.NetworkCredential]::new("", $secure).Password
Set-ScheduledTask -TaskName $name -Action $action -User $t.Principal.UserId -Password $plain | Out-Null
$plain = $null
$a = (Get-ScheduledTask -TaskName $name).Actions[0]
"Updated: $($a.Execute) $($a.Arguments) @$($a.WorkingDirectory)"
