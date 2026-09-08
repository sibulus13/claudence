---
name: google-form-builder
description: Build a live Google Form by browser-automating the Google Forms editor (Claude-in-Chrome), transcribing a finalized question-set document exactly. Use when asked to "turn this into a Google Form", "build the form", or "automate filling out a Google Form" and no Forms-API/MCP path exists. Triggers: "make this a Google Form", "build the form for this survey", "automate the form creation".
version: 1.0.0
---

# /google-form-builder

Google's own MCP tooling (`Google_Drive__create_file`) cannot create a Forms-mimetype file —
there is no agentic API path to a Google Form. The only way to build one without a human
clicking through the editor is **Claude-in-Chrome browser automation**, question by question.

## Say this before starting, every time

**This is token-heavy work — say so up front, don't let the user discover it mid-run.** Every
question requires a screenshot to verify state (often two or three: type change, options
filled, Required toggle), and a themed survey/form is typically 8–15 questions. Tell the user
roughly how many questions are being built and that the run will screenshot after nearly every
action — this is not a cheap "just paste the text in" task, it is closer in cost to a multi-step
UI QA pass.

## Prerequisites

1. **The source content is finalized before automation starts.** Building against a
   still-changing question set means redoing work; per the source repo's own conventions this
   is a design-then-build sequence, not simultaneous. Confirm with the user if the doc still
   reads as draft.
2. Load the Claude-in-Chrome tools in one `ToolSearch` call:
   `select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__browser_batch`
3. Do **not** use Google Forms' built-in AI generator — it rewords option text, which silently
   diverges from a carefully-negotiated question set. Build manually, question by question.

## The procedure

1. Create the form (Drive → new Google Form, or navigate directly to a blank form URL), set the
   title and description from the doc's own framing (anonymity/timing disclaimers, if any).
2. For each question, in order: type the title → set the question type → fill options → set
   Required. Use the gotchas below — they are not edge cases, they fired on nearly every
   question in the reference run.
3. After all questions: check **Settings → Responses** (see the anonymity checklist below)
   and do a full top-to-bottom pass in **Preview mode** (the eye icon), not the editor — the
   editor is not the respondent's view (see gotcha 4).
4. Report the live edit-link back to the user. **Never click Publish** — that is a
   send/distribute-equivalent action requiring the user's own explicit go-ahead, same as any
   other irreversible or externally-visible action.

## Gotchas (each one cost real time in the reference run — don't rediscover them)

| # | What happens | Fix |
|---|---|---|
| 1 | A question title that wraps to 2 lines pushes "Option 1" down. A batched click computed from a screenshot taken *before* the title was typed misses. | Never chain a title-type action and an option-click in the same batch when the title might wrap. Screenshot fresh after typing the title, before clicking into the first option. |
| 2 | The "Required" toggle and "add 'Other'" link both live at the block's bottom; adding "Other" shifts Required down. | Click "add Other" first, screenshot, **then** click Required at its now-correct position. Never chain both from one stale screenshot. |
| 3 | Clicking a type-dropdown item (e.g. "Checkboxes") sometimes only *hovers/highlights* it — the underlying type doesn't change, and the dropdown re-renders as a ghost overlay on the next screenshot, showing the OLD type still applied underneath. | Click the option, take a fresh screenshot, click elsewhere to dismiss, screenshot again to confirm cleanly. If it still hasn't taken, use keyboard `Down`/`Up` + `Return` from the currently-open dropdown instead of a second mouse click — more reliable when the mouse path is flaky. |
| 4 | Long checkbox/radio option text shows truncated with "…" **in the editor row only**. This is cosmetic — the full text is stored, and Google Forms wraps (never truncates) long option text for actual respondents. | Verify wording completeness via **Preview mode**, not the editor's option-row width. Don't shorten carefully-written option text to "fix" an editor-only artifact. |
| 5 | For two questions sharing an identical option set (e.g. "which could you explain" / "which have you used"), retyping every option is wasteful and error-prone. | Build the first fully, then use the duplicate icon (bottom toolbar of the question block) and only retype the title. |
| 6 | New-question "+" button adds the block after whichever question was last *focused/clicked*, not necessarily the one you scrolled to — it can land mid-sequence. | Click into the intended predecessor question first, confirm it's focused, then click "+". Screenshot immediately after adding to confirm placement before typing. |
| 7 | **A Google Workspace org can enforce "Collect email addresses: Verified" at the domain level**, disabling the "Do not collect" and "Responder input" options in Settings → Responses (they render greyed-out and unclickable). This can silently flip ON — along with "Limit to 1 response" (which requires sign-in) — the first time the Publish flow is opened, even without clicking Publish, seemingly re-applying an org default. | **Before calling any form "anonymous" or "ready", open Settings → Responses and check "Collect email addresses."** If it's locked to "Verified", tell the user explicitly — this means respondents must sign in with their org Google account and see a required "record my email" prompt, which likely contradicts an "anonymous" framing stated elsewhere in the form. This is an org policy, not a bug in the form — it cannot be fixed by re-toggling settings. |

## Anonymity/settings checklist (run once, at the end)

- [ ] Settings → Responses → "Collect email addresses" — confirm it matches the design intent,
      and flag if it's org-locked to "Verified" (gotcha 7).
- [ ] Settings → Responses → "Limit to 1 response" — this requires sign-in; off if the form
      claims to be anonymous.
- [ ] "Make this a quiz" — off, unless the form is genuinely a quiz.
- [ ] Full Preview-mode read-through, top to bottom, checking wording, option completeness
      (gotcha 4), and Required markers against the source doc.

## Scope

**Global.** Building a form from a spec via browser automation is a generic capability, not
tied to any one project's domain — lives in `~/.claude/skills/` rather than a project's own
skill directory.
