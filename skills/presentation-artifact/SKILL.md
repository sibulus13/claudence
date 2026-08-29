---
name: presentation-artifact
description: Build a scroll/beat-paced HTML presentation artifact (a funding pitch, an internal proposal, a stakeholder deck) — one beat per screen, diagram-first, with a verified nav rail. Use when asked for a "deck", "presentation", "pitch" as an artifact, or a slide-shaped page rather than a report. Includes a real-viewport verification procedure learned from repeated defects — always run it before publishing.
version: 1.0.0
---

# /presentation-artifact

A checklist and verification procedure for building a beat-paced (one-screen-per-section)
HTML presentation artifact, distilled from repeated defects found the hard way across one
long build session. The structural/visual craft (typography, palette, layout) still comes
from the `artifact-design` skill — load that first. This skill is specifically about the
**presentation shape** (beats, nav, pacing) and the **verification steps that catch real bugs
a screenshot alone will not**.

## Shape

- Each "beat" is a `<section>` with `min-height: 100vh`, one idea per beat, diagram-first —
  text supports the visual, it doesn't replace it.
- A sticky side rail (numbered dots, one per beat) plus prev/next arrow buttons and
  `ArrowLeft`/`ArrowRight` keyboard nav.
- Detail that isn't needed to follow the room lives behind a native `<details>` disclosure,
  not on the beat itself — full derivations, appendices, every-comment-addressed trackers.

## The nav-sync bug, and its real fix

Don't use an `IntersectionObserver` with a percentage `rootMargin` band as the only sync
mechanism — it drifts as soon as sections vary in height (a cost beat with an expanded
derivation table is taller than a diagram-only beat), and the highlighted nav item stops
matching what's on screen. Use **scroll-position sync** instead: on `scroll` (rAF-throttled),
find the last section whose `getBoundingClientRect().top` has crossed a line near the top of
the viewport — that's always exactly one answer, regardless of section height. Re-run the same
check on `load`, `resize`, `document.fonts.ready`, and via a `ResizeObserver` on `document.body`
(a `<details>` toggle changes heights without firing a scroll event).

## Verification — do this before every publish, not just the first one

**A screenshot alone will not catch two real bug classes this session hit repeatedly.**
Verify with actual measurements, on a page you can interact with:

1. **Get the real viewport, don't assume one.** `resize_window` does not reliably affect
   content viewed through `claude.ai/code/artifact/...`, and the `computer` screenshot tool
   crops to a fixed width (~1568px) regardless of the real viewport size. Serve a local copy
   (`python3 -m http.server <port>` in the artifact's directory, `navigate` to
   `http://localhost:<port>/file.html`) and read `window.innerWidth`/`innerHeight` there via
   `javascript_tool` — that's the number to design against, not a guessed monitor size.

2. **Scrolling is broken inside the artifact viewer** in this environment — mouse wheel,
   keys, `scrollIntoView`, and `window.scrollTo` all silently no-op there. To inspect a tall,
   `100vh`-paced page without scrolling, make a **temporary debug copy**:
   `{ echo '<!DOCTYPE html><html><head>'; sed 's/min-height: 100vh/min-height: auto/g' deck.html; echo '</body></html>'; } > _debug.html`
   — the `<!DOCTYPE html>` matters: a bare fragment (what the artifact source actually is)
   renders in **quirks mode**, where `document.body` — not the window — becomes the scroll
   container, so `window.scrollTo`/`scrollY` silently no-ops there too (`document.compatMode`
   reads `BackCompat`). Confirm `document.compatMode === 'CSS1Compat'` before trusting any
   scroll call on the debug copy. Serve and open it instead of the artifact URL — sections
   shrink to their natural content height, so the whole page fits in view without needing
   scroll, and with a real doctype, mouse-wheel scroll (`computer` tool's `scroll` action) and
   `window.scrollTo` both work normally. Delete `_debug.html` before finishing; never publish it.

3. **Measure every beat's real height against the real viewport**, on the debug copy:
   ```js
   Array.from(document.querySelectorAll('section.beat')).map(b => ({
     id: b.id, h: b.getBoundingClientRect().height, fits: b.getBoundingClientRect().height <= window.innerHeight
   }))
   ```
   Anything `false` needs trimming (padding, merged cards, a smaller diagram) before publish.

4. **Check for SVG text overflow — `scrollWidth` will NOT catch this.** Inline SVG's default
   `overflow: visible` lets `<text>` paint past its own `viewBox` without ever registering as
   page/layout overflow (no scrollbar, `document.body.scrollWidth` stays unchanged). This is
   the single most likely cause of "content is off the page" that isn't visible in a normal
   overflow check. Verify with the real geometry, on every `<svg>` in the document:
   ```js
   Array.from(document.querySelectorAll('svg')).flatMap(svg => {
     const vb = svg.viewBox.baseVal;
     return Array.from(svg.querySelectorAll('text')).map(t => {
       const b = t.getBBox();
       return { text: t.textContent.slice(0,40), overflowRight: (b.x+b.width) - (vb.x+vb.width) };
     });
   }).filter(o => o.overflowRight > 2)
   ```
   Any hit means the string is too long for a left/right-anchored text element at that
   viewBox width — shorten it, or widen the viewBox and reposition. `text-anchor="middle"`
   text inside a sized box is much safer than left-anchored text near an edge.

5. **Check real horizontal overflow too** (a different, real thing from #4):
   `document.body.scrollWidth <= window.innerWidth`.

6. **Check every inline SVG `<text>` has a `fill`, inherited or explicit — SVG's implicit
   default is opaque black, not `currentColor`.** A `<text>` with no `fill` (and no ancestor
   `<g>` setting one) silently renders correctly in a light theme, where black is close enough
   to the ink token to go unnoticed, then paints literally invisible black-on-near-black the
   moment the page is viewed in dark theme. This is a distinct bug from #4/#5 — it's a color
   defect, not a geometry one — and a plain read-through won't catch it because the light-theme
   render looks fine. Grep every `<text` and confirm each either sets `fill=` itself or sits
   inside a `<g fill="...">`:
   ```sh
   grep -n '<text' deck.html | grep -v 'fill='
   ```
   Any hit that isn't provably inside a fill-setting `<g>` is a real bug — give it an explicit
   `fill="var(--ink)"` (or whichever token the label's weight calls for), never rely on the
   SVG default.

7. **Check whitespace UTILIZATION, not just overflow — a diagram sized small under space
   pressure stays small after the pressure is gone.** Cutting prose elsewhere frees real width
   and height; if a diagram's `max-width` was tuned once during a crunch, it silently keeps
   using a fraction of the space forever unless someone re-checks it. After any content cut,
   re-measure how much of the beat's actual available width the diagrams use, not just whether
   the beat fits vertically — a beat sitting at 400px of an 873px budget with a diagram capped at
   340px next to acres of empty space is passing every overflow check while looking broken.

8. **Check coupled-element counts whenever a repeated element changes — this is a distinct bug
   class from overflow.** A hand-authored SVG with N labels needs N of every element paired to
   them (a connector line per label, a gridline per label). Editing the labels (adding a 4th)
   without re-counting the connector lines (still 3) produces a diagram that renders with no
   error, no overflow, and no fill defect — just a line silently pointing at the wrong thing.
   After any edit that adds or removes a repeated SVG element, count its paired elements too:
   ```sh
   grep -c '<text' section-of-svg   # vs.
   grep -c '<line' section-of-svg   # do these match the intended 1:1 pairing?
   ```
   Don't trust the diff alone — re-read the whole `<svg>` block, since the paired element may be
   many lines away from the one actually edited.

9. **A rotated `<text>` element breaks the automated overflow check — verify it by screenshot,
   not by the geometry check.** `getBBox()` on an SVG `<text>` with a `transform="rotate(...)"`
   returns the PRE-rotation bounding box, so the overflow-check formula in step 4 reports
   nonsensical (often deeply negative) numbers for any rotated label — a false positive, not a
   real bug, but it can't be told apart from a real one by the numbers alone. Any diagram using
   `transform="rotate"` on text (a rotated axis label is the common case) needs a screenshot
   check specifically for that element; don't let the false positive get "fixed" by guessing,
   and don't let it get ignored as "probably fine" either — look at it.

10. **Fitting and not-overflowing is not the same claim as looking good — take a real
   screenshot and read it, every time, not just the numeric checks above.** Across one session,
   repeated height-budget pressure led to shrinking font sizes (0.78rem uppercase labels,
   0.85rem body text) turn over turn to make new content fit a fixed `100vh` box. Every
   measurement check passed (height fit, no overflow, fill set) while the actual rendered page
   turned into a dense, small-type report — exactly what a beat-paced deck is supposed to not
   be. The fix is architectural, not a smaller font: **cut or consolidate content before you
   shrink text below ~0.95rem for anything a reader is meant to actually read** (a
   caption/footnote can go smaller; primary content should not). Screenshot the debug copy at
   each beat (scroll to it, then `computer` screenshot) and actually look before publishing —
   a wall of small text passes every mechanical check and still fails the room.

11. **Run the design-token gate before every publish — deterministically, not by re-reading the
   CSS by eye.** Step 10 describes the failure; this is the mechanical check that catches it
   going forward instead of relying on a human noticing. `check-design-tokens.py`, in this same
   skill directory, fails the moment any `font-size` in the deck isn't a `var(--text-*)` token
   and isn't on its explicit, reasoned allow-list:
   ```sh
   python3 check-design-tokens.py deck.html
   ```
   A real off-scale value fails the gate; a genuine, deliberate exception (a display heading, an
   icon size, UI chrome) gets added to `ALLOWLIST` in the script **with a one-line reason** —
   never by loosening the check itself. Content inside a collapsed `<details>` is exempt by
   design (reference tier, read once, up close) — everything else must resolve to a token.

## Content discipline, learned the hard way

- **A model or a figure that changes must be hunted down everywhere else it's cited.** A cost
  model that gets revised in the source-of-truth doc but not in the narration script and the
  older brief produces three different headline numbers for the same claim, on the same day —
  the single most damaging thing a sharp reviewer catches in the first five minutes.
- **Don't let an illustrative example quietly borrow the confidence of a measured one.** If
  beat 2 shows two parallel failure modes and only one is backed by a real, checked data point,
  label the other as illustrative and name the real check that would confirm it — don't present
  them with equal weight.
- **Reserve semantic colors for one meaning across the whole document.** If teal/gold/red mean
  funded/pending/critical in the footer legend, don't reuse the same three colors locally for a
  different meaning (e.g. topic categories) — add a neutral/outlined variant for plain labels
  instead, or the legend becomes actively misleading.
- **A "concurrency" or "scaling" cost line needs one explicit question answered before it's
  trusted**: is this always-on or auto-scaled? Modeling burst-only infrastructure at a flat
  always-on annual rate can overstate a worst-case cost by 3-4x — a real correctness bug, not
  a rounding difference.
- **State formulas in the terms a reader would use**, not just as a named-constant expression —
  a variable name and a value is not the same as explaining what it represents and where it
  came from.
