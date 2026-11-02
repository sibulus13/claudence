---
id: fix-friction-system-prompts
type: bugfix
status: draft
touches: [harness]
layers:
  architecture: none
  component: none
  functional: none
  data: none
created: "2026-11-02"
owner: harness
lifecycle: false
---
# The friction score counts system-injected prompts as the owner's

## References

### Local

| Source (file:line) | Status (working / partial / broken) | What it shows | Decision (extract / wrap / replace / ignore) + reason |
|---|---|---|---|
| C:/Users/Michael/.claude/telemetry/lib/classification.ps1:96-121 | broken | `Get-PromptClassification` decides from timing alone and counts every prior prompt, so an injected prompt is scored as the owner's and also shifts the owner's next label | wrap: owner-only prior events, a `system` label, and the new pure functions below |
| C:/Users/Michael/.claude/telemetry/analyze-session.ps1:89-102 | broken | the Stop-time scorer trusts the live labels and reads only the telemetry log | replace: the scoring moves into a pure `Get-FrictionScore` in the lib, fed the telemetry events joined to the transcript |
| C:/Users/Michael/.claude/telemetry/analyze-session.ps1:22-26 | working | the Stop hook reads its JSON input, which carries `transcript_path` | extract: the transcript is reachable at Stop |
| C:/Users/Michael/.claude/telemetry/analyze-session.ps1:213 | broken | the report's `transcript_path` is hard-coded to `history.jsonl` | replace: the hook input's `transcript_path` |
| C:/Users/Michael/.claude/telemetry/analyze-session.ps1:350-352 | working | the Stop chime plays through `SoundPlayer` | wrap: `TELEMETRY_NO_SOUND=1` skips it, so tests never play sounds |
| C:/Users/Michael/.claude/telemetry/log-prompt.ps1:46-53 | working | each prompt event stores `ts` (local offset), `classification` and `prompt_text` cut to 1,000 characters | extract: the join reads these fields |
| C:/Users/Michael/.claude/telemetry/log-prompt.ps1:75 | partial | `state.prompts` counts every prompt | wrap: `Test-CountsAsPrompt` |
| C:/Users/Michael/.claude/telemetry/log-prompt.ps1:97-117 | partial | the theme block bumps or opens a theme for any prompt | wrap: `Test-UpdatesTheme` gates the whole block |
| C:/Users/Michael/.claude/tests/classification.tests.ps1:1 | working | Pester 5 suite that dot-sources the lib | extract: the new cases go here; new functions `Test-IsSystemPrompt`, `Test-CountsAsPrompt`, `Test-UpdatesTheme`, `Join-TranscriptSource`, `Get-FrictionScore` live in `telemetry/lib/classification.ps1` |

### Web

| Source (URL) | Date checked | What it shows | Decision |
|---|---|---|---|
| https://code.claude.com/docs/en/hooks | 2026-11-02 | common hook input carries `session_id`, `prompt_id`, `transcript_path` and `cwd`; `UserPromptSubmit` also fires for scheduled tasks, `/loop` iterations, background subagent reports and messages from other sessions, with no field naming the origin | extract: live labels read the text; the Stop-time score reads the transcript's `promptSource` |

## Operating envelope

| Assumption | How it is observed (not hoped) | If violated |
|---|---|---|
| Each transcript prompt entry carries `promptSource`; `typed`, `queued` and `suggestion_accepted` are the owner, `system` and `sdk` are not | adversary probe 2026-11-02: 1,192 entries with the field (typed 443, queued 51, system 635, sdk 62, suggestion_accepted 1); AC-1 uses all five | keep: an event with no matching transcript entry keeps its live label and is counted under `unlabelled` in the report (AC-7) |
| Live text markers cover the injected prompts seen so far: `<task-notification`, `<agent-message`, `<cross-session-message` | probe over 2,726 telemetry sessions (1,222, 414 and 15 hits; 0 for every other candidate), pinned by AC-2 and counted live by AC-7 | flag: the Stop-time count of `system` prompts the markers missed is written to the report as `marker_misses` |
| `prompt_id` is not unique per prompt | design review 2026-11-02: two typed prompts in one transcript share a `promptId`; the AC-1 fixture repeats it | refuse: the join never uses it |

## Root cause

The live classifier labels every prompt by timing (running means `addition`, a stop plus an override word means
`override`) without asking who sent it, and counts injected prompts as prior events. The Stop-time scorer trusts
those labels. Claude Code injects task notifications, subagent hand-backs and cross-session messages through the same
`UserPromptSubmit` hook. The transcript records each prompt's true source, but nothing read it.

## Observed vs expected

- **Observed:** the retrospective of 2026-11-02 ran over the reports now in `telemetry/reports/archived/`, covering the 6 sessions since 2026-10-29.
  - 249 of 335 friction notes (74%), and 195 of 225 override points, came from injected prompts.
  - In 30 cases, the owner's reply to a stop was scored `addition` because a notification had arrived first.
  - The report's `transcript_path` pointed at the prompt history.
- **Expected:**
  - At Stop, each telemetry prompt event is joined to its transcript entry: same text prefix and timestamps within 5 s after converting both to UTC, the nearest timestamp winning, each entry used at most once, sidechain entries skipped.
  - Only owner prompts are scored and counted (`prompt_count`, `overrides`, `additions`).
  - An injected prompt scores 0, adds no note, opens or bumps no theme, and counts in no rate.
  - The owner's prompt is classified against the owner's previous prompt.
  - The report links the real transcript.

## Acceptance criteria

| AC | Traces | Given / when | Pass when | Fail when | Test |
|---|---|---|---|---|---|
| AC-1 | - | `Get-FrictionScore` over fixture telemetry events and a fixture transcript with all five `promptSource` values (real texts), two owner prompts sharing one `promptId` and identical text, a sidechain entry, and offsets `Z` vs `-08:00` | each event joins its own entry; only `typed`, `queued` and `suggestion_accepted` prompts are scored and counted; the report counts exclude the rest | a system or sdk prompt is scored or counted, or a join crosses entries | tests/classification.tests.ps1 |
| AC-2 | - | live labelling of prompts starting with `<task-notification>`, `<agent-message from=`, `<cross-session-message from=`, each after leading whitespace | each is `system` | any is `addition` or `override` | tests/classification.tests.ps1 |
| AC-3 | - | owner look-alikes: a marker mid-text (`why did <task-notification> fire?`), a `<pasted_content` paste, the typed line `/retrospect`, an empty prompt | none is `system` | any is silenced | tests/classification.tests.ps1 |
| AC-4 | - | owner stops, a notification arrives, the owner replies 2 s later | the reply is classified against the owner's last prompt (`followup` or `override`), not `addition` | it is `addition` | tests/classification.tests.ps1 |
| AC-5 | - | a session whose first prompt is a notification, then the owner's first prompt | the notification is `system`; the owner's prompt is `first_prompt` | otherwise | tests/classification.tests.ps1 |
| AC-6 | - | `Test-UpdatesTheme` and `Test-CountsAsPrompt` for every label, including `followup` | both are false for `system` and true for every owner label | a system prompt bumps a theme or a rate | tests/classification.tests.ps1 |
| AC-7 | - | `analyze-session.ps1` run end to end in a child process with `USERPROFILE` set to a temp folder and `TELEMETRY_NO_SOUND=1`, fed a Stop input with `transcript_path` | the report's `transcript_path` is that path; `marker_misses` and `unlabelled` are present; no real counter changes and no sound plays | it names `history.jsonl`, omits a count, or touches the real telemetry folder | tests/classification.tests.ps1 |

## Gate plan

| Risk | Kind (deterministic / qualitative) | Check | Blocking / advisory |
|---|---|---|---|
| an injected prompt is still scored, or an owner prompt is silenced | deterministic | powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/run-tests.ps1 | blocking |
| the existing classifier cases regress | deterministic | the same suite, unchanged existing cases | blocking |
