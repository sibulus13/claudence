# system.tests.ps1
# Integration regression tests for the friction tracking system.
# Covers session staleness (statusline), session state reset (log-prompt),
# cumulative retrospect threshold (analyze-session), and skill file validity.
#
# Run via: tests/run-tests.ps1
# Or manually: Invoke-Pester tests/system.tests.ps1 -Output Detailed

BeforeAll {
    $script:ClaudeRoot  = "$HOME\.claude"
    $script:StateFile   = "$script:ClaudeRoot\telemetry\current-session.json"
    $script:CumFile     = "$script:ClaudeRoot\telemetry\cumulative.json"
    $script:SessionsDir = "$script:ClaudeRoot\telemetry\sessions"
    $script:ReportsDir  = "$script:ClaudeRoot\telemetry\reports"

    function script:Strip-Ansi([string]$s) { $s -replace '\x1b\[[0-9;]*[mGKHF]', '' }

    function script:Backup-File([string]$Path) {
        if (Test-Path $Path) { Copy-Item $Path "${Path}.testbak" -Force }
    }

    function script:Restore-File([string]$Path) {
        if (Test-Path "${Path}.testbak") {
            Move-Item "${Path}.testbak" $Path -Force
        } elseif (Test-Path $Path) {
            Remove-Item $Path -Force
        }
    }
}

# ---------------------------------------------------------------------------

Describe "Skill File: /retrospect" {

    It "skill file exists at skills/retrospect/SKILL.md" {
        Test-Path "$script:ClaudeRoot\skills\retrospect\SKILL.md" | Should -Be $true
    }

    It "skill file has YAML frontmatter with name and description fields" {
        $content = Get-Content "$script:ClaudeRoot\skills\retrospect\SKILL.md" -Raw
        $content | Should -Match '(?m)^---'
        $content | Should -Match '(?m)^name:\s+retrospect'
        $content | Should -Match '(?m)^description:'
    }

    It "skill file contains all required section headings" {
        $content = Get-Content "$script:ClaudeRoot\skills\retrospect\SKILL.md" -Raw
        $content | Should -Match 'Load friction reports'
        $content | Should -Match 'Identify patterns'
        $content | Should -Match 'Propose and apply changes'
        $content | Should -Match 'Archive addressed reports'
    }
}

# ---------------------------------------------------------------------------

Describe "Statusline: running spinner" {

    BeforeAll {
        $script:RunningFlag = "$script:ClaudeRoot\telemetry\running.flag"
    }
    BeforeEach {
        if (Test-Path $script:RunningFlag) { Remove-Item $script:RunningFlag -Force }
    }
    AfterEach {
        if (Test-Path $script:RunningFlag) { Remove-Item $script:RunningFlag -Force }
    }

    It "appends extra content when running.flag exists" {
        # Braille chars corrupt when captured through subprocess pipe encoding.
        # Instead verify the spinner adds length to the output (ANSI-stripped).
        $stdin = '{"session_id":"spin-test","context_window":{"used_percentage":5}}'

        Remove-Item $script:RunningFlag -Force -ErrorAction SilentlyContinue
        $without = script:Strip-Ansi (($stdin | powershell.exe -NoProfile -File "$script:ClaudeRoot\statusline.ps1") -join '')

        'running' | Set-Content $script:RunningFlag
        $with = script:Strip-Ansi (($stdin | powershell.exe -NoProfile -File "$script:ClaudeRoot\statusline.ps1") -join '')

        $with.Length | Should -BeGreaterThan $without.Length
    }

    It "shows no spinner when running.flag is absent" {
        # Flag is absent (removed in BeforeEach) — baseline length
        $stdin   = '{"session_id":"idle-test","context_window":{"used_percentage":5}}'
        $without = script:Strip-Ansi (($stdin | powershell.exe -NoProfile -File "$script:ClaudeRoot\statusline.ps1") -join '')
        # Add flag — output must grow
        'running' | Set-Content $script:RunningFlag
        $with = script:Strip-Ansi (($stdin | powershell.exe -NoProfile -File "$script:ClaudeRoot\statusline.ps1") -join '')
        $without.Length | Should -BeLessThan $with.Length
    }
}

# ---------------------------------------------------------------------------

Describe "Statusline: session staleness detection" {
    # CAVEAT: Claude Code runs the statusline command after each assistant response, NOT at
    # startup. This means there is a window between terminal restart and the first assistant
    # response where stale data from the previous session may still be visible. The fix
    # below is defence-in-depth (handles race conditions and future startup-invocation
    # scenarios) but does not eliminate the startup gap. The existing log-prompt.ps1
    # session reset is what corrects the state before the statusline next fires.
    #

    BeforeEach { script:Backup-File $script:StateFile }
    AfterEach  { script:Restore-File $script:StateFile }

    It "shows '0 Prompts' when stdin session_id differs from current-session.json" {
        # Seed stale state from a previous session
        [PSCustomObject]@{
            session_id   = 'old-session-aaa'
            prompts      = 7
            overrides    = 3
            additions    = 2
            perm_reqs    = 1
            perm_repeats = 0
            started_at   = (Get-Date).AddHours(-2).ToString('o')
        } | ConvertTo-Json | Set-Content $script:StateFile

        $stdin = '{"session_id":"new-session-bbb","context_window":{"used_percentage":2},"cost":{"total_cost_usd":0.00}}'
        $raw   = $stdin | powershell.exe -NoProfile -File "$script:ClaudeRoot\statusline.ps1"
        $out   = script:Strip-Ansi ($raw -join '')

        $out | Should -Match '0 Prompts'
        $out | Should -Not -Match '7 Prompts'
    }

    It "shows '0 Prompts' when current-session.json does not exist" {
        if (Test-Path $script:StateFile) { Remove-Item $script:StateFile -Force }

        $stdin = '{"session_id":"brand-new","context_window":{"used_percentage":1}}'
        $raw   = $stdin | powershell.exe -NoProfile -File "$script:ClaudeRoot\statusline.ps1"
        $out   = script:Strip-Ansi ($raw -join '')

        $out | Should -Match '0 Prompts'
    }

    It "shows actual counts when session_id matches current-session.json" {
        $sid = 'matching-session-xyz'
        [PSCustomObject]@{
            session_id      = $sid
            prompts         = 4
            overrides       = 1
            additions       = 0
            denial_contexts = 0
            perm_reqs       = 0
            perm_repeats    = 0
            started_at      = (Get-Date).AddMinutes(-15).ToString('o')
        } | ConvertTo-Json | Set-Content $script:StateFile

        $stdin = "{`"session_id`":`"$sid`",`"context_window`":{`"used_percentage`":10},`"cost`":{`"total_cost_usd`":0.03}}"
        $raw   = $stdin | powershell.exe -NoProfile -File "$script:ClaudeRoot\statusline.ps1"
        $out   = script:Strip-Ansi ($raw -join '')

        $out | Should -Match '4 Prompts'
    }

    It "does NOT discard state when stdin has no session_id (graceful degradation)" {
        # If Claude Code doesn't send session_id in statusline stdin, the fix must be inert
        # and existing stored data must still be shown.
        [PSCustomObject]@{
            session_id   = 'any-session'
            prompts      = 3
            overrides    = 0
            additions    = 0
            perm_reqs    = 0
            perm_repeats = 0
            started_at   = (Get-Date).AddMinutes(-5).ToString('o')
        } | ConvertTo-Json | Set-Content $script:StateFile

        $stdin = '{"context_window":{"used_percentage":5}}'
        $raw   = $stdin | powershell.exe -NoProfile -File "$script:ClaudeRoot\statusline.ps1"
        $out   = script:Strip-Ansi ($raw -join '')

        # Without session_id in stdin the staleness check is skipped — show as-is
        $out | Should -Match '3 Prompts'
    }
}

# ---------------------------------------------------------------------------

Describe "log-prompt.ps1: session state reset on new session_id" {

    BeforeEach { script:Backup-File $script:StateFile }
    AfterEach  { script:Restore-File $script:StateFile }

    It "resets counts to 1/0/0 when session_id in hook input differs from stored state" {
        $newSid = 'reset-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8)

        # Pre-seed state from a different session
        [PSCustomObject]@{
            session_id   = 'previous-session'
            prompts      = 50
            overrides    = 5
            additions    = 3
            perm_reqs    = 2
            perm_repeats = 1
            started_at   = (Get-Date).AddHours(-3).ToString('o')
        } | ConvertTo-Json | Set-Content $script:StateFile

        $hookInput = [PSCustomObject]@{
            session_id = $newSid
            prompt     = 'Starting fresh'
        } | ConvertTo-Json -Compress
        $hookInput | powershell.exe -NoProfile -File "$script:ClaudeRoot\telemetry\log-prompt.ps1" | Out-Null

        $s = Get-Content $script:StateFile -Raw | ConvertFrom-Json
        $s.session_id | Should -Be $newSid
        $s.prompts    | Should -Be 1
        $s.overrides  | Should -Be 0
        $s.additions  | Should -Be 0
        $s.perm_reqs  | Should -Be 0

        # Cleanup session JSONL written by the hook
        $f = Join-Path $script:SessionsDir "$newSid.jsonl"
        if (Test-Path $f) { Remove-Item $f -Force }
    }

    It "increments prompt count when session_id matches stored state" {
        $sid = 'continuing-' + [guid]::NewGuid().ToString('N').Substring(0, 8)

        [PSCustomObject]@{
            session_id   = $sid
            prompts      = 2
            overrides    = 0
            additions    = 0
            perm_reqs    = 0
            perm_repeats = 0
            started_at   = (Get-Date).AddMinutes(-5).ToString('o')
        } | ConvertTo-Json | Set-Content $script:StateFile

        # Seed session JSONL so classification has a prior stop to work with
        $sessionFile = Join-Path $script:SessionsDir "$sid.jsonl"
        @(
            [PSCustomObject]@{ ts = (Get-Date).AddMinutes(-3).ToString('o'); session_id = $sid; event = 'prompt'; classification = 'first_prompt'; prompt_chars = 10; prompt_text = 'hi'; cwd = 'C:\test' }
            [PSCustomObject]@{ ts = (Get-Date).AddMinutes(-2).ToString('o'); session_id = $sid; event = 'stop' }
        ) | ForEach-Object { $_ | ConvertTo-Json -Compress } | Set-Content $sessionFile

        $hookInput = [PSCustomObject]@{ session_id = $sid; prompt = 'Keep going' } | ConvertTo-Json -Compress
        $hookInput | powershell.exe -NoProfile -File "$script:ClaudeRoot\telemetry\log-prompt.ps1" | Out-Null

        $s = Get-Content $script:StateFile -Raw | ConvertFrom-Json
        $s.session_id | Should -Be $sid
        $s.prompts    | Should -Be 3   # was 2, incremented to 3

        if (Test-Path $sessionFile) { Remove-Item $sessionFile -Force }
    }
}

# ---------------------------------------------------------------------------

Describe "analyze-session.ps1: cumulative reset after retrospect threshold" {

    BeforeEach { script:Backup-File $script:CumFile }
    AfterEach  { script:Restore-File $script:CumFile }

    It "resets cumulative counters and emits systemMessage when threshold is met" {
        # Threshold: sessions_since_review >= 3 AND total_score >= 6
        [PSCustomObject]@{
            total_score           = 8
            sessions_since_review = 3
            last_review_ts        = ''
        } | ConvertTo-Json | Set-Content $script:CumFile

        $sid   = 'retro-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
        $sFile = Join-Path $script:SessionsDir "$sid.jsonl"
        @(
            [PSCustomObject]@{ ts = (Get-Date).AddMinutes(-5).ToString('o'); session_id = $sid; event = 'prompt'; classification = 'override'; prompt_chars = 20; prompt_text = 'redo it'; cwd = 'C:\test' }
            [PSCustomObject]@{ ts = (Get-Date).AddMinutes(-1).ToString('o'); session_id = $sid; event = 'stop' }
        ) | ForEach-Object { $_ | ConvertTo-Json -Compress } | Set-Content $sFile

        $hookInput = [PSCustomObject]@{ session_id = $sid } | ConvertTo-Json -Compress
        $raw = $hookInput | powershell.exe -NoProfile -File "$script:ClaudeRoot\telemetry\analyze-session.ps1" 2>$null
        $out = $raw -join ''

        $out | Should -Match 'systemMessage'
        $out | Should -Match 'retrospect'

        $cum = Get-Content $script:CumFile -Raw | ConvertFrom-Json
        $cum.sessions_since_review | Should -Be 0
        $cum.total_score           | Should -Be 0
        $cum.last_review_ts        | Should -Not -BeNullOrEmpty

        if (Test-Path $sFile) { Remove-Item $sFile -Force }
        $rFile = Join-Path $script:ReportsDir "$($sid.Substring(0,8)).json"
        if (Test-Path $rFile) { Remove-Item $rFile -Force }
    }

    It "does NOT reset cumulative counters when threshold is not met" {
        [PSCustomObject]@{
            total_score           = 2
            sessions_since_review = 1
            last_review_ts        = ''
        } | ConvertTo-Json | Set-Content $script:CumFile

        $sid   = 'no-retro-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
        $sFile = Join-Path $script:SessionsDir "$sid.jsonl"
        @(
            [PSCustomObject]@{ ts = (Get-Date).AddMinutes(-3).ToString('o'); session_id = $sid; event = 'prompt'; classification = 'followup'; prompt_chars = 10; prompt_text = 'continue'; cwd = 'C:\test' }
            [PSCustomObject]@{ ts = (Get-Date).AddMinutes(-1).ToString('o'); session_id = $sid; event = 'stop' }
        ) | ForEach-Object { $_ | ConvertTo-Json -Compress } | Set-Content $sFile

        $hookInput = [PSCustomObject]@{ session_id = $sid } | ConvertTo-Json -Compress
        $hookInput | powershell.exe -NoProfile -File "$script:ClaudeRoot\telemetry\analyze-session.ps1" 2>$null | Out-Null

        $cum = Get-Content $script:CumFile -Raw | ConvertFrom-Json
        # Threshold not met — last_review_ts must still be empty (not reset)
        $cum.last_review_ts | Should -BeNullOrEmpty

        if (Test-Path $sFile) { Remove-Item $sFile -Force }
        $rFile = Join-Path $script:ReportsDir "$($sid.Substring(0,8)).json"
        if (Test-Path $rFile) { Remove-Item $rFile -Force }
    }
}

# ---------------------------------------------------------------------------

Describe "analyze-session.ps1: permission approve vs deny scoring" {

    BeforeEach { script:Backup-File $script:CumFile }
    AfterEach  { script:Restore-File $script:CumFile }

    It "approved perm_req scores 0 friction and adds allow_suggestion" {
        [PSCustomObject]@{ total_score = 0; sessions_since_review = 0; last_review_ts = '' } |
            ConvertTo-Json | Set-Content $script:CumFile

        $sid   = 'perm-approved-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
        $sFile = Join-Path $script:SessionsDir "$sid.jsonl"
        $t0    = (Get-Date).AddMinutes(-5).ToString('o')
        $t1    = (Get-Date).AddMinutes(-4).ToString('o')  # tool_done after perm_req → approved
        $t2    = (Get-Date).AddMinutes(-1).ToString('o')
        @(
            [PSCustomObject]@{ ts = $t0; session_id = $sid; event = 'prompt';       classification = 'first_prompt'; prompt_chars = 10; prompt_text = 'go'; cwd = 'C:\test' }
            [PSCustomObject]@{ ts = $t0; session_id = $sid; event = 'permission_req'; tool = 'Bash'; input_preview = 'git status' }
            [PSCustomObject]@{ ts = $t1; session_id = $sid; event = 'tool_done';     tool = 'Bash'; input_preview = 'git status' }
            [PSCustomObject]@{ ts = $t2; session_id = $sid; event = 'stop' }
        ) | ForEach-Object { $_ | ConvertTo-Json -Compress } | Set-Content $sFile

        $hookInput = [PSCustomObject]@{ session_id = $sid } | ConvertTo-Json -Compress
        $hookInput | powershell.exe -NoProfile -File "$script:ClaudeRoot\telemetry\analyze-session.ps1" 2>$null | Out-Null

        $rFile  = Join-Path $script:ReportsDir "$($sid.Substring(0,8)).json"
        $report = Get-Content $rFile -Raw | ConvertFrom-Json
        $report.score             | Should -Be 0
        $report.allow_suggestions | Should -Contain 'Bash(git:*)'

        if (Test-Path $sFile)  { Remove-Item $sFile  -Force }
        if (Test-Path $rFile)  { Remove-Item $rFile  -Force }
    }

    It "denied perm_req scores 1 friction and adds no allow_suggestion" {
        [PSCustomObject]@{ total_score = 0; sessions_since_review = 0; last_review_ts = '' } |
            ConvertTo-Json | Set-Content $script:CumFile

        $sid   = 'perm-denied-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
        $sFile = Join-Path $script:SessionsDir "$sid.jsonl"
        $t0    = (Get-Date).AddMinutes(-5).ToString('o')
        $t2    = (Get-Date).AddMinutes(-1).ToString('o')
        @(
            [PSCustomObject]@{ ts = $t0; session_id = $sid; event = 'prompt';       classification = 'first_prompt'; prompt_chars = 10; prompt_text = 'go'; cwd = 'C:\test' }
            [PSCustomObject]@{ ts = $t0; session_id = $sid; event = 'permission_req'; tool = 'Bash'; input_preview = 'rm -rf temp' }
            # No tool_done for Bash → denied
            [PSCustomObject]@{ ts = $t2; session_id = $sid; event = 'stop' }
        ) | ForEach-Object { $_ | ConvertTo-Json -Compress } | Set-Content $sFile

        $hookInput = [PSCustomObject]@{ session_id = $sid } | ConvertTo-Json -Compress
        $hookInput | powershell.exe -NoProfile -File "$script:ClaudeRoot\telemetry\analyze-session.ps1" 2>$null | Out-Null

        $rFile  = Join-Path $script:ReportsDir "$($sid.Substring(0,8)).json"
        $report = Get-Content $rFile -Raw | ConvertFrom-Json
        $report.score             | Should -Be 1
        $report.allow_suggestions | Should -BeNullOrEmpty

        if (Test-Path $sFile)  { Remove-Item $sFile  -Force }
        if (Test-Path $rFile)  { Remove-Item $rFile  -Force }
    }
}
