---
name: book-meeting
description: Book a meeting with named attendees — resolve them to real email addresses, estimate a reasonable duration, find the next opening that respects everyone's actual working hours (not just the organizer's), and confirm before sending the invite. Invoke whenever the user asks to schedule, book, or find time for a meeting/call/chat with one or more people.
---

# Booking a meeting — resolve, estimate, check real hours, confirm

**Origin: 2026-09-03.** A first pass at this found a "free" slot for two colleagues using a flat
9am–5pm Pacific window — the organizer's own assumed hours, applied to everyone, unchecked. One
attendee's identity was also nearly guessed from a large attendee list on an unrelated meeting.
Both are silent failure modes: a "free" slot outside someone's real hours reads as a real answer
until they push back, and a misdirected invite is worse — an email lands on the wrong desk.

## The procedure, in order

### 1 · Resolve every attendee to a real email — never guess between look-alikes

- `search_events` on their name (and a plausible full name / last name if only a first name was
  given). A single confident match — especially a recurring 1:1 or a title naming them directly —
  is enough; state where it came from.
- **Two or more plausible matches, or zero matches: STOP and ask** (`AskUserQuestion`, present the
  candidates found). Never pick the more-likely-looking one — a coffee-chat invite sent to the
  wrong person is a real, if small, mistake, and it's cheap to just ask.

### 2 · Estimate a reasonable duration — state the default, don't apply it silently

If the user didn't give one, infer from the stated purpose and say so out loud:

| Purpose sounds like | Default |
|---|---|
| coffee chat · 1:1 · quick sync · check-in | 30 min |
| a quick question · a status ping | 15 min |
| working session · review · planning · workshop | 60 min |
| unstated / unclear | 30 min, flagged as a guess |

### 3 · Check REAL operating hours, not the organizer's assumed ones

**This is the step that was skipped the first time.** A calendar's free/busy data (what
`suggest_time`/freebusy actually returns) only says BUSY or FREE — it says nothing about whether
9am is a reasonable hour for that specific person. Check sources **in this order, stopping at the
first authoritative hit**:

1. **Slack profile — authoritative, check this FIRST.** `slack_search_users` on the attendee's
   name, then read the result's `Timezone` field directly — Slack's own configured timezone
   setting, a real fact, not an inference. The display name is a second, free confirming signal:
   a name like "Liz Steward (Vancouver, BC)" states the city outright. Two for the price of one
   API call — always check both fields, don't stop at the timezone alone if the name also carries
   a location.
2. **Any other explicit source** — the user states it, a team roster / `CLAUDE.local.md`-style
   reference names a colleague's home office, or a `WORKING_LOCATION` calendar event is visible.
3. **A soft signal, only if 1 and 2 give nothing** — the `timeZone` field on events an attendee has
   *organized* (not merely attended) is a weak clue, never authoritative on its own; a shared org
   calendar's default timezone can leak onto events regardless of where the organizer actually
   sits. (Confirmed once: this soft signal and the Slack-profile fact agreed exactly — Slack is
   still the one to check first and cite, because it doesn't need a lucky organized-event to exist.)
4. **No signal at all** — do not silently default to the organizer's own timezone/hours and call it
   done. Use a **narrower, conservative core-hours window** (e.g. 10:00–16:00, not 9:00–17:00) in
   the best-guess timezone, and **say plainly that this is unverified** — name which attendee(s) it
   applies to and invite a correction.

**Take the narrowest overlapping window across every attendee**, not the organizer's alone — if
one person's real hours are 9–17 Eastern and another's are 9–17 Pacific, the search window is the
intersection (9am–2pm Pacific in that example), not either person's own full day.

### 3a · Check for back-to-back sandwiching, not just "is this slot free"

**A slot with nothing scheduled in it can still be a bad slot** — jammed between two other
meetings with zero transition time is a real cost the free/busy check alone won't show, since it
only asks about the meeting's own window. For the top few candidates from step 4:

- Query `suggest_time` for a window bracketing the candidate — 30 min before through 30 min after
  (a 90-min window for a 30-min meeting) — same attendees, same duration as the bracket. An empty
  result means at least one attendee has something touching one or both edges.
- If that comes back empty, split it: check the 30-min-before and 30-min-after windows separately
  to see which side is actually tight (a single tight side is a much smaller cost than both).
- **If every candidate in the window fails this check, say so plainly rather than silently
  dropping the requirement or picking one anyway without disclosure.** Busy schedules can
  legitimately leave zero fully-buffered slots in a given window — that's a real finding to
  surface, not a bug to hide. Recommend the least-bad option and name the trade-off, or offer to
  widen the search (later hours, a longer horizon) instead.

### 4 · Find the next reasonable opening

- `suggest_time` with every resolved email, the duration from step 2, and the business-hours
  window from step 3 (`preferences.startHour`/`endHour`, `excludeWeekends: true` unless told
  otherwise).
- Default lookahead: **two weeks** from today, unless the user names a different horizon.
- **Bias toward soonest** — return a short list (3–5 options spread across distinct days), not
  an exhaustive dump. The point is one good next opening, with a couple of alternates.

### 3b · Block out a presumed lunch hour, per attendee, in THEIR local time

**Added 2026-09-03.** Even when a slot is technically free, don't book across what's reasonably
someone's lunch. Default assumption: **12:00–13:00 in each attendee's own local time** (from step
3's confirmed timezone, not the organizer's) is presumptively reserved, whether or not it's
labeled on their calendar — most people don't bother blocking lunch even though they still expect
not to be booked then. If an explicit "lunch"-labeled event is visible on any calendar this
session can see, that overrides the default with their actual time; otherwise apply the flat
12–1 default. **Convert each attendee's lunch window into the organizer's timezone and exclude
all of them from the search** — a meeting must fall outside every attendee's own lunch hour, not
just the organizer's. (This caught a real miss: the first two "buffered" picks in one session
both landed inside the Pacific attendee's actual lunch hour, found only after this step was added.)

**A slot ending right as lunch starts, or starting right as lunch ends, is a GOOD placement, not a
tight one** — lunch itself is the transition buffer, not a back-to-back meeting. Prefer these over
slots merely adjacent to another meeting.

### 3c · Start times land on `:00` or `:30`

**Added 2026-09-03.** A candidate inside a wide free block can drift onto an odd boundary (`:15`,
`:45`) if it's centered or buffer-optimized without this constraint — technically fine, off the
grid everyone's calendar actually runs on. Once a clear block is found, place the meeting at the
nearest `:00`/`:30` boundary *within* that block rather than the mathematically centered point,
preferring the edge that lands the natural-transition side (lunch, day-start) per step 3b.

### 4a · If nothing in the horizon has real buffer, widen once before proposing

**Confirmed 2026-09-03**: within a 2-week horizon, every candidate can legitimately be sandwiched
between other meetings for at least one attendee — busy calendars can leave zero fully-buffered
slots in a short window, and that's a real finding, not a bug. Before reporting "nothing works,"
widen the horizon once (e.g. 2 weeks → 4 weeks) and look specifically for slots that sit inside a
**wide free block** (`suggest_time` returning ≥60 min free, not just the requested duration) — a
30-min meeting centered in a 90-min free block has 30 min of proven buffer on each side, verified
by the block itself, no separate check needed. **If the widened search still finds nothing
buffered, stop asking and propose the best available option** with the trade-off named — don't
keep bouncing the decision back for a third round.

### 5 · Present the top 2 — not a comprehensive list

**Corrected 2026-09-03, standing preference.** Give the two best candidates, each with the specific
reason it's the pick (buffer, centering, day), not every slot found. A comprehensive list was the
default the first time; the user corrected it explicitly — offer to widen or show more only if
asked, don't lead with the full set.

Every slot shown carries its timezone label. Any remaining hours-window assumption from step 3 is
stated next to the option it affects, not buried in a caveat nobody reads — e.g. "assuming Liz is
on Pacific hours since I have no signal otherwise; flag if she's elsewhere."

**Creating and sending the invite is an explicit-permission action — never do it on this step.**
Ask which slot, confirm the title and whether a video link is wanted, then create it.

### 6 · Book it

**Defaults, confirmed 2026-09-03 — apply without asking unless told otherwise**:
- **Title**: the meeting's own already-stated purpose (a "coffee chat" ask titles itself "Coffee
  Chat") — don't ask separately for a title the purpose already gives; only ask when the purpose
  is genuinely unstated or ambiguous.
- **Video**: **Google Meet**, always (`addGoogleMeetUrl: true`) — the standing default source,
  unless the user names a different platform.

`create_event` with the confirmed slot, every resolved attendee email, the title, and the Meet
link. Report back the event link and the Meet URL.

## What this skill will not do

- Guess a colleague's identity from a partial name in a crowded attendee list.
- Apply the organizer's own working-hours assumption to every attendee without saying so.
- Send an invite without an explicit slot confirmation from the user first.
