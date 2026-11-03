"""Shared helpers for tests that lock or ship a work item: stage a fresh review record through the real writer.

Work item: docs/work/review-records. Since the gate demands a fresh `pass` record at the lock and ship moves, every test
that makes such a move stages one with `stage_record` first. The record is written by `review_record.py write` itself, so
the helper cannot drift from the format the gate reads.
"""
from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

CLAUDE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLAUDE / "scripts"))
ITEM = "docs/work/demo"


def review_record():
    return importlib.import_module("review_record")


def spec_check():
    return importlib.import_module("spec_check")


def good_report(content: str, verdict: str = "pass", commit: str | None = None) -> str:
    """A reviewer report in the shape `write` accepts: the echoed brief lines, a finding line, the verdict last."""
    lines = ["REVIEW: demo", "", f"REVIEWED: {content}"]
    if commit:
        lines.append(f"REVIEWED-COMMIT: {commit}")
    return "\n".join([*lines, "", "No findings.", "", f"VERDICT: {verdict}", ""])


def item_hash(repo: Path, item: str = ITEM) -> str:
    return review_record().content_hash(spec_check().IndexTree(repo), item)


def head_sha(repo: Path) -> str:
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()


def stage_record(repo: Path, kind: str = "design", *, verdict: str = "pass", item: str = ITEM,
                 reviewer: str = "reviewer agent a1b2") -> str:
    """Stage the item, write a record of `kind` for its staged content, stage the record; return its repo path."""
    subprocess.run(["git", "-C", str(repo), "add", "-A", item], check=True, capture_output=True)
    commit = head_sha(repo) if kind == "code" else None
    report = repo.parent / f"report-{kind}-{verdict}.md"
    report.write_text(good_report(item_hash(repo, item), verdict, commit), encoding="utf-8", newline="\n")
    out = subprocess.run([sys.executable, str(CLAUDE / "scripts" / "review_record.py"), "write", "--item", item,
                          "--kind", kind, "--reviewer", reviewer, "--report", str(report), "--root", str(repo)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    path = out.stdout.strip()
    subprocess.run(["git", "-C", str(repo), "add", "--", path], check=True, capture_output=True)
    return path
