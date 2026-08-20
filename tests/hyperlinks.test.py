#!/usr/bin/env python3
"""What a click in WezTerm actually resolves to — the hyperlink rules in terminal.lua, and the
path resolution in scripts/open-in-editor.sh, checked as one chain.

It exists because the chain fails SILENTLY at every joint: a rule that matches the wrong span
still renders as a link, and a target that resolves to nothing exits 0. Nobody sees a broken
link; they see a click that does nothing. Both halves were broken this way until 2026-08-20 —
repo-relative paths (the shape agent output is full of) matched from their first slash, and the
resolver skipped its root search for anything carrying a directory.

The rules are READ OUT OF terminal.lua rather than restated here, so this cannot pass while the
config says something else.
"""
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
passed = failed = 0


def check(label: str, got, want) -> None:
    global passed, failed
    if got == want:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL {label}: got {got!r}, wanted {want!r}")


def unix_rules() -> list[tuple[str, str]]:
    src = (REPO / "terminal.lua").read_text()
    found = re.findall(r"regex\s*=\s*\[\[(.+?)\]\],\n\s*format\s*=\s*'(\$\d)'", src)
    return [(rx, fmt) for rx, fmt in found if "A-Za-z]:" not in rx]  # the Windows rule is not ours


def link_for(rules, text: str):
    """First matching rule wins, as WezTerm applies them in insertion order."""
    for rx, fmt in rules:
        m = re.search(rx, text)
        if m:
            return m.group(1 if fmt == "$1" else 0)
    return None


def test_spans() -> None:
    rules = unix_rules()
    check("three unix rules present", len(rules), 3)
    for text, want in [
        # the shape that was broken: a repo-relative path must match WHOLE, not from its slash
        ("docs/notes/harness/ORCHESTRATION-MAP.md", "docs/notes/harness/ORCHESTRATION-MAP.md"),
        ("see 4JIM/PROPOSAL.md for the ask", "4JIM/PROPOSAL.md"),
        ("(docs/README.md:12)", "docs/README.md:12"),
        ("~/repo/claudence/terminal.lua", "~/repo/claudence/terminal.lua"),
        ("/Users/me/repo/x/foo.ts:31:4", "/Users/me/repo/x/foo.ts:31:4"),
        ("./scripts/gates.py", "./scripts/gates.py"),
        ("ORCHESTRATION-MAP.md", "ORCHESTRATION-MAP.md"),
        ("create_corporation.rb:31", "create_corporation.rb:31"),
        # prose must not become a dead link — the reason the extension list is an allowlist
        ("read/write access", None), ("TODO: 3/4 done", None), ("and/or", None),
        ("e.g. this", None), ("version 14.13.2 shipped", None),
    ]:
        check(f"span of {text!r}", link_for(rules, text), want)


def test_resolution() -> None:
    """The resolver's own self-check, run as a subprocess — it owns the temp tree it needs."""
    r = subprocess.run([str(REPO / "scripts" / "open-in-editor.sh"), "--selftest"],
                       capture_output=True, text=True)
    check("open-in-editor.sh --selftest exits 0", r.returncode, 0)
    if r.returncode != 0:
        print("    " + r.stdout.strip().replace("\n", "\n    "))


if __name__ == "__main__":
    test_spans()
    test_resolution()
    print(f"{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
