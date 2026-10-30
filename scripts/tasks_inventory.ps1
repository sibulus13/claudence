# tasks_inventory.ps1
# Read-only: prints the user-level Windows scheduled tasks (TaskPath "\") as a JSON array for tasks_audit.py.
# Registers, changes and runs nothing.
$ErrorActionPreference = 'Stop'

function Format-Time($t) {
    if ($null -eq $t) { return $null }
    return ([datetime]$t).ToString('yyyy-MM-ddTHH:mm:sszzz')
}

$rows = foreach ($task in Get-ScheduledTask | Where-Object { $_.TaskPath -eq '\' }) {
    $info = Get-ScheduledTaskInfo -TaskName $task.TaskName -TaskPath $task.TaskPath
    [pscustomobject]@{
        name         = $task.TaskName
        state        = "$($task.State)"
        lastRun      = Format-Time $info.LastRunTime
        lastResult   = [int64]$info.LastTaskResult
        nextRun      = Format-Time $info.NextRunTime
        triggerCount = @($task.Triggers).Count
    }
}
ConvertTo-Json -InputObject @($rows) -Compress
