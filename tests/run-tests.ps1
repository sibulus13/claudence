# run-tests.ps1
# Runs the Pester test suite. Called by the pre-commit hook and runnable manually.
# Usage: powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/run-tests.ps1
# Exit code: 0 = all passed, 1 = failures or Pester unavailable

$ErrorActionPreference = 'Stop'

# Ensure user module path is in PSModulePath (missing when run from bash/non-login shell)
$userModules = [System.IO.Path]::Combine($env:USERPROFILE, 'Documents', 'WindowsPowerShell', 'Modules')
if ($env:PSModulePath -notlike "*$userModules*") {
    $env:PSModulePath = $userModules + ';' + $env:PSModulePath
}

# Ensure Pester 5+ is available
$pester = Get-Module -ListAvailable -Name Pester | Sort-Object Version -Descending | Select-Object -First 1
if (-not $pester -or $pester.Version.Major -lt 5) {
    Write-Host 'Pester 5+ not found — installing...' -ForegroundColor Yellow
    Install-Module Pester -Force -Scope CurrentUser -SkipPublisherCheck -MinimumVersion 5.0
}
Import-Module Pester -MinimumVersion 5.0 -Force

$config = New-PesterConfiguration
$config.Run.Path           = "$PSScriptRoot\classification.tests.ps1"
$config.Output.Verbosity   = 'Detailed'
$config.Run.PassThru       = $true
$config.TestResult.Enabled = $false

$result = Invoke-Pester -Configuration $config

Write-Host ''
$passed = $result.PassedCount
$failed = $result.FailedCount
if ($failed -gt 0) {
    Write-Host "FAILED  $failed test(s) failed, $passed passed." -ForegroundColor Red
    exit 1
} else {
    Write-Host "PASSED  $passed test(s) passed." -ForegroundColor Green
    exit 0
}
