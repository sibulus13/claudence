# tasks_inventory.ps1
# Read-only: prints the Windows scheduled tasks under -TaskPath (default: the user-level root) as a JSON array for tasks_audit.py.
# Registers, changes and runs nothing.
param([string]$TaskPath = '\')
$ErrorActionPreference = 'Stop'

function Format-Time($t) {
    if ($null -eq $t) { return $null }
    return ([datetime]$t).ToString('yyyy-MM-ddTHH:mm:sszzz')
}

$rows = @(foreach ($task in Get-ScheduledTask | Where-Object { $_.TaskPath -eq $TaskPath }) {
    $info = Get-ScheduledTaskInfo -TaskName $task.TaskName -TaskPath $task.TaskPath
    [pscustomobject]@{
        name         = $task.TaskName
        state        = "$($task.State)"
        lastRun      = Format-Time $info.LastRunTime
        lastResult   = [int64]$info.LastTaskResult
        nextRun      = Format-Time $info.NextRunTime
        triggerCount = @($task.Triggers).Count
    }
})
# ConvertTo-Json prints [null] for an empty array; an empty inventory must be [].
if ($rows.Count -eq 0) { '[]' } else { ConvertTo-Json -InputObject $rows -Compress }
