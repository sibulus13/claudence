---
name: register-task
description: Register or change a Windows scheduled task the owner's way - hidden (no console flash) and smoke-tested through the real path. Use for any Register-ScheduledTask / schtasks work, daemons, or "run this every morning".
---

# /register-task

1. Copy `D:/repo/Assistant/cortex/scripts/run-hidden.vbs` into the repo's `scripts/` (Python may use `pythonw.exe` instead).
2. Action: `New-ScheduledTaskAction -Execute wscript.exe -Argument '//B //Nologo "<repo>\scripts\run-hidden.vbs" "<program>" <args>' -WorkingDirectory <repo>`; register with `-Settings (New-ScheduledTaskSettingsSet -Hidden ...)`. Never `powershell -WindowStyle Hidden` (it flashes). The guard hook denies a registration without the hidden launcher.
3. Paths come from the repo root (`$PSScriptRoot`), never typed absolute repo paths inside the scripts.
4. Smoke through the real path: `Start-ScheduledTask -TaskName <t>`, then require `(Get-ScheduledTaskInfo <t>).LastTaskResult -eq 0` and a non-empty log written by this run.
5. A task set to run whether logged on or not needs the owner's password to change: write a small script that prompts for it securely (`Read-Host -AsSecureString`) and hand it over; never ask for the password in chat.
6. Record the task in the repo's docs (name, schedule, what it runs, its log path).
