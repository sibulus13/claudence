"""SessionStart context: inject facts instead of instructing Claude to go find them.

- the repo's state doc (first match) and whether it is older than the last commit;
- the repo's deploymentTier (from its CLAUDE.md), or a warning that it is undeclared;
- ledger drafts the nightly job wrote that /ledger has not confirmed yet;
- after a compaction: the standing ask to summarize in-progress work, open states and the next step;
- in a fresh fleet session: the hand-off (NEXT_SESSION.md) and the ledger's latest day, as a banner for the owner
  (systemMessage) and in full for the agent, so neither has to go and read them.
Prints hook JSON; prints nothing when there is nothing to say.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import textwrap
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fleet_paths import fleet_docs_dir  # noqa: E402
from ledger_draft import ledger_has_day  # noqa: E402  (one definition of "the ledger has this day")

STATE_DOCS = ("docs/STATE.md", "STATE.md", "workflow_state.md", "todo.md", "context.md", "docs/KNOWLEDGE.md",
              "ROADMAP.md", "docs/ROADMAP.md")
TIER = re.compile(r"deploymentTier:\s*`?([a-z-]+)", re.I)
BRIEF_SOURCES = ("startup", "clear")  # resume and compact already hold the brief
MAX_CONTEXT_CHARS = 9000  # stays under the 10,000-character limit on hook context
MAX_BANNER_CHANGES = 6
MAX_CHANGE_CHARS = 90


def repo_root(cwd: str) -> Path | None:
    r = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10)
    return Path(r.stdout.strip()) if r.returncode == 0 else None


def last_commit_epoch(root: Path) -> int:
    r = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%ct"], capture_output=True, text=True,
                       timeout=10)
    return int(r.stdout.strip() or 0)


def pending_drafts(drafts_dir: Path | None = None, ledger_file: Path | None = None) -> list[str]:
    """Draft days the ledger does not have a row for yet (a draft whose day is already curated is stale)."""
    drafts_dir = drafts_dir or fleet_docs_dir() / "drafts"
    ledger_file = ledger_file or fleet_docs_dir() / "LEDGER.md"
    if not drafts_dir.is_dir():
        return []
    ledger = ledger_file.read_text(encoding="utf-8", errors="replace") if ledger_file.exists() else ""
    # Only <YYYY-MM-DD>.md is a draft; a stray note or an edited copy must never break session start.
    days = (p.stem for p in drafts_dir.glob("*.md") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.stem))
    return sorted(d for d in days if not ledger_has_day(ledger, date.fromisoformat(d)))


def lines_for(cwd: str, source: str, drafts_dir: Path | None = None, ledger_file: Path | None = None) -> list[str]:
    out = []
    pending = pending_drafts(drafts_dir, ledger_file)
    if pending:
        out.append(f"ledger draft for {', '.join(pending)} pending: run /ledger to curate it into LEDGER.md.")
    root = repo_root(cwd)
    if root is None:
        out.append("Fleet session (not inside a repo): project hooks and memory arrive via the D:/repo router "
                   "on first touch of a project.")
    else:
        doc = next((root / d for d in STATE_DOCS if (root / d).exists()), None)
        if doc:
            stale = doc.stat().st_mtime < last_commit_epoch(root) - 86400
            out.append(f"State doc: {doc.as_posix()}{' (older than the last commit by >1 day: spot-check it)' if stale else ''}. "
                       "Read it before changing code.")
        else:
            out.append(f"No state doc in {root.as_posix()}: that is itself a finding.")
        claude_md = root / "CLAUDE.md"
        m = TIER.search(claude_md.read_text(encoding="utf-8", errors="replace")) if claude_md.exists() else None
        out.append(f"deploymentTier: {m.group(1)}" if m else "deploymentTier: undeclared (treat as pre-traffic; declare it).")
    if source == "compact":
        out.append("After compaction: first summarize what was in progress, any temporary states left in place, "
                   "and the next concrete step.")
    return out


def is_fleet_session(cwd: str, docs: Path) -> bool:
    """True in the fleet docs repo, or in a non-repo folder of the fleet tree (D:/repo itself, a theme folder)."""
    root = repo_root(cwd)
    if root is not None:
        return root.resolve() == docs.resolve()
    return Path(cwd).resolve().is_relative_to(docs.resolve().parent)


def section(text: str, heading: str) -> str:
    """The body of a `## heading` section; empty when the doc has no such section."""
    m = re.search(rf"^## {re.escape(heading)}[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def table_rows(text: str) -> list[list[str]]:
    """Body rows of the markdown tables in `text`, as stripped cells; header and rule rows dropped."""
    lines = text.splitlines()
    return [[c.strip() for c in line.strip().strip("|").split("|")] for i, line in enumerate(lines)
            if line.startswith("|") and not line.startswith("|-")
            and not (i + 1 < len(lines) and lines[i + 1].startswith("|-"))]


def latest_day(ledger: str) -> tuple[str, str] | None:
    """(heading, body) of the newest day in the ledger: days are listed newest first."""
    m = re.search(r"^### (\d{4}-\d{2}-\d{2}[^\n]*)\n(.*?)(?=^### |\Z)", section(ledger, "Days"), re.M | re.S)
    return (m.group(1), m.group(2)) if m else None


def banner_for(hand_off: str, day: tuple[str, str] | None, path: Path) -> str:
    written = re.search(r"\(written ([\d-]+)\)", hand_off)
    out = [f"Hand-off{f', written {written.group(1)}' if written else ''} (full: {path.as_posix()})"]
    if day:
        heading, body = day
        out.append(f"Last session, {heading}:")
        changes = [r for r in table_rows(body) if len(r) >= 2]
        out += [f"- {r[0]}: {textwrap.shorten(r[1].split(';')[0], MAX_CHANGE_CHARS, placeholder='...')}"
                for r in changes[:MAX_BANNER_CHANGES]]
        if len(changes) > MAX_BANNER_CHANGES:
            out.append(f"- +{len(changes) - MAX_BANNER_CHANGES} more")
        incidents = re.search(r"\*\*Incidents\*\*\n((?:- .*\n?)+)", body)
        if incidents:
            out.append(f"Incidents: {len(incidents.group(1).strip().splitlines())}")
    checks = table_rows(section(hand_off, "Check first"))
    if checks:
        now = sum(r[0] == "Now" for r in checks)
        dated = next((r[0] for r in checks if r[0] != "Now"), None)
        out.append(f"Check first: {now} now" + (f"; next {dated}" if dated else ""))
    first = re.search(r"^1\. \*\*(.+?)\*\*", section(hand_off, "Pick up, in order"), re.M)
    if first:
        out.append(f"Pick up: {first.group(1)}")
    owner = re.findall(r"^- \*\*(.+?)\*\*", section(hand_off, "Needs the owner"), re.M)
    out.append(f"Needs you: {'; '.join(owner) if owner else 'nothing'}")
    return "\n".join(out)


def handoff(cwd: str, source: str, docs: Path | None = None) -> tuple[str, str] | None:
    """(banner for the owner, context for the agent) in a fresh fleet session; None anywhere else."""
    docs = docs or fleet_docs_dir()
    if source not in BRIEF_SOURCES or not is_fleet_session(cwd, docs):
        return None
    path = docs / "NEXT_SESSION.md"
    if not path.exists():
        missing = f"NEXT_SESSION.md missing at {path.as_posix()}: the last session left no hand-off."
        return missing, missing
    hand_off = path.read_text(encoding="utf-8", errors="replace")
    ledger_file = docs / "LEDGER.md"
    day = latest_day(ledger_file.read_text(encoding="utf-8", errors="replace")) if ledger_file.exists() else None
    context = re.sub(r"```mermaid.*?```\n*", "", hand_off, flags=re.S)
    if day:
        context += f"\n# Ledger, {day[0]}\n{day[1]}"
    if len(context) > MAX_CONTEXT_CHARS:
        cut = f"\n[cut at {MAX_CONTEXT_CHARS} characters; read {path.as_posix()}]"
        context = context[:MAX_CONTEXT_CHARS - len(cut)] + cut
    return banner_for(hand_off, day, path), context


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    cwd, source = event.get("cwd") or ".", event.get("source") or "startup"
    lines = lines_for(cwd, source)
    brief = handoff(cwd, source)
    payload: dict = {}
    if brief:
        lines.append(brief[1])
        payload["systemMessage"] = brief[0]
    if lines:
        payload["hookSpecificOutput"] = {"hookEventName": "SessionStart", "additionalContext": "\n".join(lines)}
    if payload:
        print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
