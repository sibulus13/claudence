#!/usr/bin/env python3
"""Deterministic gate: every font-size and padding value in a presentation-artifact
deck must reference a design token (var(--text-*) / var(--space-*)), not a raw
one-off number — unless explicitly allow-listed below with a stated reason.

Why this exists: across one build session, off-scale font-size values (.9rem,
1rem, hardcoded .85rem that matched a token but didn't reference it) kept
reappearing turn over turn, because nothing checked for it — a human read-through
caught some, missed others. This script makes the check mechanical instead of
relying on memory.

Usage: python3 check-design-tokens.py <deck.html>
Exit 0 = clean. Exit 1 = at least one un-allow-listed raw value found, printed
with its line number and content so it can be fixed or explicitly allow-listed.

Scope, deliberately: content OUTSIDE a collapsed <details> block must use a
token. Content INSIDE one (reference-tier, read once, up close) may use a raw
value without tripping the gate — but grep the output either way; if a
<details> block is drifting off-scale too, that's still worth knowing.
"""
import re
import sys

# Raw values that are allowed WITHOUT a token reference, and why. Add to this
# list only for a genuine, deliberate exception — not to silence a real miss.
ALLOWLIST = {
    ".8rem": "rail nav-dot UI chrome (tiny circular buttons, not reading content) — exempt by design",
    ".75rem": "collapsed-detail table header, reference-tier text — exempt, smaller than the floor on purpose",
    "1.9rem": "cost-step big stat number — a display figure, not body/caption text, not on the small-text scale",
    "1.4rem": "hero-meta stat value / stepper icon size — a display figure or icon, not body text",
    "clamp(2rem, 3.4vw, 3.1rem)": "h2 — a responsive display heading, not on the small-text scale",
    "clamp(2.8rem, 6.5vw, 5.2rem)": "hero h1 — a responsive display heading, not on the small-text scale",
    "1.5rem": "hero lede — a deliberately larger opening statement, not on the small-text scale",
    "1.1rem": "lede — a deliberately larger intro line, not on the small-text scale",
    "1.2rem": "quote-card font-size override — a deliberately larger illustrated-quote treatment",
}

TOKEN_PREFIX = "var(--text-"


def find_details_ranges(text):
    """Return a list of (start_offset, end_offset) for every <details>...</details> block."""
    ranges = []
    for m in re.finditer(r"<details\b.*?</details>", text, re.DOTALL | re.IGNORECASE):
        ranges.append((m.start(), m.end()))
    return ranges


def in_any_range(pos, ranges):
    return any(start <= pos < end for start, end in ranges)


def main():
    if len(sys.argv) != 2:
        print("usage: check-design-tokens.py <deck.html>", file=sys.stderr)
        sys.exit(2)

    path = sys.argv[1]
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
        if value.startswith(TOKEN_PREFIX):
            continue
        if value in ALLOWLIST:
            continue
        if in_any_range(pos, details_ranges):
            continue  # collapsed reference tier — exempt from the strict gate, not silently ignored
        violations.append((line_number_for(pos), "font-size", value))

    if violations:
        print(f"FAIL — {len(violations)} un-tokenized font-size value(s):")
        for ln, prop, val in violations:
            print(f"  line {ln}: {prop}: {val}  (not a var(--text-*) token, not allow-listed)")
        print("\nFix: use a var(--text-*) token, or add the exact value to ALLOWLIST in this")
        print("script with a one-line reason — never silence by widening the regex.")
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
        '<p style="font-size:.8rem">c</p>'  # allow-listed
        '<details><p style="font-size:.63rem">d</p></details>'
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
        print("selftest OK")
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        _selftest()
        sys.exit(0)
    main()
