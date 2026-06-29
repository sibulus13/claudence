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
    # Spinner now reads a PER-SESSION flag (running-<session_id>.flag), so the flag
    # name must match the session_id sent on stdin.
    AfterEach {
        Get-ChildItem "$script:ClaudeRoot\telemetry\running-spin-test.flag", `
                      "$script:ClaudeRoot\telemetry\running-idle-test.flag" -ErrorAction SilentlyContinue |
            Remove-Item -Force -ErrorAction SilentlyContinue
    }

    It "appends extra content when running-<session>.flag exists" {
        # Braille chars corrupt when captured through subprocess pipe encoding.
        # Instead verify the spinner adds length to the output (ANSI-stripped).
        $sid   = 'spin-test'
        $flag  = "$script:ClaudeRoot\telemetry\running-$sid.flag"
        $stdin = "{`"session_id`":`"$sid`",`"context_window`":{`"used_percentage`":5}}"

        Remove-Item $flag -Force -ErrorAction SilentlyContinue
        $without = script:Strip-Ansi (($stdin | powershell.exe -NoProfile -File "$script:ClaudeRoot\statusline.ps1") -join '')

        'running' | Set-Content $flag
        $with = script:Strip-Ansi (($stdin | powershell.exe -NoProfile -File "$script:ClaudeRoot\statusline.ps1") -join '')

        Remove-Item $flag -Force -ErrorAction SilentlyContinue
        $with.Length | Should -BeGreaterThan $without.Length
    }

    It "shows no spinner when the per-session flag is absent" {
        $sid   = 'idle-test'
        $flag  = "$script:ClaudeRoot\telemetry\running-$sid.flag"
        $stdin = "{`"session_id`":`"$sid`",`"context_window`":{`"used_percentage`":5}}"

        Remove-Item $flag -Force -ErrorAction SilentlyContinue
        $without = script:Strip-Ansi (($stdin | powershell.exe -NoProfile -File "$script:ClaudeRoot\statusline.ps1") -join '')
        # Add flag — output must grow
        'running' | Set-Content $flag
        $with = script:Strip-Ansi (($stdin | powershell.exe -NoProfile -File "$script:ClaudeRoot\statusline.ps1") -join '')

        Remove-Item $flag -Force -ErrorAction SilentlyContinue
        $without.Length | Should -BeLessThan $with.Length
    }
}

# ---------------------------------------------------------------------------

Describe "Statusline: per-session prompt count" {
    # Staleness is now STRUCTURAL: statusline reads telemetry/state-<session_id>.json,
    # so a different session has no file to read (no count shown) and a matching session
    # reads its own file. The old shared current-session.json + staleness check is gone.

    AfterEach {
        Get-ChildItem "$script:ClaudeRoot\telemetry\state-old-session-aaa.json", `
                      "$script:ClaudeRoot\telemetry\state-brand-new.json", `
                      "$script:ClaudeRoot\telemetry\state-matching-session-xyz.json" -ErrorAction SilentlyContinue |
            Remove-Item -Force -ErrorAction SilentlyContinue
    }

    It "does not show a stale count from a different session" {
        # State exists for an OLD session; statusline is invoked for a DIFFERENT session,
        # which has no state file of its own → it must not surface the old count.
        $old = 'old-session-aaa'
        [PSCustomObject]@{
            session_id = $old; prompts = 7; overrides = 3; additions = 2
            started_at = (Get-Date).AddHours(-2).ToString('o')
        } | ConvertTo-Json | Set-Content "$script:ClaudeRoot\telemetry\state-$old.json"

        $stdin = '{"session_id":"new-session-bbb","context_window":{"used_percentage":2},"cost":{"total_cost_usd":0.00}}'
        $out   = script:Strip-Ansi (($stdin | powershell.exe -NoProfile -File "$script:ClaudeRoot\statusline.ps1") -join '')

        $out | Should -Not -Match '7 Prompts'
        $out | Should -Not -Match '\d+ Prompts'
    }

    It "shows no prompt count when no state file exists for the session" {
        $sid = 'brand-new'
        Remove-Item "$script:ClaudeRoot\telemetry\state-$sid.json" -Force -ErrorAction SilentlyContinue

        $stdin = '{"session_id":"brand-new","context_window":{"used_percentage":1}}'
        $out   = script:Strip-Ansi (($stdin | powershell.exe -NoProfile -File "$script:ClaudeRoot\statusline.ps1") -join '')

        $out | Should -Not -Match '\d+ Prompts'
    }

    It "shows actual counts when a state file exists for the session" {
        $sid = 'matching-session-xyz'
        [PSCustomObject]@{
            session_id      = $sid; prompts = 4; overrides = 1; additions = 0; denial_contexts = 0
            started_at      = (Get-Date).AddMinutes(-15).ToString('o')
        } | ConvertTo-Json | Set-Content "$script:ClaudeRoot\telemetry\state-$sid.json"

        $stdin = "{`"session_id`":`"$sid`",`"context_window`":{`"used_percentage`":10},`"cost`":{`"total_cost_usd`":0.03}}"
        $out   = script:Strip-Ansi (($stdin | powershell.exe -NoProfile -File "$script:ClaudeRoot\statusline.ps1") -join '')

        $out | Should -Match '4 Prompts'
    }

    It "renders without a prompt count when stdin has no session_id" {
        # All state is keyed on session_id; without one there is no file to read, so it
        # degrades to ctx-only rather than showing a misleading count. Must not crash.
        $stdin = '{"context_window":{"used_percentage":5}}'
        $out   = script:Strip-Ansi (($stdin | powershell.exe -NoProfile -File "$script:ClaudeRoot\statusline.ps1") -join '')

        $out | Should -Match 'ctx 5%'
        $out | Should -Not -Match '\d+ Prompts'
    }
}

# ---------------------------------------------------------------------------

Describe "log-prompt.ps1: per-session state file" {
    # Each session has its own telemetry/state-<session_id>.json. A brand-new session
    # therefore starts at 1/0/0 in its OWN file (no shared file to "reset"); an existing
    # session's file is incremented in place.

    It "creates a fresh state-<sid>.json with counts 1/0/0 for a new session" {
        $newSid    = 'reset-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
        $stateFile = "$script:ClaudeRoot\telemetry\state-$newSid.json"
        Remove-Item $stateFile -Force -ErrorAction SilentlyContinue

        $hookInput = [PSCustomObject]@{
            session_id = $newSid
            prompt     = 'Starting fresh'
        } | ConvertTo-Json -Compress
        $hookInput | powershell.exe -NoProfile -File "$script:ClaudeRoot\telemetry\log-prompt.ps1" | Out-Null

        $s = Get-Content $stateFile -Raw | ConvertFrom-Json
        $s.session_id | Should -Be $newSid
        $s.prompts    | Should -Be 1
        $s.overrides  | Should -Be 0
        $s.additions  | Should -Be 0
        $s.perm_reqs  | Should -Be 0

        Remove-Item $stateFile -Force -ErrorAction SilentlyContinue
        Remove-Item "$script:ClaudeRoot\telemetry\running-$newSid.flag" -Force -ErrorAction SilentlyContinue
        $f = Join-Path $script:SessionsDir "$newSid.jsonl"
        if (Test-Path $f) { Remove-Item $f -Force }
    }

    It "increments prompt count when the session's state file already exists" {
        $sid       = 'continuing-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
        $stateFile = "$script:ClaudeRoot\telemetry\state-$sid.json"

        [PSCustomObject]@{
            session_id   = $sid
            prompts      = 2
            overrides    = 0
            additions    = 0
            perm_reqs    = 0
            perm_repeats = 0
            started_at   = (Get-Date).AddMinutes(-5).ToString('o')
        } | ConvertTo-Json | Set-Content $stateFile

        # Seed session JSONL so classification has a prior stop to work with
        $sessionFile = Join-Path $script:SessionsDir "$sid.jsonl"
        @(
            [PSCustomObject]@{ ts = (Get-Date).AddMinutes(-3).ToString('o'); session_id = $sid; event = 'prompt'; classification = 'first_prompt'; prompt_chars = 10; prompt_text = 'hi'; cwd = 'C:\test' }
            [PSCustomObject]@{ ts = (Get-Date).AddMinutes(-2).ToString('o'); session_id = $sid; event = 'stop' }
        ) | ForEach-Object { $_ | ConvertTo-Json -Compress } | Set-Content $sessionFile

        $hookInput = [PSCustomObject]@{ session_id = $sid; prompt = 'Keep going' } | ConvertTo-Json -Compress
        $hookInput | powershell.exe -NoProfile -File "$script:ClaudeRoot\telemetry\log-prompt.ps1" | Out-Null

        $s = Get-Content $stateFile -Raw | ConvertFrom-Json
        $s.session_id | Should -Be $sid
        $s.prompts    | Should -Be 3   # was 2, incremented to 3

        Remove-Item $stateFile -Force -ErrorAction SilentlyContinue
        Remove-Item "$script:ClaudeRoot\telemetry\running-$sid.flag" -Force -ErrorAction SilentlyContinue
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
