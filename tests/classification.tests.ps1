# classification.tests.ps1
# Pester 5 test suite for the prompt classification library.
# Run via: tests/run-tests.ps1
# Or manually: Invoke-Pester tests/classification.tests.ps1 -Output Detailed

BeforeAll {
    . "$PSScriptRoot\..\telemetry\lib\classification.ps1"
}

Describe "Get-IsDenialContext" {

    Context "No prior events" {
        It "returns false with null events" {
            Get-IsDenialContext $null | Should -Be $false
        }
        It "returns false with empty array" {
            Get-IsDenialContext @() | Should -Be $false
        }
    }

    Context "Unmatched perm_req (tool was denied)" {
        It "returns true when perm_req has no subsequent tool_done for that tool" {
            $events = @(
                [PSCustomObject]@{ ts = '2026-01-01T10:00:00Z'; event = 'prompt';       classification = 'first_prompt' }
                [PSCustomObject]@{ ts = '2026-01-01T10:00:05Z'; event = 'permission_req'; tool = 'Bash' }
                # No tool_done for Bash — was denied
            )
            Get-IsDenialContext $events | Should -Be $true
        }

        It "returns true for perm_req_repeat with no subsequent tool_done" {
            $events = @(
                [PSCustomObject]@{ ts = '2026-01-01T10:00:00Z'; event = 'prompt';           classification = 'first_prompt' }
                [PSCustomObject]@{ ts = '2026-01-01T10:00:05Z'; event = 'perm_req_repeat';  tool = 'Bash' }
            )
            Get-IsDenialContext $events | Should -Be $true
        }
    }

    Context "Matched perm_req (tool was approved)" {
        It "returns false when perm_req is followed by tool_done for the same tool" {
            $events = @(
                [PSCustomObject]@{ ts = '2026-01-01T10:00:00Z'; event = 'prompt';       classification = 'first_prompt' }
                [PSCustomObject]@{ ts = '2026-01-01T10:00:05Z'; event = 'permission_req'; tool = 'Bash' }
                [PSCustomObject]@{ ts = '2026-01-01T10:00:10Z'; event = 'tool_done';      tool = 'Bash' }
            )
            Get-IsDenialContext $events | Should -Be $false
        }

        It "returns false when tool_done for a different tool does not satisfy the perm_req" {
            $events = @(
                [PSCustomObject]@{ ts = '2026-01-01T10:00:00Z'; event = 'prompt';       classification = 'first_prompt' }
                [PSCustomObject]@{ ts = '2026-01-01T10:00:05Z'; event = 'permission_req'; tool = 'Bash' }
                [PSCustomObject]@{ ts = '2026-01-01T10:00:10Z'; event = 'tool_done';      tool = 'Read' }  # different tool
            )
            Get-IsDenialContext $events | Should -Be $true
        }
    }

    Context "Scoped to current turn only" {
        It "ignores unmatched perm_req from a previous turn" {
            $events = @(
                # Turn 1: perm_req denied (old turn)
                [PSCustomObject]@{ ts = '2026-01-01T09:00:00Z'; event = 'prompt';       classification = 'first_prompt' }
                [PSCustomObject]@{ ts = '2026-01-01T09:00:05Z'; event = 'permission_req'; tool = 'Bash' }
                # Turn 1 stop + Turn 2 prompt — new turn begins
                [PSCustomObject]@{ ts = '2026-01-01T09:01:00Z'; event = 'stop' }
                [PSCustomObject]@{ ts = '2026-01-01T09:02:00Z'; event = 'prompt';       classification = 'followup' }
                # No perm_req in turn 2
            )
            Get-IsDenialContext $events | Should -Be $false
        }
    }
}

Describe "Test-IsOverride" {

    Context "Start-anchored override signals" {
        It "detects 'Actually' at start" {
            Test-IsOverride "Actually, let's try a different approach" | Should -Be $true
        }
        It "detects 'No,' at start" {
            Test-IsOverride "No, I meant the first implementation" | Should -Be $true
        }
        It "detects 'No!' at start" {
            Test-IsOverride "No! That's wrong, redo it" | Should -Be $true
        }
        It "detects 'Wait,' at start" {
            Test-IsOverride "Wait, that's not what I wanted" | Should -Be $true
        }
        It "detects 'Stop' at start" {
            Test-IsOverride "Stop, let's reconsider" | Should -Be $true
        }
        It "detects 'Undo' at start" {
            Test-IsOverride "Undo the last change" | Should -Be $true
        }
        It "is case-insensitive for start patterns" {
            Test-IsOverride "ACTUALLY let's do this differently" | Should -Be $true
        }
    }

    Context "Anywhere override signals" {
        It "detects 'forget that'" {
            Test-IsOverride "Forget that, let's start fresh" | Should -Be $true
        }
        It "detects 'forget this'" {
            Test-IsOverride "Forget this approach entirely" | Should -Be $true
        }
        It "detects 'instead'" {
            Test-IsOverride "Let's do it a different way instead" | Should -Be $true
        }
        It "detects 'scratch that'" {
            Test-IsOverride "Scratch that, use a simpler approach" | Should -Be $true
        }
        It "detects 'start over'" {
            Test-IsOverride "Start over with a cleaner design" | Should -Be $true
        }
        It "detects 'never mind'" {
            Test-IsOverride "Never mind, keep the original" | Should -Be $true
        }
        It "detects 'cancel that'" {
            Test-IsOverride "Cancel that last change please" | Should -Be $true
        }
        It "detects 'ignore that'" {
            Test-IsOverride "Ignore that, I found the issue" | Should -Be $true
        }
        It "detects 'disregard'" {
            Test-IsOverride "Disregard the previous instruction" | Should -Be $true
        }
    }

    Context "Non-override prompts" {
        It "does not flag clean followup" {
            Test-IsOverride "Let's implement the goals screen next" | Should -Be $false
        }
        It "does not flag additive prompt" {
            Test-IsOverride "Also add error handling to the function" | Should -Be $false
        }
        It "does not flag 'actually' mid-sentence" {
            Test-IsOverride "Can you actually also fix the linting errors?" | Should -Be $false
        }
        It "does not flag 'no' mid-sentence" {
            Test-IsOverride "There's no issue with that approach" | Should -Be $false
        }
        It "does not flag questions" {
            Test-IsOverride "What does this function return?" | Should -Be $false
        }
        It "does not flag long deliberate followup" {
            Test-IsOverride "Now that we have the API working, let's move on to the UI layer and implement the goals screen with the same pattern we used for budgets." | Should -Be $false
        }
        It "handles empty string" {
            Test-IsOverride "" | Should -Be $false
        }
        It "handles whitespace only" {
            Test-IsOverride "   " | Should -Be $false
        }
        It "handles null" {
            Test-IsOverride $null | Should -Be $false
        }
    }
}

Describe "Test-IsAddition" {

    Context "Additive language patterns" {
        It "detects 'also'" {
            Test-IsAddition "Also add error handling" | Should -Be $true
        }
        It "detects 'additionally'" {
            Test-IsAddition "Additionally, we need null checks throughout" | Should -Be $true
        }
        It "detects 'note that'" {
            Test-IsAddition "Note that we're running on Windows not Linux" | Should -Be $true
        }
        It "detects 'don't forget'" {
            Test-IsAddition "Don't forget to add the import statement at the top" | Should -Be $true
        }
        It "detects 'by the way'" {
            Test-IsAddition "By the way, the API key is already in .env" | Should -Be $true
        }
        It "detects 'oh and'" {
            Test-IsAddition "Oh and make it async too while you're at it" | Should -Be $true
        }
        It "detects 'one more thing'" {
            Test-IsAddition "One more thing - it also needs to handle the empty array case" | Should -Be $true
        }
        It "detects 'forgot to mention'" {
            Test-IsAddition "I forgot to mention it needs to validate the input first" | Should -Be $true
        }
        It "detects 'furthermore'" {
            Test-IsAddition "Furthermore, it should validate on the server side too" | Should -Be $true
        }
        It "detects 'separately'" {
            Test-IsAddition "Separately, we also need to update the types" | Should -Be $true
        }
        It "detects 'while you're at it'" {
            Test-IsAddition "While you're at it, fix the formatting too" | Should -Be $true
        }
        It "is case-insensitive" {
            Test-IsAddition "ALSO make sure to run the tests" | Should -Be $true
        }
    }

    Context "Non-additive prompts" {
        It "does not flag clean followup" {
            Test-IsAddition "Let's implement the goals screen next" | Should -Be $false
        }
        It "does not flag a question" {
            Test-IsAddition "What does this function return?" | Should -Be $false
        }
        It "does not flag override language" {
            Test-IsAddition "Actually, let's do this differently" | Should -Be $false
        }
        It "does not flag long neutral followup" {
            Test-IsAddition "Now let's move on to the settings screen and implement the connected accounts feature using the same hook pattern." | Should -Be $false
        }
        It "handles empty string" {
            Test-IsAddition "" | Should -Be $false
        }
        It "handles null" {
            Test-IsAddition $null | Should -Be $false
        }
    }
}

Describe "Get-PromptClassification" {

    Context "No prior events" {
        It "returns first_prompt with empty array" {
            Get-PromptClassification "Let's start building" @() | Should -Be 'first_prompt'
        }
        It "returns first_prompt with null" {
            Get-PromptClassification "Hello" $null | Should -Be 'first_prompt'
        }
        It "returns first_prompt regardless of override language when no history" {
            Get-PromptClassification "Actually forget that" @() | Should -Be 'first_prompt'
        }
    }

    Context "Mid-run detection (no stop after last prompt)" {
        BeforeAll {
            # Last event is a prompt with no subsequent stop — Claude is still running
            $script:midRunEvents = @(
                [PSCustomObject]@{ event = 'stop';     ts = '2026-01-01T09:00:00Z' },
                [PSCustomObject]@{ event = 'prompt';   ts = '2026-01-01T10:00:00Z' },
                [PSCustomObject]@{ event = 'tool_done'; ts = '2026-01-01T10:00:05Z' }
            )
        }
        It "returns addition for neutral text while mid-run" {
            Get-PromptClassification "Keep going on the same task" $script:midRunEvents | Should -Be 'addition'
        }
        It "returns addition even for override language while mid-run" {
            Get-PromptClassification "Actually stop and do X instead" $script:midRunEvents | Should -Be 'addition'
        }
        It "returns addition for additive language while mid-run" {
            Get-PromptClassification "Also make sure to handle the error case" $script:midRunEvents | Should -Be 'addition'
        }
    }

    Context "Post-stop classification" {
        BeforeAll {
            # Stop is more recent than last prompt
            $script:stoppedEvents = @(
                [PSCustomObject]@{ event = 'prompt'; ts = '2026-01-01T10:00:00Z' },
                [PSCustomObject]@{ event = 'stop';   ts = '2026-01-01T10:01:00Z' }
            )
        }
        It "returns override for override language post-stop" {
            Get-PromptClassification "Actually, let's scrap this and do it differently" $script:stoppedEvents | Should -Be 'override'
        }
        It "returns override for 'instead' post-stop" {
            Get-PromptClassification "Let's use a different pattern instead" $script:stoppedEvents | Should -Be 'override'
        }
        It "returns followup for additive language post-stop (additive language no longer scores as addition)" {
            Get-PromptClassification "Also add error handling to that function" $script:stoppedEvents | Should -Be 'followup'
        }
        It "returns followup for 'note that' post-stop" {
            Get-PromptClassification "Note that we're on Windows so use backslashes" $script:stoppedEvents | Should -Be 'followup'
        }
        It "returns followup for neutral text post-stop" {
            Get-PromptClassification "Let's implement the settings screen next" $script:stoppedEvents | Should -Be 'followup'
        }
        It "returns followup for a question post-stop" {
            Get-PromptClassification "What's the best way to handle authentication here?" $script:stoppedEvents | Should -Be 'followup'
        }
    }

    Context "Denial context (mid-run with unmatched perm_req)" {
        BeforeAll {
            $script:deniedEvents = @(
                [PSCustomObject]@{ event = 'stop';         ts = '2026-01-01T09:00:00Z' }
                [PSCustomObject]@{ event = 'prompt';       ts = '2026-01-01T10:00:00Z'; classification = 'first_prompt' }
                [PSCustomObject]@{ event = 'permission_req'; ts = '2026-01-01T10:00:05Z'; tool = 'Bash' }
                # No tool_done for Bash — it was denied
            )
        }
        It "returns denial_context when there is an unmatched perm_req in the current turn" {
            Get-PromptClassification "Don't run that, it would delete the wrong dir" $script:deniedEvents | Should -Be 'denial_context'
        }
        It "returns denial_context even with neutral text" {
            Get-PromptClassification "Actually that command is wrong" $script:deniedEvents | Should -Be 'denial_context'
        }
        It "returns denial_context even with additive language" {
            Get-PromptClassification "Also you should avoid touching node_modules" $script:deniedEvents | Should -Be 'denial_context'
        }

        It "returns addition (not denial_context) when perm_req was approved" {
            $approvedEvents = @(
                [PSCustomObject]@{ event = 'stop';          ts = '2026-01-01T09:00:00Z' }
                [PSCustomObject]@{ event = 'prompt';        ts = '2026-01-01T10:00:00Z'; classification = 'first_prompt' }
                [PSCustomObject]@{ event = 'permission_req'; ts = '2026-01-01T10:00:05Z'; tool = 'Bash' }
                [PSCustomObject]@{ event = 'tool_done';     ts = '2026-01-01T10:00:10Z'; tool = 'Bash' }
            )
            Get-PromptClassification "Also update the types" $approvedEvents | Should -Be 'addition'
        }
    }

    Context "Multiple sessions of events" {
        It "uses only the most recent stop vs most recent prompt" {
            $events = @(
                [PSCustomObject]@{ event = 'prompt'; ts = '2026-01-01T09:00:00Z' },
                [PSCustomObject]@{ event = 'stop';   ts = '2026-01-01T09:01:00Z' },
                [PSCustomObject]@{ event = 'prompt'; ts = '2026-01-01T10:00:00Z' },
                [PSCustomObject]@{ event = 'stop';   ts = '2026-01-01T10:01:00Z' }
            )
            # Last stop (10:01) > last prompt (10:00) → stopped → classify by text
            Get-PromptClassification "Let's continue with the next feature" $events | Should -Be 'followup'
        }

        It "detects mid-run when last prompt is after last stop" {
            $events = @(
                [PSCustomObject]@{ event = 'prompt'; ts = '2026-01-01T09:00:00Z' },
                [PSCustomObject]@{ event = 'stop';   ts = '2026-01-01T09:01:00Z' },
                [PSCustomObject]@{ event = 'prompt'; ts = '2026-01-01T10:00:00Z' }
                # No stop after 10:00 prompt — Claude is mid-run
            )
            Get-PromptClassification "Add logging too" $events | Should -Be 'addition'
        }
    }
}
