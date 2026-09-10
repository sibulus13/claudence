# Run the relative-hyperlink resolution UNIT tests using the WezTerm-bundled
# Lua — no separate Lua install needed. WezTerm executes a config file's
# top-level code on load, and pathlink.test.lua writes results to
# .last-results-pathlink.txt.
#
#   powershell.exe -NoProfile -File ~/.claude/tests/run-pathlink-tests.ps1
# Exit 0 = all pass, 1 = a test failed, 2 = the test file failed to load.
#
# (Separate from run-tests.ps1, which runs the Pester telemetry suite, and
# from run-attention-tests.ps1, which covers the unrelated notification logic.)
$ErrorActionPreference = 'Stop'

$wt   = 'C:\Program Files\WezTerm\wezterm.exe'
$test = Join-Path $env:USERPROFILE '.claude\tests\pathlink.test.lua'
$out  = Join-Path $env:USERPROFILE '.claude\tests\.last-results-pathlink.txt'

if (Test-Path $out) { Remove-Item $out -Force }
& $wt --config-file $test show-keys *> $null

if (-not (Test-Path $out)) {
  Write-Error 'No results written — the test file failed to load (Lua syntax/runtime error).'
  exit 2
}
Get-Content $out
if (Select-String -Path $out -Pattern '^FAIL' -Quiet) { exit 1 } else { exit 0 }
