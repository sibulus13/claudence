#!/usr/bin/env python3
"""Deterministic gate: every font-size and padding value in a presentation-artifact
deck must reference a design token (var(--text-*) / var(--space-*)), not a raw
one-off number — unless explicitly allow-listed below with a stated reason.

Why this exists: across one build session, off-scale font-size values (.9rem,
1rem, hardcoded .85rem that matched a token but didn't reference it) kept
reappearing turn over turn, because nothing checked for it — a human read-through
caught some, missed others. This script makes the check mechanical instead of
relying on memory.

Usage: python3 check-design-tokens.py [--profile deck|report] <file.html>
Profile defaults to "deck" (var(--text-*) tokens) when omitted. Pass
"--profile report" for a report-artifact file (var(--r-text-*) tokens) — see
PROFILES below and the report-artifact skill for what that profile allows.
Exit 0 = clean. Exit 1 = at least one un-allow-listed raw value found, printed
with its line number and content so it can be fixed or explicitly allow-listed.

Scope, deliberately: content OUTSIDE a collapsed <details> block must use a
token. Content INSIDE one (reference-tier, read once, up close) may use a raw
value without tripping the gate — but grep the output either way; if a
<details> block is drifting off-scale too, that's still worth knowing.
"""
import re
import sys

# Two profiles share this one script rather than forking a second copy — the check (every
# font-size resolves to a token or a reasoned exception) is identical; only the token prefix
# and the allow-list of deliberate raw values differ per artifact shape. See report-artifact's
# SKILL.md for why the report profile is px-based (--r-text-*) while the deck is rem-based
# (--text-*): the report never set a custom `html` font-size, so rem there would silently
# scale off the browser default, not off the report's own 17px body — the same rem-is-root-
# relative trap presentation-artifact's own SKILL.md documents hitting once already.
PROFILES = {
    "deck": {
        "token_prefix": "var(--text-",
        "allowlist": {
            "19px": "body base font-size — the root unit every rem token scales FROM, not itself reading content",
            ".68rem": "rail nav-dot UI chrome, shrunk from .8rem when a deck grew past ~10 sections — tiny circular buttons, not reading content",
            ".75rem": "collapsed-detail table header, reference-tier text — exempt, smaller than the floor on purpose",
            "1.9rem": "cost-step big stat number — a display figure, not body/caption text, not on the small-text scale",
            "1.4rem": "prev/next stepper chevron icon size — an icon, not body text",
            "1.8rem": "hero-meta stat value — a display figure, deliberately bigger than --text-md so it reads as a headline number",
            "clamp(2rem, 3.4vw, 3.1rem)": "h2 — a responsive display heading, not on the small-text scale",
            "clamp(2.8rem, 6.5vw, 5.2rem)": "hero h1 — a responsive display heading, not on the small-text scale",
            "2rem": "hero lede — a deliberately larger opening statement, bigger than --text-sm on purpose",
            "1.6rem": "lede — a deliberately larger intro line, bigger than --text-sm on purpose",
            "2.2rem": "closing-beat prompt line — a deliberately large one-off call-to-action, bigger than any card heading",
            "1.5rem": "closing-beat response pills (Approve/Redirect/Pivot) — deliberately oversized touch-target-style pills, not ordinary body pills",
        },
    },
    "report": {
        "token_prefix": "var(--r-text-",
        "allowlist": {
            "clamp(30px,5vw,50px)": "h1 — a responsive display heading, not on the small-text scale",
            "clamp(23px,3vw,31px)": "h2.sh — section headline, a responsive display heading",
            "clamp(19px,2.2vw,23px)": "recommendation-cell big stat number — a display figure, not body/caption text",
            "clamp(17px,2vw,20px)": "the dek (subtitle under h1) — a responsive display line, bigger than any body token on purpose",
        },
    },
}

# Back-compat module-level names — existing callers (and the selftest below) that import
# ALLOWLIST/TOKEN_PREFIX directly keep working against the deck profile, the original default.
ALLOWLIST = PROFILES["deck"]["allowlist"]
TOKEN_PREFIX = PROFILES["deck"]["token_prefix"]

# Raw SVG font-size="N" attributes are a distinct check from CSS font-size — SVG text isn't on
# the rem-based token scale, it's viewBox px scaled by the diagram's own rendered width, so there
# is no var(--text-*) to point it at. Instead: a floor, in raw attribute px. Below this, text in
# a diagram meant to be read (not a collapsed appendix) is illegible on a big screen at typical
# render scale — closed 2026-08-31 after finding un-caught 9px/10px SVG labels in a shipped deck.
SVG_FONT_SIZE_FLOOR = 11


def find_details_ranges(text):
    """Return a list of (start_offset, end_offset) for every <details>...</details> block."""
    ranges = []
    for m in re.finditer(r"<details\b.*?</details>", text, re.DOTALL | re.IGNORECASE):
        ranges.append((m.start(), m.end()))
    return ranges


def in_any_range(pos, ranges):
    return any(start <= pos < end for start, end in ranges)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--profile")]
    profile_name = "deck"
    for a in sys.argv[1:]:
        if a.startswith("--profile="):
            profile_name = a.split("=", 1)[1]
    if "--profile" in sys.argv:
        idx = sys.argv.index("--profile")
        if idx + 1 < len(sys.argv):
            profile_name = sys.argv[idx + 1]
            args = [a for a in args if a != sys.argv[idx + 1]]

    if profile_name not in PROFILES:
        print("unknown --profile %r — choices: %s" % (profile_name, ", ".join(PROFILES)), file=sys.stderr)
        sys.exit(2)
    if len(args) != 1:
        print("usage: check-design-tokens.py [--profile deck|report] <file.html>", file=sys.stderr)
        sys.exit(2)

    profile = PROFILES[profile_name]
    token_prefix = profile["token_prefix"]
    allowlist = profile["allowlist"]

    path = args[0]
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    details_ranges = find_details_ranges(text)
    lines = text.split("\n")
    line_starts = []
    offset = 0
    for line in lines:
        line_starts.append(offset)
        offset += len(line) + 1

    def line_number_for(pos):
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    violations = []
    for m in re.finditer(r"font-size:\s*([^;\"']+)", text):
        value = m.group(1).strip()
        pos = m.start()
        if value.startswith(token_prefix):
            continue
        if value in allowlist:
            continue
        if in_any_range(pos, details_ranges):
            continue  # collapsed reference tier — exempt from the strict gate, not silently ignored
        violations.append((line_number_for(pos), "font-size", value))

    svg_violations = []
    for m in re.finditer(r'font-size="(\d+(?:\.\d+)?)"', text):
        value = float(m.group(1))
        pos = m.start()
        if value >= SVG_FONT_SIZE_FLOOR:
            continue
        if in_any_range(pos, details_ranges):
            continue  # collapsed reference tier — exempt, same as the CSS check
        svg_violations.append((line_number_for(pos), m.group(1)))

    if violations or svg_violations:
        if violations:
            print(f"FAIL — {len(violations)} un-tokenized CSS font-size value(s):")
            for ln, prop, val in violations:
                print(f"  line {ln}: {prop}: {val}  (not a var(--text-*) token, not allow-listed)")
        if svg_violations:
            print(f"FAIL — {len(svg_violations)} SVG font-size attribute(s) under the {SVG_FONT_SIZE_FLOOR}px floor:")
            for ln, val in svg_violations:
                print(f"  line {ln}: font-size=\"{val}\"  (below {SVG_FONT_SIZE_FLOOR}px, outside a <details>)")
        print("\nFix: use a var(--text-*) token for CSS, raise SVG font-size attributes to at")
        print(f"least {SVG_FONT_SIZE_FLOOR}px (or move the text into a collapsed <details>) — never")
        print("silence by widening the regex or lowering the floor to match what's already there.")
        sys.exit(1)

    print(f"OK — every font-size in {path} is a token or an explicit, reasoned exception.")
    sys.exit(0)


def _selftest():
    """Minimal runnable check: an off-scale value fails, a token and an allow-listed
    value pass, and a value inside <details> is exempt. Run with --selftest."""
    import tempfile, os
    sample = (
        '<p style="font-size:.85rem">a</p>'
        '<p style="font-size:var(--text-xs)">b</p>'
        '<p style="font-size:.68rem">c</p>'  # allow-listed
        '<details><p style="font-size:.63rem">d</p></details>'
        '<svg><text font-size="9">e</text></svg>'
        '<svg><text font-size="13">f</text></svg>'
        '<details><svg><text font-size="9">g</text></svg></details>'
    )
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(sample)
        tmp_path = f.name
    try:
        with open(tmp_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        details_ranges = find_details_ranges(text)
        offs = [m.start() for m in re.finditer(r"font-size:\s*([^;\"']+)", text)]
        vals = [m.group(1).strip() for m in re.finditer(r"font-size:\s*([^;\"']+)", text)]
        # a: .85rem, not token, not allow-listed, not in <details> -> should be flagged
        assert vals[0] == ".85rem" and not in_any_range(offs[0], details_ranges)
        # b: token -> exempt
        assert vals[1].startswith(TOKEN_PREFIX)
        # c: allow-listed
        assert vals[2] in ALLOWLIST
        # d: inside <details> -> exempt regardless of value
        assert in_any_range(offs[3], details_ranges)
        # e/f/g: SVG font-size — e (9, visible) flagged, f (13, visible) exempt, g (9, in <details>) exempt
        svg_offs = [m.start() for m in re.finditer(r'font-size="(\d+(?:\.\d+)?)"', text)]
        svg_vals = [float(m.group(1)) for m in re.finditer(r'font-size="(\d+(?:\.\d+)?)"', text)]
        assert svg_vals[0] == 9 and svg_vals[0] < SVG_FONT_SIZE_FLOOR and not in_any_range(svg_offs[0], details_ranges)
        assert svg_vals[1] == 13 and svg_vals[1] >= SVG_FONT_SIZE_FLOOR
        assert svg_vals[2] == 9 and in_any_range(svg_offs[2], details_ranges)
        print("selftest OK")
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        _selftest()
        sys.exit(0)
    main()
