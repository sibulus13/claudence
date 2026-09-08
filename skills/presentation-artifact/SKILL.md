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
- **Centering is an owner preference, not a default — ask, don't assume.** This skill went
  top-anchor → full horizontal+vertical centering on direct, repeated owner instruction (asked
  twice, the second time as an explicit directive). Top-anchor's real argument still holds
  (title position stays stable across variable-height beats) but so does full centering's
  (better viewport-space use, reads intentional rather than ad hoc) — **neither is universally
  correct, so a new deck asks the owner rather than picking either as a house default.**
  If full centering is chosen: set it on the section (`justify-content: center`,
  `text-align: center`) but **explicitly re-left-align structured card content**
  (`.card { text-align: left }`) — Who:/Wants:-style label:value text reads worse centered, and
  a `max-width`-constrained block (`.lede`/`.prose`) needs `margin: auto` rather than
  `align-self: flex-start` to center as a block while still inheriting centered text.
- A sticky side rail (numbered dots, one per beat) plus prev/next arrow buttons and
  `ArrowLeft`/`ArrowRight` keyboard nav. **Number beats flat and sequential (1, 2, 3…)** — no
  lettered sub-beats (`1a`/`1b`). If a beat has genuinely separable content, split it into two
  full sequential beats instead; a title alone should say what each screen is.
- Detail that isn't needed to follow the room lives behind a native `<details>` disclosure,
  not on the beat itself — full derivations, appendices, every-comment-addressed trackers.
- **No internal/local references in visible text — file paths, script names, ticket IDs
  (`specs/…`, `scripts/…`, `*.md`, `ES-####`) belong inside a collapsed `<details>` only, never
  in a beat's plain-sight copy.** A "publishable" artifact reads as unfinished the moment a
  room sees a bare file path; "every figure is sourced and available on request" carries the
  same honesty without exposing the path.
- **No forward references between beats.** A beat may cite an EARLIER beat by number ("the gap
  shown in beat 4") — the room has already seen it, it's a legitimate callback. It may never cite
  a LATER one ("the 4 items in beat 7") — the room hasn't gotten there yet, and naming a number
  they can't check yet reads as homework, not a payoff. Either drop the number ("ahead," "the
  closing ask," "the room's own three options, later") or restructure the sentence so it doesn't
  need the forward pointer at all. Audit with `grep -n 'beat [0-9]'` and check each hit's
  direction before publishing.

## Every specific claim gets its tier checked, not just its existence

**A claim tracing to a source file is not automatically safe — check what tier that source
itself assigns it.** Found 2026-08-31: a persona-beat line ("cross-tenant peer benchmarking is
the strongest case") traced cleanly to a real file, but that file's own status column said
`answered-weakly` — self-authored, corroborated by one account, explicitly not customer-ranked.
Sitting three rows away in the same register, a different claim was marked `verbatim from named
colleagues`. Same document, two different evidence tiers, and only reading the tier column (not
just confirming the citation exists) tells them apart. **If a claim's own source marks it
weak/self-authored, cut it or fold it into something the strong claims already carry — don't
present it at the same visual confidence as a verbatim-sourced one.**

## The type scale — a real floor, not a web-body-text scale

**`rem` is root-relative (the browser's default 16px), not relative to a custom `body`
font-size** — a page that sets `body { font-size: 19px }` and then defines tokens as `.85rem`
etc. is NOT scaling off 19px; it's scaling off 16px regardless, and a comment claiming otherwise
will mislead every future edit. Confirmed the hard way 2026-08-31: a "13.6px floor" went
unnoticed for most of a build session because the token comment asserted a false relationship.

**Default starting scale for a new deck** — grounded in real presentation-design guidance
(Kawasaki's 10/20/30 rule floors body text at 30pt/~40px for a *projected* room; a screen-viewed
HTML artifact doesn't need to go that far, but should sit well above ordinary web body text):

```css
--text-2xs: 1.15rem;  /* 18.4px — the floor: fine print, captions, read once up close */
--text-xs: 1.3rem;    /* 20.8px — secondary body text, pill labels */
--text-sm: 1.45rem;   /* 23.2px — default body text */
--text-md: 1.7rem;    /* 27.2px — card headings */
```

Any raw value used outside these tokens (a hero lede, a display stat) should be **bigger than
the token it's near**, not smaller — a "larger opening statement" that renders smaller than the
body text token defeats its own purpose. Check this explicitly when allow-listing a raw value in
`check-design-tokens.py`, not just whether it's on the allowlist at all.

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

0. **Every companion HTML file — not just the main deck — needs its own `<meta charset="utf-8">`
   as the first line.** Missed on a report built alongside a deck that already had one: every
   em-dash and curly quote rendered as mojibake (`â€"`) once wrapped for a browser to render,
   because without an explicit charset the browser guesses one, and it guesses wrong for UTF-8
   punctuation. Silent and easy to miss in a code read — it only shows up rendered. Check the
   first line of every `.html` file this skill produces, every time, not just the one the user
   is looking at.
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

4. **Check for SVG shape overflow — on every shape type, not just `<text>`, and `scrollWidth`
   will NOT catch any of it.** A `<rect>`/`<circle>`/`<line>`/`<polygon>` can extend past its own
   `viewBox` exactly as easily as text can, and it registers as neither a scrollbar nor a change
   to `document.body.scrollWidth` — SVG internals are invisible to page-level overflow checks.
   **Confirmed the hard way in report-artifact's own history**: a text-only version of this check
   (below, restricted to `<text>`) passed clean on a diagram whose 4th box was visibly clipped on
   the right — the box's own `<rect>` extended past the viewBox while its `text-anchor="middle"`
   label, narrower and centered, happened to stay just inside. A check scoped to text alone cannot
   see the shape overflowing around it. Verify all four directions, on every shape, on every
   `<svg>` in the document:
   ```js
   const bad = [];
   document.querySelectorAll('svg').forEach(svg => {
     const vb = svg.viewBox.baseVal;
     if (!vb || (vb.width === 0 && vb.height === 0)) return;
     ['rect','circle','line','polygon','text','ellipse'].forEach(tag => {
       svg.querySelectorAll(tag).forEach(el => {
         if (el.hasAttribute('transform')) return; // rotated text: step 9 below, screenshot instead
         let b; try { b = el.getBBox(); } catch(e) { return; }
         if (b.width === 0 && b.height === 0) return;
         const over = Math.max(
           (b.x + b.width) - (vb.x + vb.width), (b.y + b.height) - (vb.y + vb.height),
           vb.x - b.x, vb.y - b.y);
         if (over > 2) bad.push({ svg: (svg.getAttribute('aria-label')||'').slice(0,40), tag, text: (el.textContent||'').slice(0,25), over: Math.round(over) });
       });
     });
   });
   JSON.stringify(bad);
   ```
   An empty array is the only acceptable result. Any hit on a `<text>` means the string is too
   long for its position at that viewBox width — shorten it, or widen the viewBox and reposition;
   a hit on a shape means the shape itself needs repositioning or the viewBox needs to grow to
   actually contain it (growing the viewBox alone never clips anything further — verify the
   change didn't just move the overflow elsewhere). `text-anchor="middle"` text inside a sized box
   is safer than left-anchored text near an edge, but it does NOT make the box around it safe —
   check the box on its own terms, every time.

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

   **The gate also checks raw SVG `font-size="N"` attributes against an 11px floor** (closed
   2026-08-31 — the CSS-only check had missed 9px/10px SVG labels in a shipped deck). SVG text
   isn't on the rem-based token scale (it's viewBox px scaled by the diagram's own render width),
   so there's no token to point it at — the fix is either raising the attribute to ≥11, or moving
   the text into a collapsed `<details>` if it's genuinely reference-tier.

12. **To verify nav actually works, invoke it via JS directly — not the `computer` tool's
   synthetic click/key actions, which produce false "broken nav" readings.** Confirmed 2026-08-31:
   `computer` tool synthetic clicks and keypresses on a nav-rail button did not move `scrollY` at
   all, while `document.querySelector(...).click()` via `javascript_tool` on the exact same button
   worked immediately (`scrollY` jumped correctly, `aria-current` updated). The deck's own
   `scrollIntoView`/`window.scrollTo` code was never the problem — the automation tool's synthetic
   input doesn't reliably trigger the handlers a real user gesture would. Verify with:
   ```js
   document.querySelector('#rail button[data-target="beat-N"]').click();
   window.scrollY // should match the target section's offset
   ```
   for every nav button, and separately confirm `window.scrollTo` moves the page when called
   directly. If both work via direct JS, treat navigation as verified — don't distrust it just
   because a `computer` tool click or keypress appeared to do nothing.

13. **"Fits the viewport" and "uses the viewport well" are different claims — measure both.**
   A beat can pass every height-budget check in step 3 while still using under 30% of the
   available space, which reads as sparse/unfinished even though nothing is technically wrong.
   Measure real content-vs-viewport utilization, not just whether it overflows:
   ```js
   const vpH = window.innerHeight, vpW = window.innerWidth;
   Array.from(document.querySelectorAll('section.beat')).map(b => {
     let minY=Infinity, maxY=-Infinity, minX=Infinity, maxX=-Infinity;
     Array.from(b.children).forEach(c => {
       const r = c.getBoundingClientRect();
       if (r.width===0 && r.height===0) return;
       minY=Math.min(minY,r.top); maxY=Math.max(maxY,r.bottom);
       minX=Math.min(minX,r.left); maxX=Math.max(maxX,r.right);
     });
     return { id: b.id, heightUtil: Math.round(100*(maxY-minY)/vpH)+'%', widthUtil: Math.round(100*(maxX-minX)/vpW)+'%' };
   });
   ```
   A beat under ~40% height utilization is a real finding, not noise — either the content
   deserves more visual weight (bigger diagram, bigger type, a two-column layout instead of
   stacked), or it's genuinely a light closing/transition beat and that's fine, but say so
   rather than leaving it unexamined. **Don't pad with filler text to fill the number** — enlarge
   the real content (bigger `max-width` on a diagram scales its text too, via the viewBox ratio)
   before inventing new copy.

14. **Real viewport height varies by reading, even within one session — verify against the
   smaller of any two readings you get.** Measured 873px and 929px at different points in the
   same browser session this build (window chrome differences). Design to the stricter number;
   a beat that fits at 929 but not 873 will clip for some viewers.

15. **`align-items: center` on the beat container silently floats any `max-width`-constrained
   block off the left margin — this is not just a text-class bug, it's every figure and grid
   with its own `max-width` too, and patching one instance at a time never fully kills it.**
   Traced to ground on 2026-08-31 after THREE rounds of "this still looks off-center": a `.lede`
   fix (`align-self: flex-start`) resolved the subtitle, but every diagram and card-grid narrower
   than the full column (which is most of them — a 820px figure in a ~1450px column, a 1300px
   grid, etc.) kept floating toward the viewport's visual center underneath a flush-left title,
   because `align-items: center` centers ANY child narrower than its container, regardless of
   class. **The fix that actually holds**: don't patch classes one at a time — flip the section's
   own `align-items` (and `text-align`) from `center` to `flex-start`/`left` as the DEFAULT for
   every content beat, with the hero/cover page as the one explicit exception
   (`section.beat.hero { align-items: center; text-align: center; }`). One left margin, every
   element anchors to it, and the whole "is this centered enough" question class stops existing.
   If a user flags "still off-center" a second time after a targeted fix, that's the signal this
   is a container-level default, not another instance to patch. **Caveat, learned the very next
   turn: don't over-rotate past what was actually asked.** "Text is off-center, fix it" does not
   automatically mean "make everything left" — it can just as easily mean "the centering itself
   is fine, put it back correctly." Title/subtitle-left + body-centered is a legitimate, common
   formal-deck pattern on its own; the bug above was real, but the FIX is "center it symmetrically
   within the full section width," not "stop centering anything." When in doubt about which of
   the two the complaint means, the safer default is the narrower one (fix the centering) —
   flipping the whole page to left-everything is the bigger, more visible change and should only
   follow an explicit "make it all left" instruction, not an inferred one.
16. **After ANY edit to any beat, re-read that beat's own text for orphaned references** — a
   number, a claim, or a phrase ("the derivation," "40 users," "shown below") that used to point
   at content on the SAME beat, before the edit removed or moved that content. Trimming an
   appendix or restructuring a paragraph is exactly when this happens: the sentence survives, the
   thing it pointed at doesn't. This is a standing pass, not a one-time fix — run it as part of
   every publish, on every beat touched that round, not just the beat the user flagged.
17. **A roadmap or deliverable-by-deliverable beat is grounded in the project's own architecture
   spec, never invented milestone labels.** "What does each checkpoint actually deliver" has a
   real answer sitting in the codebase's own architecture/phasing doc (committed checkpoints,
   named module boundaries, what's covered vs. not) — go find it before designing the beat, even
   if an earlier attempt at the same beat used plausible-sounding placeholder labels instead.
18. **If the same beat gets redesigned 3 times and the feedback stays vague ("still not right"),
   stop redesigning blind and ask a diagnostic question instead** — not "which layout do you
   want" again (already tried), but "what's actually wrong: too dense, wrong content, wrong
   visual style, or something else" (multi-select). A 4th guess costs a full rebuild; a targeted
   question costs one reply. When the answer names "wrong content," the fix is usually an axis
   change, not a layout change — e.g. a roadmap written in engineering-milestone language
   ("citation wired," "matched pairs") rewritten in end-user-validation language tied to the
   buyer persona's OWN stated words ("what's overstretched," "without digging") is a different
   beat, not a restyled one, and it's also usually less dense — technical framing tends to drag
   in supporting detail (module names, tool counts) that user-facing framing doesn't need at all.
19. **Hard validation has TWO separate failure modes, and checking only one misses the
   other.** Found the hard way: v1 of this check measured BOX position (does a nested element's
   center drift from its parent's center) — that catches a `figcaption` silently left-anchoring
   from a missing `margin:auto`. It does NOT catch a full-width element whose box is already
   symmetric but whose `text-align` is still `center` — a pill, a card-less label, anything that
   inherited the section's base center and was never given its own class rule. Box position and
   computed `text-align` are different questions; a check that answers only the first will pass
   elements that are still visibly wrong. **Run both, every time, not only when a user flags a
   specific beat** — paste into `javascript_tool` against the debug-verify copy:
   ```js
   // (a) computed text-align — catches inherited-center on any full-width element
   const bad = [];
   document.querySelectorAll('section.beat:not(.hero) p, section.beat:not(.hero) h2, section.beat:not(.hero) h3, section.beat:not(.hero) li, section.beat:not(.hero) span, section.beat:not(.hero) div')
     .forEach(el => {
       if (el.closest('figcaption') || el.tagName === 'FIGCAPTION') return; // the one deliberate exception
       const hasOwnText = Array.from(el.childNodes).some(n => n.nodeType === 3 && n.textContent.trim());
       if (!hasOwnText) return;
       const ta = getComputedStyle(el).textAlign;
       if (ta === 'center' || ta === 'right' || ta === 'justify') bad.push({beat: el.closest('section.beat')?.id, tag: el.tagName, cls: el.className, ta, text: el.textContent.trim().slice(0,40)});
     });
   // (b) box-position drift — catches a nested max-width element with no margin:auto
   document.querySelectorAll('section.beat p, section.beat figcaption, section.beat h2').forEach(el => {
     if (el.closest('.beat-head') || el.classList.contains('lede') || el.classList.contains('footnote') || el.closest('.card')) return;
     const er = el.getBoundingClientRect(), pr = el.parentElement.getBoundingClientRect();
     if (er.width < 2) return;
     const drift = Math.abs((er.left + er.width/2) - (pr.left + pr.width/2));
     if (drift > 4) bad.push({beat: el.closest('section.beat')?.id, tag: el.tagName, drift: Math.round(drift), note: 'box-drift'});
   });
   JSON.stringify(bad);
   ```
   An empty array from BOTH checks is the only acceptable result before publishing — one check
   passing is not evidence the other would too. Every class that touches typography (`.pill`,
   `.cost-step`, any future card-like wrapper) needs an explicit `text-align` the day it's
   written, not left to inherit the section default and get discovered later.

## Component library — named parts, not per-beat inline styles

A beat assembles from a small, fixed set of named parts, always in this order. Standardizing them
once (in CSS) is what makes a new beat consistent by default instead of by discipline — and it's
what actually fixes a recurring "this looks slightly off" complaint, which is usually five beats
each inventing their own inline version of the same element.

| Part | Class | Rule |
|---|---|---|
| Heading | `.beat-head` (num + `<h2>`) | Always left-justified, always present |
| Subheading | `.beat-head + .lede` | Optional per beat — only when the beat needs one, never filler. When present: same size, same margin, same left alignment every time (one CSS rule, not a per-instance inline override) |
| Body | `.grid` (single panel) or `.split` (two-panel, with a `.cols-N-M` modifier for the column ratio) | Whichever the content needs; centered as a balanced block either way |
| Closing caption | `.footnote` | The "one more small line" pattern (a takeaway, a caveat, a companion-report pointer) — one size, one color, one spacing, wherever it appears. Never a second big heading-weight element partway down a beat: that reads as a second subheading competing with the real one above it, especially when the real one is left-justified and this one defaults to centered |

**The failure this replaces**: five beats each writing their own inline `style="font-size:...;
margin:...; color:..."` for what is structurally the same closing-caption role, drifting slightly
different from each other every time. A user who can't name the specific CSS property will still
correctly sense "the subtitles look weirdly offset" — the fix is a shared class, not a closer look
at any one instance.

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
- **A merge-or-split call needs a real redesign attempt, not just arithmetic on the current
  layout.** Measuring two beats' current heights and rejecting a merge because they don't fit
  summed is measuring the wrong thing — a merge redesigned for its own layout (shared heading,
  compacted card padding, smaller secondary text) can land well under budget even when the naive
  sum overflows it. Build the merged version, measure IT, then compare against the split — don't
  reject on the split's own numbers.
- **Formal-deck convention: title + its immediate subtitle line left-justify; body content
  (cards, diagrams) can still center as a balanced block below them.** Owner-directed standard —
  a slide's headline anchors top-left even when everything under it is centered. Scope the CSS to
  the adjacent-sibling case (title block + the line directly after it) so a cover/hero page,
  which has no such heading block, is unaffected and can stay fully centered on its own terms.
- **A sourced "0 of N rivals" claim still needs its own hedge checked**, separately from whether
  it's sourced at all. If the source itself distinguishes *claims* from *demonstrations*
  ("two rivals claim X, none publish a working example of X"), the deck's own wording should
  carry that distinction too — "0 of N do this" overclaims structural absence when the finding is
  really "0 of N show this publicly."
- **Dense per-claim appendices (a collapsed `<details>` full of per-vendor prose, a full cost
  derivation table) can be replaced wholesale by two cheaper mechanisms**: a numbered inline
  citation (`<a href="#ref-N" class="cite">[N]</a>`) pointing to a compact References list at the
  very end (one line per source, not paragraphs), plus a single sentence naming that the full
  backup lives in a companion report shared alongside the deck. This keeps every claim traceable
  without the deck itself carrying the weight of the sourcing — appropriate once a deck is paired
  with real backup material and doesn't need to be self-proving in isolation.
- **A value-case or roadmap idea the owner raises more than once is a signal to change approach,
  not to re-decline with the same reasoning.** The correct response to a repeated ask is usually
  not "no" a second time — it's including the idea with its real evidence tier stated honestly
  (same treatment as any other card: label it draft/speculative if it is, cite what's real), so
  the owner's intent is honored without the deck overclaiming.
