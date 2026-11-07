"""SessionStart context: the pending-ledger-draft line.

    python -m pytest ~/.claude/tests/test_session_context.py -q
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
import session_context as sc  # noqa: E402


def test_pending_drafts_are_named_by_date(tmp_path: Path):
    (tmp_path / "2026-10-28.md").write_text("x", encoding="utf-8")
    (tmp_path / "2026-10-27.md").write_text("x", encoding="utf-8")
    (tmp_path / "note.txt").write_text("x", encoding="utf-8")
    lines = sc.lines_for(str(tmp_path), "startup", drafts_dir=tmp_path, ledger_file=tmp_path / "none.md")
    assert lines[0] == "ledger draft for 2026-10-27, 2026-10-28 pending: run /ledger to curate it into LEDGER.md."


def test_a_draft_whose_day_is_already_in_the_ledger_is_not_pending(tmp_path: Path):
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    (drafts / "2026-10-28.md").write_text("x", encoding="utf-8")
    (drafts / "2026-10-27.md").write_text("x", encoding="utf-8")
    ledger = tmp_path / "LEDGER.md"
    ledger.write_text("### 2026-10-28 (Wed)", encoding="utf-8")  # heading at EOF, no newline
    assert sc.pending_drafts(drafts, ledger) == ["2026-10-27"]


def test_non_date_markdown_in_drafts_is_ignored(tmp_path: Path):
    for name in ("notes.md", "2026-10-29.bak.md", "2026-10-29-edit.md", "2026-10-27.md"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert sc.pending_drafts(tmp_path, tmp_path / "none.md") == ["2026-10-27"]


def test_no_drafts_dir_or_empty_dir_says_nothing_about_the_ledger(tmp_path: Path):
    assert not any("ledger draft" in line for line in sc.lines_for(str(tmp_path), "startup", drafts_dir=tmp_path))
    assert not any("ledger draft" in line for line in sc.lines_for(str(tmp_path), "startup", drafts_dir=tmp_path / "x"))


def test_default_drafts_and_ledger_come_from_fleet_docs(tmp_path: Path, monkeypatch):
    """fleet-docs-home/AC-5: with no explicit paths the drafts dir and ledger are read under FLEET_DOCS."""
    (tmp_path / "drafts").mkdir()
    (tmp_path / "drafts" / "2026-10-27.md").write_text("x", encoding="utf-8")
    (tmp_path / "drafts" / "2026-10-28.md").write_text("x", encoding="utf-8")
    (tmp_path / "LEDGER.md").write_text("### 2026-10-28 (Wed)\n", encoding="utf-8")
    monkeypatch.setenv("FLEET_DOCS", str(tmp_path))
    assert sc.pending_drafts() == ["2026-10-27"]


NEXT = """# Next session (written 2026-11-07)

```mermaid
flowchart TD
  A[Read this file] --> B[Check]
```

## Check first

| When | What | Pass looks like | If not |
|---|---|---|---|
| Now | Foreman's first run | It opens a PR | Read the logs |
| Now | Hub on 0.4.0 | Messages arrive | Check the hub |
| Sun Nov 8, 07:30 | EA's first run | Brief arrives | Read its report |

## Pick up, in order

1. **Cortex PR #12** (dates in the owner's local day): fix round.
2. **Close stale items**: issues.

## Needs the owner

- **TeleFi 0.4.0 on PyPI**: tagging publishes it.
- **Meter's public history** carries the email.
"""

LEDGER = """# Fleet ledger

### Not a day heading

## Days

### 2026-11-07 (Sat)
| project | change | why | ref | kind |
|---|---|---|---|---|
| TeleFi | Public repo became the only home; 0.4.0 landed | Drift | abc | move |
| Foreman | All 11 repos pinned to PR-only | Tier default | repos.json | fix |

**Incidents**
- Foreman merged five PRs itself.
- A real result nearly went public.

**Watch**: see `NEXT_SESSION.md`.

### 2026-11-06 (Fri)
| project | change | why | ref | kind |
|---|---|---|---|---|
| Crucible | Older day must not show | x | y | feat |
"""


def fleet_docs(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "NEXT_SESSION.md").write_text(NEXT, encoding="utf-8")
    (docs / "LEDGER.md").write_text(LEDGER, encoding="utf-8")
    return docs


def test_fleet_session_startup_shows_the_banner_to_the_owner(tmp_path: Path):
    """session-handoff-brief/AC-1: the banner carries last session, checks, next pick-up and owner items."""
    banner, _ = sc.handoff(str(tmp_path), "startup", fleet_docs(tmp_path))
    assert "Last session, 2026-11-07 (Sat)" in banner
    assert "- TeleFi: Public repo became the only home" in banner
    assert "- Foreman: All 11 repos pinned to PR-only" in banner
    assert "Incidents: 2" in banner
    assert "Check first: 2 now; next Sun Nov 8, 07:30" in banner
    assert "Pick up: Cortex PR #12" in banner
    assert "Needs you: TeleFi 0.4.0 on PyPI; Meter's public history" in banner
    assert "Older day" not in banner


def test_the_agent_gets_the_hand_off_and_last_day_without_the_diagram(tmp_path: Path):
    """session-handoff-brief/AC-2: the agent needs no Read of either doc."""
    _, context = sc.handoff(str(tmp_path), "startup", fleet_docs(tmp_path))
    assert "| Now | Foreman's first run | It opens a PR | Read the logs |" in context
    assert "A real result nearly went public" in context
    assert "mermaid" not in context
    assert "Older day" not in context


def test_a_long_hand_off_is_cut_and_says_where_the_rest_is(tmp_path: Path):
    """session-handoff-brief/AC-2: context stays under the cap, and the cut is named."""
    docs = fleet_docs(tmp_path)
    (docs / "NEXT_SESSION.md").write_text(NEXT + "x" * sc.MAX_CONTEXT_CHARS, encoding="utf-8")
    _, context = sc.handoff(str(tmp_path), "startup", docs)
    assert len(context) <= sc.MAX_CONTEXT_CHARS
    assert "cut at" in context and "NEXT_SESSION.md" in context


def test_many_changes_collapse_to_a_count(tmp_path: Path):
    docs = fleet_docs(tmp_path)
    rows = "".join(f"| P{i} | Change {i} | w | r | k |\n" for i in range(sc.MAX_BANNER_CHANGES + 3))
    (docs / "LEDGER.md").write_text(f"## Days\n\n### 2026-11-07 (Sat)\n| project | change | why | ref | kind |\n|---|---|---|---|---|\n{rows}",
                                    encoding="utf-8")
    banner, _ = sc.handoff(str(tmp_path), "startup", docs)
    assert f"- P{sc.MAX_BANNER_CHANGES - 1}: Change" in banner
    assert f"- P{sc.MAX_BANNER_CHANGES}: Change" not in banner
    assert "+3 more" in banner


def test_a_missing_hand_off_is_named_not_silent(tmp_path: Path):
    """session-handoff-brief/AC-3."""
    docs = tmp_path / "docs"
    docs.mkdir()
    banner, context = sc.handoff(str(tmp_path), "startup", docs)
    assert "NEXT_SESSION.md missing" in banner
    assert "NEXT_SESSION.md missing" in context


def test_a_ledger_without_days_still_gives_the_hand_off(tmp_path: Path):
    docs = fleet_docs(tmp_path)
    (docs / "LEDGER.md").write_text("# Fleet ledger\n", encoding="utf-8")
    banner, _ = sc.handoff(str(tmp_path), "startup", docs)
    assert "Last session" not in banner
    assert "Pick up: Cortex PR #12" in banner


def test_only_a_fresh_conversation_gets_the_brief(tmp_path: Path):
    """session-handoff-brief/AC-4: resume and compact already hold it."""
    docs = fleet_docs(tmp_path)
    assert sc.handoff(str(tmp_path), "clear", docs) is not None
    assert sc.handoff(str(tmp_path), "resume", docs) is None
    assert sc.handoff(str(tmp_path), "compact", docs) is None


def test_a_project_repo_session_gets_no_brief(tmp_path: Path, monkeypatch):
    """session-handoff-brief/AC-4: a project repo has its own state doc."""
    docs = fleet_docs(tmp_path)
    repo = tmp_path / "Theme" / "project"
    repo.mkdir(parents=True)
    monkeypatch.setattr(sc, "repo_root", lambda cwd: repo)
    assert sc.handoff(str(repo), "startup", docs) is None


def test_the_docs_repo_itself_is_a_fleet_session(tmp_path: Path, monkeypatch):
    docs = fleet_docs(tmp_path)
    monkeypatch.setattr(sc, "repo_root", lambda cwd: docs)
    assert sc.handoff(str(docs), "startup", docs) is not None


def test_a_folder_outside_the_fleet_gets_no_brief(tmp_path: Path):
    fleet = tmp_path / "fleet"
    fleet.mkdir()
    docs = fleet_docs(fleet)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    assert sc.handoff(str(outside), "startup", docs) is None


def test_hook_output_is_the_session_start_contract(tmp_path: Path, monkeypatch, capsys):
    """session-handoff-brief/AC-5: top-level systemMessage for the owner, additionalContext for the agent."""
    docs = fleet_docs(tmp_path)
    monkeypatch.setenv("FLEET_DOCS", str(docs))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"cwd": str(tmp_path), "source": "startup"})))
    assert sc.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert "Pick up: Cortex PR #12" in out["systemMessage"]
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "Fleet session (not inside a repo)" in out["hookSpecificOutput"]["additionalContext"]
    assert "| Now | Hub on 0.4.0 |" in out["hookSpecificOutput"]["additionalContext"]


ROADMAP = """## Roadmap (as of 2026-11-07)

### Ranked queue (one list, highest first)
| # | item | why this rank | exit condition |
|---|---|---|---|
""" + "".join(f"| {i} | Roadmap item {i} {'w' * 300} | why | exit |\n" for i in range(8)) + """
### Now
- detail
"""


def test_session_roadmap_AC_1_the_top_of_the_roadmap_opens_the_context_even_when_cut(tmp_path: Path):
    """session-roadmap/AC-1"""
    docs = fleet_docs(tmp_path)
    (docs / "LEDGER.md").write_text(ROADMAP + LEDGER, encoding="utf-8")
    (docs / "NEXT_SESSION.md").write_text(NEXT + "x" * sc.MAX_CONTEXT_CHARS, encoding="utf-8")
    _, context = sc.handoff(str(tmp_path), "startup", docs)
    head = context[:2000]
    assert all(f"#{i} Roadmap item {i}" in head for i in range(6))
    assert "Roadmap item 6" not in context
    assert len(context) <= sc.MAX_CONTEXT_CHARS


def test_session_roadmap_AC_2_no_ranked_queue_leaves_the_context_as_before(tmp_path: Path):
    """session-roadmap/AC-2"""
    _, context = sc.handoff(str(tmp_path), "startup", fleet_docs(tmp_path))
    assert "Roadmap" not in context
    assert context.startswith(NEXT[:40].split("```")[0][:20])
