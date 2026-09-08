---
name: report-artifact
description: Build or audit a long-scroll, single-column HTML report artifact (a companion to a pitch deck, a comprehensive backing document, a reference the reader scrolls and reads up close) — every claim sourced, tiered, and collapsible. Use when asked for a "report", "full case", "backing document", or companion to a presentation-artifact deck, rather than a beat-paced slide-shaped page. Extracted 2026-08-31 from the first real report built this way, after its type scale was found to have never been tokenized at all.
version: 1.0.0
---

# /report-artifact

A companion to `presentation-artifact`, for the other artifact shape that pairs with a deck.
**Load `artifact-design` first** for the structural/visual craft (typography, palette, layout) —
this skill is specifically the report's own **component vocabulary**, **type scale**, and the
**verification steps** that catch what a screenshot alone won't.

## Why this is a separate skill, not a section of presentation-artifact

A deck is beat-paced — one `min-height:100vh` section per idea, read from across a room or a
big screen, scroll-snapped, nav-rail synced. A report is **read up close, scrolled continuously,
by one person deciding whether to trust a number.** Nearly every presentation-artifact
verification step assumes the beat/100vh shape and does not apply here (nav-rail sync, per-beat
height budget, viewport utilization). The parts that DO carry over — charset, SVG fill defaults,
horizontal overflow, the design-token gate — are named below, not re-derived.

## Shape

- **Single column, sequential sections**, each `<section>` a `snum` + `sbody` grid row — no
  paging, no `100vh` sections, no nav-rail dots. A sticky table-of-contents (`#toc`) tracks scroll
  position instead.
- **Every load-bearing claim is a finding block** (`.asm`): a headline (`<h4>`), a compact value
  line (`.v`, monospace), and a collapsed `<details class="asmd">` holding the source and the
  caveat. The headline and value line are always visible; the reasoning is one click away, not
  hidden entirely and not forced onto the page.
- **Every finding carries a tier badge** (`<span class="tr a|b|c">`) — the report's own epistemic
  register, not decoration: tier A/B/C means *what kind of evidence this is* (verbatim/measured
  vs. self-authored vs. speculative), stated once in a `.tierlegend` near the top and then reused
  inline on every citation. **Never state a number without its tier** — an unbadged figure reads
  as tier-A confidence by default, which overclaims anything weaker.
- **Dense reference material collapses**: a full per-vendor teardown, a derivation appendix, an
  every-comment-addressed tracker — `<details class="grp">`, closed by default, never deleted to
  "keep it short." The report's whole value proposition is *comprehensive AND scannable*; collapse
  is how it gets both instead of picking one.
- **Every number that appears more than once, or that the deck also states, needs a citation**
  (`<a href="#ref-N" class="cite">[N]</a>`) resolving to a `.asm` block or the closing sources
  list — this is the report's actual job: being the backlink target a deck's own citations point
  to. See `cross-check-entity-claims-not-just-structure` (project memory) for the failure mode
  this exists to prevent — a claim ported between deck and report drifting from itself.
- **Tables** (`<div class="tw"><table>...`) for genuinely tabular data (3+ comparable numeric
  columns); **`.asm` blocks** for everything else. Don't reach for a table just because a `.card`
  grid feels informal — a report is not a deck, formality is the house style, but a table with one
  column of labels and one of values is still the wrong tool.
- **Derivations get their own closing section** (`.der` blocks, `<dl>` term/definition pairs) —
  every formula spelled out with the actual numbers plugged in, not just the named constant and
  its result. A reader auditing a cost or concurrency figure should be able to redo the arithmetic
  from what's on the page, without re-deriving where a variable's value came from.

## The type scale — px-based, and that's a deliberate choice, not an oversight

**presentation-artifact's deck tokens are `rem`, scaled off a `body { font-size: 19px }` reset —
this report profile is `px`, and the reason is the trap that skill's own SKILL.md already
documents once**: `rem` is root-relative (the browser's 16px default), not relative to a custom
`body` font-size, unless something explicitly sets `html { font-size: ... }`. A report built
without that reset and tokenized in `rem` anyway would silently scale off 16px while every author
reading the CSS assumes it scales off the report's own body size — the exact false-relationship
bug presentation-artifact hit and fixed by being explicit. `px` sidesteps the trap entirely by
not claiming a relationship that isn't there.

**Found 2026-08-31, building the first report this way**: the report's own CSS had **46 raw,
un-tokenized `font-size` values** — not a stylistic choice, just never audited, because no gate
existed for this shape and `check-design-tokens.py` only knew the deck's `var(--text-*)` prefix.
Sizes had drifted into near-duplicates with no visual reason to differ (11px next to 11.5px next
to 12px, three places meaning "fine print"). The fix was extracting the report's own real scale
from what was actually in use, not importing the deck's:

```css
--r-text-3xs: 10px;    /* tightest mono tags: tier pill, derivation dt-label */
--r-text-2xs: 11px;    /* fine print & mono chrome: eyebrow, stamp, section number, toc, footer,
                           tier-key label, disclosure summary — merges what had drifted across
                           10.5/11/11.5px with no intended distinction */
--r-text-xs: 12.5px;   /* small captions: recommendation-cell subtext, finding source/caveat prose */
--r-text-sm: 13px;     /* secondary reading body: finding value line, toc links, notes, closing
                           sources, tier-legend prose — merges 13/13.5px */
--r-text-table: 14.5px;/* table body — needs to read easily at a glance, not shrunk to caption size */
--r-text-md: 15px;     /* subhead/emphasis: finding headline, derivation headline, disclosure-group
                           summary, recommendation sub-line — merges 15/15.5px */
--r-text-lg: 17px;     /* body base, five-point summary */
--r-text-xl: 18px;     /* claim/emphasis prose */
--r-text-2xl: 20px;    /* recommendation headline prose — the single largest reading sentence */
```

Display headings (`h1`, `h2.sh`, a stat-cell's big number, the subtitle under `h1`) stay off this
scale on purpose, same as the deck's own hero/h2 clamps — allow-listed by name, never folded into
a body-text token just because both are "big."

**When starting a new report**, don't invent a fresh scale from scratch either: read the CSS that
already exists (if forking from a prior report) or draft the content first and let the actual
sizes needed emerge, THEN consolidate near-duplicates into a token set of this shape (~9 tokens:
one tightest-tag floor, 2-3 fine-print/caption tiers, one table-specific size, one subhead tier,
body, and 1-2 emphasis tiers above body) — don't pre-guess the count.

## Verification — before every publish

**Steps 0, 5, 6 from presentation-artifact carry over unchanged** — a report is still an HTML
file with the same charset and SVG-fill failure modes:

- **`<meta charset="utf-8">` must be the first line.** Missed once already on a report built
  alongside a deck that already had it — every em-dash/curly-quote mojibakes without it.
- **Every inline SVG `<text>` needs an explicit `fill`** (or an ancestor `<g fill="...">`) — SVG's
  implicit default is opaque black, invisible in dark theme. `grep -n '<text' report.html | grep -v 'fill='`
  should return nothing.
- **Horizontal overflow**: `document.body.scrollWidth <= window.innerWidth`, checked on a real
  served copy (`python3 -m http.server`), not the sandboxed artifact viewer.
- **SVG shape overflow past its own viewBox — check every shape, not just `<text>`.** Found
  2026-08-31, in a published report: a diagram's 4th box (`<rect x="520" width="150">` in a
  `viewBox="0 0 640 …"`, so its right edge sat at 670 against a 640-wide box) was visibly
  clipped on the right — the owner caught it live, after a text-only check had already run clean.
  The rect's own text happened to stay just inside bounds (`text-anchor="middle"`, so its bbox is
  narrower and centered), which is exactly why a check scoped to `<text>` alone missed a `<rect>`
  overflowing around it. `scrollWidth` will not catch this either — it doesn't see inside SVG
  internals. Check **all four directions, on every shape type**, not just the right edge on text:
  ```js
  const bad = [];
  document.querySelectorAll('svg').forEach(svg => {
    const vb = svg.viewBox.baseVal;
    if (!vb || (vb.width === 0 && vb.height === 0)) return;
    ['rect','circle','line','polygon','text','ellipse'].forEach(tag => {
      svg.querySelectorAll(tag).forEach(el => {
        if (el.hasAttribute('transform')) return; // rotated text: see the note below, screenshot it instead
        let b; try { b = el.getBBox(); } catch(e) { return; }
        if (b.width === 0 && b.height === 0) return;
        const over = Math.max(
          (b.x + b.width) - (vb.x + vb.width),   // right
          (b.y + b.height) - (vb.y + vb.height), // bottom
          vb.x - b.x,                            // left
          vb.y - b.y);                           // top
        if (over > 2) bad.push({ svg: (svg.getAttribute('aria-label')||'').slice(0,40), tag, text: (el.textContent||'').slice(0,25), over: Math.round(over) });
      });
    });
  });
  JSON.stringify(bad);
  ```
  An empty array is the only acceptable result. **A rotated element (`transform="rotate(...)"`)
  reports nonsense here** — same false-positive `getBBox()` returns the pre-rotation box, exactly
  as presentation-artifact's own verification step 9 already documents for rotated `<text>`; this
  check skips anything with a `transform` attribute for that reason and needs a screenshot instead.
  **A fix on one axis can break another** — raising a diagram's SVG `font-size` to clear the 11px
  legibility floor (below) can push that same label past its own box's edge, and widening a box to
  fix a clip can itself now exceed the viewBox. Re-run this full check after ANY geometry or
  font-size change to a diagram, not just after content edits — a text-only check is not a
  substitute, it is a narrower, weaker version of this one and should not be used alone.

**Run the design-token gate with the report profile**, not the deck default:
```sh
python3 ~/.claude/skills/presentation-artifact/check-design-tokens.py --profile report report.html
```
The two profiles share one script (the check is identical; only the token prefix and allow-list
differ) — see `PROFILES` in that file. Omitting `--profile` defaults to the deck profile and will
falsely flag every `--r-text-*` value as unrecognized.

**SVG `font-size` floor is 11px, shared with the deck profile** — same reasoning, same number:
text in a diagram meant to be read is illegible below it at normal render scale. Content inside a
collapsed `<details>` is exempt, same as the deck.

**What does NOT carry over from presentation-artifact**, because the shape doesn't have it:
nav-rail dot sync, per-beat `100vh` height budget, viewport height/width utilization percentages,
the scroll-is-broken-in-the-artifact-viewer debug-copy workaround (a report has no `min-height:
100vh` sections to unwrap — scrolling a normal document works fine in the sandboxed viewer).

## Cross-document integrity — the report's real job

**A report existing alongside a deck is not "the same content, more of it" — it's the backlink
target.** Two checks specific to this pairing, not covered by presentation-artifact:

- **Every citation the deck makes (`<a href="#ref-N" class="cite">`) must resolve to a real
  anchor in the report** (`id="ref-N"`), and that anchor's content must say the SAME thing the
  deck claims — not just exist. `grep -oE '#ref-[0-9]+' deck.html | sort -u` against
  `grep -oE 'id="ref-[0-9]+"' report.html | sort -u` catches a missing anchor; it does NOT catch a
  present-but-contradicting one — read both sides for every shared figure, don't just confirm the
  link resolves.
- **A deck beat with no citation at all is a finding, not a formality** — if the deck shows a
  concrete worked example or a capability demonstration and the report never mentions it, the
  report has failed its own "comprehensive and self-contained" claim regardless of how complete
  everything else is. `grep -c 'class="cite"' deck.html`, then check that count against the
  deck's own beat count — a beat with zero citations is worth reading closely, not assuming
  covered by inference.

## Content discipline

- **State every formula in the terms a reader would use, with the actual numbers plugged in** —
  a named constant and its result is not the same as showing where each input came from. A cost
  or concurrency derivation should let a skeptical reader redo the arithmetic from the page alone.
- **A concurrency or scaling figure needs one explicit question answered before it's trusted**:
  always-on or auto-scaled/burst? Modeling burst-only infrastructure at a flat always-on annual
  rate can overstate a worst-case cost by 3-4x — a real correctness bug, not a rounding
  difference. State which basis the headline number uses, and give the other basis as a named,
  separate figure rather than silently picking one.
- **Don't let an illustrative example borrow a measured one's confidence.** If a finding's own
  source file marks it `assumed`/`draft`/`self-authored`, its tier badge must say so (tier B or
  C) even if the prose reads confidently — the badge is the signal a skimming reader actually
  uses, and it must not overclaim what the underlying source itself doesn't claim.
