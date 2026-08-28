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
   `sed 's/min-height: 100vh/min-height: auto/g' deck.html > _debug.html`, serve and open
   that instead — sections shrink to their natural content height, so the whole page fits in
   view without needing scroll. Delete `_debug.html` before finishing; never publish it.

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
