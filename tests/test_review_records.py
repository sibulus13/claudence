"""Acceptance tests for review records (spec: docs/work/review-records, AC-1..AC-15).

Real git repos in temp dirs and the real commit-msg hook (core.hooksPath), as tests/test_spec_gate.py does. The record
writer runs in-process (so the clock can be set) or as a real CLI process where the process boundary is the point.

    python -m pytest ~/.claude/tests/test_review_records.py -q
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from review_helpers import good_report, head_sha, item_hash, review_record as rr, spec_check as sc
from test_spec_gate import CLAUDE, ENV, GATE, README_REL, commit, git, repo2, seed_status, set_status, write  # noqa: F401

ITEM = "docs/work/demo"
REVIEWS = f"{ITEM}/reviews"
REVIEWER = "reviewer agent a1b2"
SCRIPT = CLAUDE / "scripts" / "review_record.py"
CONTRACT = CLAUDE / "contracts" / "review-record.v1.json"
UTC = timezone.utc


# ---------------------------------------------------------------- helpers

@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch):
    """The writer's clock (`review_record.now`), settable per test."""
    class Clock:
        t = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)

        def set(self, iso: str) -> None:
            self.t = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)

    c = Clock()
    monkeypatch.setattr(rr(), "now", lambda: c.t)
    return c


def run(capsys, root: Path, *args: str) -> tuple[int, str, str]:
    """The CLI in-process: (exit code, stdout, stderr)."""
    capsys.readouterr()
    code = rr().main([*args, "--root", str(root)])
    out = capsys.readouterr()
    return code, out.out, out.err


def cli(root: Path, *args: str, env: dict | None = None, script: Path = SCRIPT) -> subprocess.CompletedProcess:
    """The CLI as a real process."""
    return subprocess.run([sys.executable, str(script), *args, "--root", str(root)], capture_output=True, text=True,
                          env={**ENV, **(env or {})}, timeout=120)


def put_report(tmp_path: Path, text: str | bytes, name: str = "report.md") -> Path:
    p = tmp_path / name
    p.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
    return p


def do_write(capsys, repo: Path, tmp_path: Path, *, kind: str = "design", verdict: str = "pass", reviewer: str = REVIEWER,
             text=None, verifies: str | None = None, commit_sha: str | None = None, item: str = ITEM,
             name: str = "report.md") -> tuple[int, str, str]:
    """`write` with a good report (or `text`: str, bytes, or a function of the current hash)."""
    h = item_hash(repo)
    if callable(text):
        text = text(h)
    if text is None:
        text = good_report(h, verdict, commit_sha)
    args = ["write", "--item", item, "--kind", kind, "--reviewer", reviewer, "--report", str(put_report(tmp_path, text, name))]
    return run(capsys, repo, *args, *(["--verifies", verifies] if verifies else []))


def reviews(repo: Path) -> list[str]:
    d = repo / REVIEWS
    return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


def put_record(repo: Path, name: str, *, kind: str = "design", verdict: str = "pass", content: str | None = None,
               recorded: str = "2026-10-01T10:00:00Z", reviewer: str = REVIEWER, commit_sha: str | None = None,
               verifies: str | None = None, body: str | None = None, body_verdict: str | None = None) -> Path:
    """A record written by hand in the FR-6 format (frontmatter, then the report)."""
    content = content or item_hash(repo)
    fm = {"kind": kind, "reviewer": reviewer, "verdict": verdict, "content": content, "commit": commit_sha,
          "verifies": verifies, "recorded": recorded}
    head = "\n".join(["---", *[f"{k}: {json.dumps(v)}" for k, v in fm.items() if v is not None], "---"])
    body = body if body is not None else f"REVIEWED: {content}\n\nVERDICT: {body_verdict or verdict}\n"
    p = repo / REVIEWS / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"{head}\n{body}", encoding="utf-8", newline="\n")
    return p


def rec_name(repo: Path, kind: str = "design", suffix: str = "") -> str:
    return f"2026-10-01-{kind}-{item_hash(repo)[7:15]}{suffix}.md"


def stage_all(repo: Path) -> None:
    git(repo, "add", "-A")


def staged_lock(repo: Path) -> None:
    """HEAD holds the demo item at draft; the lock (status: spec-locked) is staged."""
    seed_status(repo, "draft")
    set_status(repo, "spec-locked")
    stage_all(repo)


def land(repo: Path, message: str = "docs: move demo") -> subprocess.CompletedProcess:
    stage_all(repo)
    return commit(repo, "-m", message)


def staged_ship(repo: Path) -> None:
    """HEAD holds the demo item at building; the ship (status: shipped, with its evidence) is staged."""
    write(repo, f"{ITEM}/evidence/demo.webm", "x")
    set_status(repo, "shipped")
    stage_all(repo)


def edit_item(repo: Path, rel: str = "functional.md", add: str = "\nAn added paragraph.\n") -> None:
    p = repo / ITEM / rel
    p.write_text(p.read_text(encoding="utf-8") + add, encoding="utf-8", newline="\n")
    stage_all(repo)


def add_entry(repo: Path, mode: str, rel: str, content: bytes = b"target") -> None:
    """Stage an index entry of any mode without touching the working tree (symlinks and gitlinks on any OS)."""
    sha = subprocess.run(["git", "-C", str(repo), "hash-object", "-w", "--stdin"], input=content, capture_output=True,
                         check=True).stdout.decode().strip()
    git(repo, "update-index", "--add", "--cacheinfo", f"{mode},{sha},{rel}")


def states(out: str) -> dict[str, str]:
    """verify's `state<TAB>path<TAB>detail` lines as {path: state}."""
    return {cols[1]: cols[0] for cols in (line.split("\t") for line in out.splitlines()) if len(cols) >= 2}


# ---------------------------------------------------------------- AC-1: write

def test_ac1_write_records_the_briefed_hash_and_repeats_are_no_ops(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-1
    h = item_hash(repo2)
    code, out, err = do_write(capsys, repo2, tmp_path)
    assert code == 0, err
    name = f"2026-11-02-design-{h[7:15]}.md"
    assert out.strip().endswith(f"{REVIEWS}/{name}") and reviews(repo2) == [name]
    text = (repo2 / REVIEWS / name).read_text(encoding="utf-8")
    assert f'content: "{h}"' in text and "recorded: \"2026-11-02T12:00:00Z\"" in text and "verdict: \"pass\"" in text
    assert text.endswith(good_report(h))  # the report verbatim
    again = do_write(capsys, repo2, tmp_path)
    clock.set("2026-11-09T08:30:00Z")  # a later date
    later = do_write(capsys, repo2, tmp_path)
    assert again[0] == later[0] == 0 and again[1] == later[1] == out and reviews(repo2) == [name]


def test_ac1_a_different_report_gets_the_next_suffix_each_time(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-1
    h = item_hash(repo2)
    base = f"2026-11-02-design-{h[7:15]}"
    assert do_write(capsys, repo2, tmp_path)[0] == 0
    for n, extra in ((2, "Second."), (3, "Third.")):
        text = good_report(h).replace("No findings.", extra)
        code, out, err = do_write(capsys, repo2, tmp_path, text=text)
        assert code == 0, err
        assert out.strip().endswith(f"{base}-{n}.md")
    assert reviews(repo2) == sorted([f"{base}.md", f"{base}-2.md", f"{base}-3.md"])


def test_ac1_a_precreated_target_name_is_never_overwritten(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-1
    h = item_hash(repo2)
    squatter = repo2 / REVIEWS / f"2026-11-02-design-{h[7:15]}.md"
    squatter.parent.mkdir(parents=True)
    squatter.write_text("another writer got here first\n", encoding="utf-8")
    code, out, err = do_write(capsys, repo2, tmp_path)
    assert code == 0, err
    assert out.strip().endswith("-2.md") and squatter.read_text(encoding="utf-8") == "another writer got here first\n"


def test_ac1_a_writer_that_loses_the_link_race_retries_with_the_next_suffix(repo2: Path, tmp_path: Path, capsys, clock,
                                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    # review-records/AC-1: two concurrent writers both land
    real_link, raced, sources = os.link, [], []

    def racing_link(src, dst, *a, **k):
        sources.append(Path(src).name)
        if not raced:
            raced.append(dst)
            Path(dst).write_text("the other writer's record\n", encoding="utf-8")
        return real_link(src, dst, *a, **k)

    monkeypatch.setattr(os, "link", racing_link)
    code, out, err = do_write(capsys, repo2, tmp_path)
    assert code == 0, err
    # the in-flight file is `.<name>.<pid>.tmp`, never a `.md` a reader could take for a record (FR-6)
    assert all(re.fullmatch(rf"\.\d{{4}}-\d{{2}}-\d{{2}}-design-[0-9a-f]{{8}}\.md\.{os.getpid()}\.tmp", s) for s in sources), sources
    assert out.strip().endswith("-2.md") and Path(raced[0]).read_text(encoding="utf-8") == "the other writer's record\n"
    assert not [n for n in reviews(repo2) if n.endswith(".tmp")]  # the writer removed its own temp file


def test_ac1_a_leftover_temp_file_is_kept_and_never_counted(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-1
    leftover = repo2 / REVIEWS / ".2026-11-02-design-deadbeef.md.123.tmp"
    leftover.parent.mkdir(parents=True)
    leftover.write_text(good_report(item_hash(repo2)), encoding="utf-8")
    code, out, err = do_write(capsys, repo2, tmp_path)
    assert code == 0 and leftover.is_file(), err
    assert leftover.name in reviews(repo2) and out.strip().endswith(f"{item_hash(repo2)[7:15]}.md")
    vcode, vout, _ = run(capsys, repo2, "verify", "--tree", "index")
    assert "info" in vout and leftover.name in vout and states(vout).get(f"{REVIEWS}/{leftover.name}") != "fresh"
    staged_lock(repo2)  # at the gate the temp file is no record: only the one real record counts
    stage_all(repo2)
    assert commit(repo2, "-m", "docs: lock").returncode == 0


# ---------------------------------------------------------------- AC-2: write refusals

def bad(text):
    return {"text": text}


STALE_NOTE = "REVIEWED hash"
FENCE = "```\nVERDICT: pass\n```\nsome prose after the fence\n"


def tail(h: str, verdict_line: str) -> str:
    return f"REVIEWED: {h}\n\nFindings: none.\n\n{verdict_line}\n"


AC2_CASES = {
    "empty": (lambda h: "", "report is empty", {}),
    "oversize": (lambda h: tail(h, "VERDICT: pass") + "x" * 2_000_000, "larger than 1 MB", {}),
    "bold-verdict": (lambda h: tail(h, "**VERDICT: pass**"), "VERDICT", {}),
    "passed-verdict": (lambda h: tail(h, "VERDICT: passed"), "VERDICT", {}),
    "template-verdict": (lambda h: tail(h, "VERDICT: pass | fix-first | block"), "VERDICT", {}),
    "verdict-in-fence": (lambda h: f"REVIEWED: {h}\n\n{FENCE}", "VERDICT", {}),
    "no-reviewed": (lambda h: "Findings: none.\n\nVERDICT: pass\n", "REVIEWED", {}),
    "two-reviewed": (lambda h: f"REVIEWED: {h}\nREVIEWED: {h}\n\nVERDICT: pass\n", "REVIEWED", {}),
    "reviewed-in-fence": (lambda h: f"```\nREVIEWED: {h}\n```\n\nVERDICT: pass\n", "REVIEWED", {}),
    "upper-hex": (lambda h: f"REVIEWED: sha256:{h[7:].upper()}\n\nVERDICT: pass\n", "REVIEWED", {}),
    "non-utf8": (lambda h: b"REVIEWED: " + h.encode() + b"\n\xff\xfe broken\nVERDICT: pass\n", "UTF-8", {}),
    "code-no-commit": (lambda h: tail(h, "VERDICT: pass"), "REVIEWED-COMMIT", {"kind": "code"}),
    "code-missing-commit-object": (lambda h: f"REVIEWED: {h}\nREVIEWED-COMMIT: {'deadbeef' * 5}\n\nVERDICT: pass\n",
                                   "not a commit", {"kind": "code"}),
    "design-with-commit": (lambda h: f"REVIEWED: {h}\nREVIEWED-COMMIT: {'a' * 40}\n\nVERDICT: pass\n",
                           "REVIEWED-COMMIT", {}),
    "reviewer-Self": (None, "reviewer", {"reviewer": "Self"}),
    "reviewer-na": (None, "reviewer", {"reviewer": "n/a"}),
    "reviewer-placeholder": (None, "reviewer", {"reviewer": "<reviewer>"}),
    "reviewer-owner": (None, "reviewer", {"reviewer": " Harness "}),
    "reviewer-empty": (None, "reviewer", {"reviewer": ""}),
    "item-outside-work": (None, "docs/work", {"item": "src"}),
    "item-subfolder": (None, "docs/work", {"item": "docs/work/demo/sub"}),
    "item-unknown": (None, "docs/work", {"item": "docs/work/nope"}),
    "kind-unknown": (None, "kind", {"kind": "chat"}),
    "verify-without-target": (None, "verifies", {"kind": "verify"}),
    "verifies-on-design": (None, "verifies", {"verifies": "x.md"}),
}


@pytest.mark.parametrize("case", list(AC2_CASES))
def test_ac2_a_bad_report_or_argument_is_refused_by_name_and_writes_nothing(repo2: Path, tmp_path: Path, capsys, clock,
                                                                            case: str) -> None:
    # review-records/AC-2
    text, reason, opts = AC2_CASES[case]
    before = reviews(repo2)
    commit_sha = head_sha(repo2) if opts.get("kind") == "code" else None
    code, out, err = do_write(capsys, repo2, tmp_path, text=text, commit_sha=commit_sha, **opts)
    assert code == 1 and reason in err, (out, err)
    assert reviews(repo2) == before


def test_ac2_a_report_saved_before_a_later_edit_is_refused(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-2
    old = good_report(item_hash(repo2))
    edit_item(repo2)
    code, _, err = do_write(capsys, repo2, tmp_path, text=old)
    assert code == 1 and STALE_NOTE in err and reviews(repo2) == []


def test_ac2_an_item_with_an_untracked_or_unstaged_change_must_be_staged_first(repo2: Path, tmp_path: Path, capsys,
                                                                              clock) -> None:
    # review-records/AC-2 (FR-3)
    write(repo2, f"{ITEM}/notes.md", "untracked\n")
    code, _, err = do_write(capsys, repo2, tmp_path, text=good_report("sha256:" + "0" * 64))
    assert code == 1 and "stage the item first" in err
    (repo2 / ITEM / "notes.md").unlink()
    (repo2 / ITEM / "functional.md").write_text("unstaged edit\n", encoding="utf-8")
    code, _, err = run(capsys, repo2, "hash", "--item", ITEM)
    assert code == 1 and "stage the item first" in err and reviews(repo2) == []


def test_ac2_a_code_report_needs_its_commit_and_it_is_stored_in_full(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-2 (FR-4)
    full = head_sha(repo2)
    h = item_hash(repo2)
    report = f"REVIEWED: {h}\nREVIEWED-COMMIT: {full[:10]}\n\nVERDICT: fix-first\n"
    code, out, err = do_write(capsys, repo2, tmp_path, kind="code", text=report)
    assert code == 0, err
    assert f'commit: "{full}"' in (repo2 / out.strip()).read_text(encoding="utf-8")


def test_ac2_a_verify_of_a_code_record_needs_a_commit_and_a_design_verify_must_not_have_one(
        repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-2 (FR-4)
    sha = head_sha(repo2)
    code, out, err = do_write(capsys, repo2, tmp_path, kind="code", verdict="fix-first", commit_sha=sha)
    assert code == 0, err
    target = Path(out.strip()).name
    h = item_hash(repo2)
    no_commit = do_write(capsys, repo2, tmp_path, kind="verify", verifies=target, text=tail(h, "VERDICT: pass"))
    assert no_commit[0] == 1 and "REVIEWED-COMMIT" in no_commit[2]
    ok = do_write(capsys, repo2, tmp_path, kind="verify", verifies=target, commit_sha=sha)
    assert ok[0] == 0, ok[2]
    code, out, err = do_write(capsys, repo2, tmp_path, kind="design", verdict="fix-first",
                              text=lambda h: tail(h, "VERDICT: fix-first"), name="d.md")
    assert code == 0, err
    dtarget = Path(out.strip()).name
    with_commit = do_write(capsys, repo2, tmp_path, kind="verify", verifies=dtarget, commit_sha=sha)
    assert with_commit[0] == 1 and "REVIEWED-COMMIT" in with_commit[2]


def test_ac2_verifies_must_name_a_fix_first_record_of_this_item(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-2 (FR-5)
    code, out, err = do_write(capsys, repo2, tmp_path)  # a pass record
    assert code == 0, err
    passing = Path(out.strip()).name
    refused = do_write(capsys, repo2, tmp_path, kind="verify", verifies=passing)
    assert refused[0] == 1 and "fix-first" in refused[2]
    missing = do_write(capsys, repo2, tmp_path, kind="verify", verifies="2026-01-01-design-00000000.md")
    assert missing[0] == 1 and "verifies" in missing[2]
    assert reviews(repo2) == [passing]


def test_ac2_item_path_forms_resolve_to_the_exact_indexed_folder(repo2: Path, capsys) -> None:
    # review-records/AC-2 (FR-3): backslashes, a trailing slash and letter case are normalised
    expected = item_hash(repo2)
    for form in ("docs\\work\\demo", "docs/work/demo/", "DOCS/Work/Demo"):
        code, out, err = run(capsys, repo2, "hash", "--item", form)
        assert code == 0 and out.strip() == expected, (form, err)


def test_ac2_the_cli_is_a_real_process_and_takes_the_report_from_a_file(repo2: Path, tmp_path: Path) -> None:
    # review-records/AC-2: the arrival channel is a UTF-8 file, never a pipe
    text = good_report(item_hash(repo2)).replace("No findings.", "No findings. café 日本")
    report = put_report(tmp_path, text)
    r = cli(repo2, "write", "--item", ITEM, "--kind", "design", "--reviewer", REVIEWER, "--report", str(report))
    assert r.returncode == 0, r.stderr
    assert (repo2 / r.stdout.strip()).read_bytes().endswith(report.read_bytes())


# ---------------------------------------------------------------- AC-3: the hash

GOLDEN = {
    "README.md": "---\nid: golden\ntype: feature\nstatus: draft\nowner: harness\n---\n# Golden é\n\nline two\n",
    "components.md": "# Components\n\nnaïve café 日本\n",
    "Z.md": "upper\n",
    "a.md": "lower\n",
    "b.md": "b file\n",
    "b/x.md": "nested b\n",
    "data/schema.json": '{"k": [1, 2]}\n',
    "data/ünicode.txt": "path with a non-ascii letter\n",
    "reviews/2026-11-02-design-00000000.md": "not part of the hash\n",
    "evidence/shot.txt": "not part of the hash\n",
    "cycles/c1.md": "not part of the hash\n",
    "trace.jsonl": '{"a": 1}\n',
    "drift.md": "generated\n",
}
GOLDEN_ITEM = "docs/work/golden"
GOLDEN_DIGEST = "sha256:e55b06b37462680599e5b1cd5ebc0cc30417d713219b4230f9b6947a9d761251"


def golden_repo(tmp_path: Path, *, head: bool = False) -> Path:
    r = tmp_path / "golden-repo"
    git(tmp_path, "init", "-q", "-b", "main", str(r))
    git(r, "config", "core.autocrlf", "false")
    for rel, text in GOLDEN.items():
        p = r / GOLDEN_ITEM / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode("utf-8"))
    stage_all(r)
    if head:
        git(r, "commit", "-qm", "chore: golden", "--no-verify")
    return r


def golden_hash(repo: Path, tree: str = "index") -> str:
    t = sc().IndexTree(repo) if tree == "index" else sc().HeadTree(repo)
    return rr().content_hash(t, GOLDEN_ITEM)


def put_bytes(repo: Path, rel: str, data: bytes) -> None:
    p = repo / GOLDEN_ITEM / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    stage_all(repo)


def test_ac3_the_golden_vector_is_exact_on_the_index_and_on_head(tmp_path: Path) -> None:
    # review-records/AC-3
    r = golden_repo(tmp_path, head=True)
    assert golden_hash(r, "index") == GOLDEN_DIGEST
    assert golden_hash(r, "head") == GOLDEN_DIGEST


def test_ac3_a_digest_is_sha256_prefixed_lowercase_hex(tmp_path: Path) -> None:
    # review-records/AC-3
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", golden_hash(golden_repo(tmp_path)))


KEEP = {
    "crlf": lambda r: [put_bytes(r, k, v.replace("\n", "\r\n").encode()) for k, v in GOLDEN.items()],
    "lone-cr": lambda r: [put_bytes(r, k, v.replace("\n", "\r").encode()) for k, v in GOLDEN.items()],
    "status-line": lambda r: put_bytes(r, "README.md", GOLDEN["README.md"].replace("status: draft", "status: building").encode()),
    "reviews-added": lambda r: put_bytes(r, "reviews/new.md", b"another record\n"),
    "evidence-added": lambda r: put_bytes(r, "evidence/more/clip.bin", b"\x00\x01"),
    "cycles-added": lambda r: put_bytes(r, "cycles/c2/pack.md", b"a cycle pack\n"),
    "trace-appended": lambda r: put_bytes(r, "trace.jsonl", GOLDEN["trace.jsonl"].encode() + b'{"b": 2}\n'),
    "drift-appended": lambda r: put_bytes(r, "drift.md", GOLDEN["drift.md"].encode() + b"more drift\n"),
}
CHANGE = {
    "reviews-old": lambda r: put_bytes(r, "reviews-old/x.md", b"look-alike folder\n"),
    "evidence2": lambda r: put_bytes(r, "evidence2/x.md", b"look-alike folder\n"),
    "sub-reviews": lambda r: put_bytes(r, "sub/reviews/x.md", b"nested reviews folder is content\n"),
    "one-byte-in-json": lambda r: put_bytes(r, "data/schema.json", b'{"k": [1, 3]}\n'),
    "text-moved": lambda r: (put_bytes(r, "a.md", b""), put_bytes(r, "b.md", b"b file\nlower\n")),
}


@pytest.mark.parametrize("case", list(KEEP))
def test_ac3_line_endings_status_and_excluded_files_keep_the_hash(tmp_path: Path, case: str) -> None:
    # review-records/AC-3
    r = golden_repo(tmp_path)
    KEEP[case](r)
    assert golden_hash(r) == GOLDEN_DIGEST


@pytest.mark.parametrize("case", list(CHANGE))
def test_ac3_look_alike_folders_one_byte_and_moved_text_change_the_hash(tmp_path: Path, case: str) -> None:
    # review-records/AC-3
    r = golden_repo(tmp_path)
    CHANGE[case](r)
    assert golden_hash(r) != GOLDEN_DIGEST


def test_ac3_a_committed_crlf_item_hashes_the_same_on_head(tmp_path: Path) -> None:
    # review-records/AC-3: IndexTree and HeadTree are one function
    r = golden_repo(tmp_path)
    KEEP["crlf"](r)
    git(r, "commit", "-qm", "chore: crlf", "--no-verify")
    assert golden_hash(r, "head") == GOLDEN_DIGEST == golden_hash(r, "index")


def test_ac3_an_unborn_head_is_an_empty_tree(tmp_path: Path) -> None:
    # review-records/AC-3 (FR-14)
    r = golden_repo(tmp_path)
    t = sc().HeadTree(r)
    assert t.entries("docs/work/") == [] and t.read_many([]) == {}


def test_ac3_trees_return_modes_and_bytes(tmp_path: Path) -> None:
    # review-records/AC-3 (FR-14)
    r = golden_repo(tmp_path, head=True)
    add_entry(r, "100755", f"{GOLDEN_ITEM}/run.sh", b"#!/bin/sh\r\n")
    git(r, "commit", "-qm", "chore: exec", "--no-verify")
    for tree in (sc().IndexTree(r), sc().HeadTree(r)):
        entries = dict((path, mode) for mode, path in tree.entries(f"{GOLDEN_ITEM}/"))
        assert entries[f"{GOLDEN_ITEM}/run.sh"] == "100755" and entries[f"{GOLDEN_ITEM}/README.md"] == "100644"
        assert tree.read_many([f"{GOLDEN_ITEM}/run.sh", f"{GOLDEN_ITEM}/Z.md"]) == {
            f"{GOLDEN_ITEM}/run.sh": b"#!/bin/sh\r\n", f"{GOLDEN_ITEM}/Z.md": b"upper\n"}


def test_ac3_an_index_with_an_unmerged_path_cannot_be_read(tmp_path: Path) -> None:
    # review-records/AC-3 (FR-14): a half-merged index has no single staged content to hash
    r = golden_repo(tmp_path, head=True)
    git(r, "checkout", "-q", "-b", "other")
    put_bytes(r, "a.md", b"from other\n")
    git(r, "commit", "-qm", "chore: other", "--no-verify")
    git(r, "checkout", "-q", "main")
    put_bytes(r, "a.md", b"from main\n")
    git(r, "commit", "-qm", "chore: main", "--no-verify")
    assert "CONFLICT" in git(r, "merge", "other", check=False).stdout
    with pytest.raises(OSError, match="unmerged"):
        golden_hash(r)


def test_ac3_read_many_uses_one_batch_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # review-records/AC-3 (FR-14, budget): one listing and one cat-file --batch per hash
    r = golden_repo(tmp_path)
    calls: list[tuple] = []
    real = subprocess.run

    def spy(args, *a, **k):
        calls.append(tuple(args))
        return real(args, *a, **k)

    monkeypatch.setattr(subprocess, "run", spy)
    golden_hash(r)
    assert sum("cat-file" in c for c in calls) == 1 and sum("ls-files" in c for c in calls) == 1, calls


# ---------------------------------------------------------------- AC-4: hash refusals

def readme_with(repo: Path, text: str) -> None:
    put_bytes(repo, "README.md", text.encode("utf-8"))


AC4_FILE_CASES = {
    "nested-readme": (lambda r: put_bytes(r, "sub/README.md", b"# nested item\n"), "nested"),
    "bom": (lambda r: readme_with(r, "\ufeff" + GOLDEN["README.md"]), "BOM"),
    "bom-other-file": (lambda r: put_bytes(r, "a.md", b"\xef\xbb\xbfbom\n"), "BOM"),
    "non-utf8": (lambda r: put_bytes(r, "a.md", b"\xff\xfe\n"), "UTF-8"),
    "two-status": (lambda r: readme_with(r, GOLDEN["README.md"].replace("owner:", "status: again\nowner:")), "status"),
    "indented-status": (lambda r: readme_with(r, GOLDEN["README.md"].replace("status: draft", " status: draft")), "status"),
    "statusX": (lambda r: readme_with(r, GOLDEN["README.md"].replace("status: draft", "statusX: draft")), "status"),
    "quoted-status": (lambda r: readme_with(r, GOLDEN["README.md"].replace("status: draft", '"status": draft')), "status"),
    "closing-delimiter-space": (lambda r: readme_with(r, GOLDEN["README.md"].replace("\n---\n# Golden", "\n--- \n# Golden")),
                                "frontmatter"),
    "opening-delimiter-space": (lambda r: readme_with(r, GOLDEN["README.md"].replace("---\nid", "--- \nid", 1)), "frontmatter"),
    "no-frontmatter": (lambda r: readme_with(r, "# no frontmatter\n"), "frontmatter"),
}


@pytest.mark.parametrize("case", list(AC4_FILE_CASES))
def test_ac4_hash_refuses_each_unhashable_item_by_name(tmp_path: Path, capsys, case: str) -> None:
    # review-records/AC-4
    r = golden_repo(tmp_path)
    mutate, reason = AC4_FILE_CASES[case]
    mutate(r)
    code, out, err = run(capsys, r, "hash", "--item", GOLDEN_ITEM)
    assert code == 1 and reason in err and out == "", (out, err)


@pytest.mark.parametrize("folder", ["Reviews", "EVIDENCE", "Cycles"])
def test_ac4_a_letter_case_look_alike_of_an_excluded_folder_is_refused(tmp_path: Path, folder: str) -> None:
    # review-records/AC-4 (index-only entry: a case-insensitive disk cannot hold both folders)
    r = golden_repo(tmp_path)
    add_entry(r, "100644", f"{GOLDEN_ITEM}/{folder}/x.md", b"look-alike\n")
    with pytest.raises(rr().HashError, match=folder):
        golden_hash(r)


@pytest.mark.parametrize("mode", ["120000", "160000"])
def test_ac4_symlink_and_gitlink_entries_are_refused(tmp_path: Path, mode: str) -> None:
    # review-records/AC-4
    r = golden_repo(tmp_path)
    add_entry(r, mode, f"{GOLDEN_ITEM}/link", b"a.md" if mode == "120000" else b"x")
    with pytest.raises(rr().HashError, match="symlink|gitlink|submodule"):
        golden_hash(r)


def test_ac4_an_entry_under_an_excluded_folder_is_not_inspected(tmp_path: Path) -> None:
    # review-records/AC-4 (FR-2): excluded paths are not inputs
    r = golden_repo(tmp_path)
    add_entry(r, "120000", f"{GOLDEN_ITEM}/reviews/link", b"a.md")
    assert golden_hash(r) == GOLDEN_DIGEST


# ---------------------------------------------------------------- the gate: locking and shipping

def test_ac5_a_lock_with_a_fresh_pass_design_record_lands(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-5
    staged_lock(repo2)
    code, out, err = do_write(capsys, repo2, tmp_path)
    assert code == 0, err
    assert land(repo2, "docs: lock demo").returncode == 0


def test_ac5_a_lock_with_a_pass_verify_of_a_fix_first_design_record_lands(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-5
    staged_lock(repo2)
    clock.set("2026-11-02T09:00:00Z")
    code, out, err = do_write(capsys, repo2, tmp_path, verdict="fix-first")
    assert code == 0, err
    target = Path(out.strip()).name
    assert land(repo2).returncode != 0  # a lone fix-first does not lock
    clock.set("2026-11-02T11:00:00Z")
    code, out, err = do_write(capsys, repo2, tmp_path, kind="verify", verifies=target, name="verify.md")
    assert code == 0, err
    assert land(repo2).returncode == 0


def test_ac5_a_squash_merge_that_made_the_reviewed_commit_a_non_ancestor_still_ships(repo2: Path, tmp_path: Path, capsys,
                                                                                    clock) -> None:
    # review-records/AC-5: the reviewed commit is evidence, not an ancestry requirement
    git(repo2, "checkout", "-q", "-b", "side")
    write(repo2, "src/side.py", "y = 1\n")
    git(repo2, "add", "-A")
    git(repo2, "commit", "-qm", "chore: side", "--no-verify")
    side = head_sha(repo2)
    git(repo2, "checkout", "-q", "main")
    git(repo2, "branch", "-q", "-D", "side")
    staged_ship(repo2)
    code, _, err = do_write(capsys, repo2, tmp_path, kind="code", commit_sha=side)
    assert code == 0, err
    assert land(repo2, "docs: ship demo").returncode == 0


def recorded_lock(repo: Path, tmp_path: Path, capsys, **kw) -> subprocess.CompletedProcess:
    staged_lock(repo)
    return do_write(capsys, repo, tmp_path, **kw)


class Ctx:
    def __init__(self, repo: Path, tmp_path: Path, capsys, clock) -> None:
        self.repo, self.tmp, self.capsys, self.clock = repo, tmp_path, capsys, clock

    def write(self, **kw):
        code, out, err = do_write(self.capsys, self.repo, self.tmp, **kw)
        assert code == 0, err
        return Path(out.strip()).name

    def hand(self, name: str, **kw) -> Path:
        return put_record(self.repo, name, **kw)

    def sha(self) -> str:
        return head_sha(self.repo)


def sc_no_record(c: Ctx):
    return ["needs a fresh design review"]


def sc_edited_after(c: Ctx):
    c.write()
    edit_item(c.repo)
    return ["record is stale", "reviewed"]


def sc_renamed_folder(c: Ctx):
    c.write()
    git(c.repo, "mv", ITEM, "docs/work/demo2")
    for p in (c.repo / "docs/work/demo2").rglob("*.md"):
        if "reviews" not in p.parts:
            p.write_text(p.read_text(encoding="utf-8").replace("docs/work/demo/", "docs/work/demo2/")
                         .replace("id: demo\n", "id: demo2\n"), encoding="utf-8", newline="\n")
    return ["record is stale"]


def sc_older_pass_newer_fix_first(c: Ctx):
    c.hand(rec_name(c.repo), recorded="2026-10-01T09:00:00Z")
    c.hand(rec_name(c.repo, "design", "-2"), verdict="fix-first", recorded="2026-10-01T10:00:00Z")
    return ["newest design record is fix-first"]


def sc_tie_base_vs_2(c: Ctx):
    c.hand(rec_name(c.repo), verdict="pass")
    c.hand(rec_name(c.repo, "design", "-2"), verdict="fix-first")
    return ["newest design record is fix-first"]


def sc_tie_2_vs_10(c: Ctx):
    c.hand(rec_name(c.repo, "design", "-2"), verdict="pass")
    c.hand(rec_name(c.repo, "design", "-10"), verdict="fix-first")
    return ["newest design record is fix-first"]


def sc_only_code(c: Ctx):
    c.hand(rec_name(c.repo, "code"), kind="code", commit_sha=c.sha())
    return ["needs a fresh design review"]


def sc_verify_of_code(c: Ctx):
    c.hand(rec_name(c.repo, "code"), kind="code", verdict="fix-first", commit_sha=c.sha(), recorded="2026-10-01T09:00:00Z")
    c.hand(rec_name(c.repo, "verify"), kind="verify", commit_sha=c.sha(), verifies=rec_name(c.repo, "code"))
    return ["needs a fresh design review"]


def sc_frontmatter_pass_body_fix_first(c: Ctx):
    c.hand(rec_name(c.repo), verdict="pass", body_verdict="fix-first")
    return ["record invalid", "VERDICT"]


def sc_self_reviewer(c: Ctx):
    c.hand(rec_name(c.repo), reviewer="self")
    return ["record invalid", "reviewer"]


def sc_unparseable_frontmatter(c: Ctx):
    p = c.hand(rec_name(c.repo))
    p.write_text("---\nkind: [design\nverdict: pass\n---\nVERDICT: pass\n", encoding="utf-8")
    return ["record invalid", p.name]


def sc_oversize_record(c: Ctx):
    c.hand(rec_name(c.repo), body="x" * 2_000_000 + "\nVERDICT: pass\n")
    return ["record invalid", "1 MB"]


AC6_CASES = {f.__name__[3:]: f for f in (sc_no_record, sc_edited_after, sc_renamed_folder, sc_older_pass_newer_fix_first,
                                         sc_tie_base_vs_2, sc_tie_2_vs_10, sc_only_code, sc_verify_of_code,
                                         sc_frontmatter_pass_body_fix_first, sc_self_reviewer,
                                         sc_unparseable_frontmatter, sc_oversize_record)}


@pytest.mark.parametrize("case", list(AC6_CASES))
def test_ac6_a_lock_without_a_fresh_pass_is_refused_by_name(repo2: Path, tmp_path: Path, capsys, clock, case: str) -> None:
    # review-records/AC-6
    staged_lock(repo2)
    reasons = AC6_CASES[case](Ctx(repo2, tmp_path, capsys, clock))
    r = land(repo2)
    assert r.returncode != 0 and all(x in r.stderr for x in reasons), r.stderr
    assert "demo" in r.stderr


def sc_ok_base_fix_first_then_2_pass(c: Ctx):
    c.hand(rec_name(c.repo), verdict="fix-first")
    c.hand(rec_name(c.repo, "design", "-2"), verdict="pass")


def sc_ok_10_pass_over_2_fix_first(c: Ctx):
    c.hand(rec_name(c.repo, "design", "-2"), verdict="fix-first")
    c.hand(rec_name(c.repo, "design", "-10"), verdict="pass")


def sc_ok_invalid_record_beside_a_fresh_pass(c: Ctx):
    c.hand(rec_name(c.repo), verdict="pass")
    c.hand(rec_name(c.repo, "design", "-2"), reviewer="self", recorded="2026-10-02T10:00:00Z")


def sc_ok_newer_by_time_beats_larger_suffix(c: Ctx):
    c.hand(rec_name(c.repo, "design", "-10"), verdict="fix-first", recorded="2026-10-01T09:00:00Z")
    c.hand(rec_name(c.repo, "design", "-2"), verdict="pass", recorded="2026-10-01T10:00:00Z")


@pytest.mark.parametrize("scenario", [sc_ok_base_fix_first_then_2_pass, sc_ok_10_pass_over_2_fix_first,
                                      sc_ok_invalid_record_beside_a_fresh_pass, sc_ok_newer_by_time_beats_larger_suffix],
                         ids=lambda f: f.__name__[6:])
def test_ac6_the_newest_valid_record_decides_by_time_then_numeric_suffix(repo2: Path, tmp_path: Path, capsys, clock,
                                                                         scenario) -> None:
    # review-records/AC-6
    staged_lock(repo2)
    scenario(Ctx(repo2, tmp_path, capsys, clock))
    r = land(repo2)
    assert r.returncode == 0, r.stderr


def test_ac6_a_stale_pass_is_not_rescued_by_an_older_fresh_one(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-6: an old pass record copied in after later edits
    staged_lock(repo2)
    c = Ctx(repo2, tmp_path, capsys, clock)
    c.hand(rec_name(repo2), recorded="2026-10-01T09:00:00Z")
    c.hand(rec_name(repo2, "design", "-2"), content="sha256:" + "1" * 64, recorded="2026-10-01T10:00:00Z")
    r = land(repo2)
    assert r.returncode != 0 and "record is stale" in r.stderr and "reviewed 11111111" in r.stderr, r.stderr


def test_ac6_an_item_that_cannot_be_hashed_is_refused_by_name(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-6 (FR-2 at the gate): a record cannot vouch for content that has no hash
    staged_lock(repo2)
    Ctx(repo2, tmp_path, capsys, clock).hand(rec_name(repo2))
    write(repo2, f"{ITEM}/notes.txt", "﻿a BOM\n")
    r = land(repo2)
    assert r.returncode != 0 and "cannot hash item" in r.stderr and "BOM" in r.stderr, r.stderr


def test_ac6_a_block_verdict_is_named(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-6
    staged_lock(repo2)
    Ctx(repo2, tmp_path, capsys, clock).hand(rec_name(repo2), verdict="block")
    r = land(repo2)
    assert r.returncode != 0 and "newest design record is block" in r.stderr, r.stderr


def ship_with(repo: Path, tmp_path: Path, capsys, *records: str) -> subprocess.CompletedProcess:
    staged_ship(repo)
    for kind in records:
        code, _, err = do_write(capsys, repo, tmp_path, kind=kind, commit_sha=head_sha(repo) if kind == "code" else None,
                                name=f"{kind}.md")
        assert code == 0, err
    return land(repo, "docs: ship demo")


def test_ac7_a_ship_with_a_fresh_pass_code_record_lands(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-7
    assert ship_with(repo2, tmp_path, capsys, "code").returncode == 0


def test_ac7_a_ship_with_only_a_design_record_is_refused(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-7
    r = ship_with(repo2, tmp_path, capsys, "design")
    assert r.returncode != 0 and "needs a fresh code review" in r.stderr, r.stderr


def test_ac7_a_ship_with_a_stale_or_failing_code_record_is_refused(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-7
    staged_ship(repo2)
    c = Ctx(repo2, tmp_path, capsys, clock)
    c.hand(rec_name(repo2, "code"), kind="code", commit_sha=head_sha(repo2), content="sha256:" + "2" * 64)
    r = land(repo2)
    assert r.returncode != 0 and "record is stale" in r.stderr, r.stderr
    (repo2 / REVIEWS / rec_name(repo2, "code")).unlink()
    c.hand(rec_name(repo2, "code"), kind="code", commit_sha=head_sha(repo2), verdict="fix-first")
    r = land(repo2)
    assert r.returncode != 0 and "newest code record is fix-first" in r.stderr, r.stderr


def test_ac7_a_ship_after_a_source_change_made_after_the_code_record_lands(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-7: pins D32 - the local gate does not judge code freshness (work item gate-ci does)
    staged_ship(repo2)
    code, _, err = do_write(capsys, repo2, tmp_path, kind="code", commit_sha=head_sha(repo2))
    assert code == 0, err
    git(repo2, "stash", "-q", "-u")  # land the source change first, on its own commit
    write(repo2, "src/app.py", "x = 2\n")
    assert commit(repo2, "-am", "feat: after the code review\n\nSpec: docs/work/demo/README.md").returncode == 0
    git(repo2, "stash", "pop", "-q")
    assert land(repo2, "docs: ship demo").returncode == 0


def research_item(repo: Path) -> None:
    """The demo item rewritten as a valid research item at building (no layers; References, Question, Sources,
    Findings, Recommendation), with its evidence declared."""
    p = repo / README_REL
    text = p.read_text(encoding="utf-8")
    head = text[:text.index("\n---\n", 4) + 5]
    head = head.replace("type: feature", "type: research").replace(": added", ": none")
    refs = text[text.index("## References"):text.index("## Operating envelope")]
    body = "# Demo research\n\n" + refs + "## Question\nWhy?\n\n## Sources\nHere.\n\n## Findings\nThis.\n\n## Recommendation\nThat.\n"
    p.write_text(head + body, encoding="utf-8", newline="\n")
    for layer in ("architecture", "components", "functional"):
        (repo / ITEM / f"{layer}.md").unlink()
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "chore: research", "--no-verify")


def test_ac7_a_research_item_ships_on_a_fresh_design_record(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-7: a results re-review
    research_item(repo2)
    r = ship_with(repo2, tmp_path, capsys, "design")
    assert r.returncode == 0, r.stderr


def test_ac7_the_committed_type_not_the_staged_one_decides_what_a_ship_needs(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-7: retyping to research inside the ship commit does not relax the rule (the gate passes the
    # committed type to required_records)
    staged_ship(repo2)
    p = repo2 / README_REL
    p.write_text(p.read_text(encoding="utf-8").replace("type: feature", "type: research"), encoding="utf-8", newline="\n")
    stage_all(repo2)
    code, _, err = do_write(capsys, repo2, tmp_path, kind="design")
    assert code == 0, err
    stage_all(repo2)
    tree, edges = sc().IndexTree(repo2), [["building", "shipped"]]
    assert rr().required_records(tree, ITEM, edges) is None  # judged by the staged type alone: a research item
    assert "needs a fresh code review" in rr().required_records(tree, ITEM, edges, item_type="feature")


def test_ac7_the_gate_hands_required_records_the_committed_type_and_the_edges(repo2: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # review-records/AC-7, AC-8: the wiring between spec_gate and review_record
    staged_ship(repo2)
    p = repo2 / README_REL
    p.write_text(p.read_text(encoding="utf-8").replace("type: feature", "type: research"), encoding="utf-8", newline="\n")
    stage_all(repo2)
    seen = []
    monkeypatch.setattr(rr(), "required_records", lambda tree, item, edges, item_type=None: seen.append((item, edges, item_type)))
    monkeypatch.setattr(sc(), "check_work_item", lambda *a, **k: ([], []))  # the tier is not under test
    monkeypatch.chdir(repo2)
    gate = importlib_gate()
    gate.lifecycle_problem(sc().IndexTree(repo2), gate.staged_readmes(gate.staged_changes()), False)
    assert seen == [(ITEM, [["building", "shipped"]], "feature")]


# ---------------------------------------------------------------- AC-8: edges of a move

def branch_moves(repo: Path, *statuses: str) -> None:
    """On branch `feat`, move the (draft) demo item through `statuses`, bypassing hooks; back on main."""
    git(repo, "checkout", "-q", "-b", "feat")
    for s in statuses:
        if s == "shipped":
            write(repo, f"{ITEM}/evidence/demo.webm", "x")
        set_status(repo, s)
        stage_all(repo)
        git(repo, "commit", "-qm", f"chore: {s}", "--no-verify")
    git(repo, "checkout", "-q", "main")


def test_ac8_a_squash_of_lock_and_build_needs_a_design_record(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-8
    seed_status(repo2, "draft")
    branch_moves(repo2, "spec-locked", "building")
    git(repo2, "merge", "--squash", "-q", "feat")
    refused = commit(repo2, "-m", "docs: squash feat")
    assert refused.returncode != 0 and "needs a fresh design review" in refused.stderr, refused.stderr
    code, _, err = do_write(capsys, repo2, tmp_path)
    assert code == 0, err
    assert land(repo2, "docs: squash feat").returncode == 0


@pytest.mark.parametrize("edited", [False, True])
def test_ac8_an_item_imported_at_shipped_by_a_merge_lands_unless_the_merge_changed_it(repo2: Path, tmp_path: Path, capsys,
                                                                                    clock, edited: bool) -> None:
    # review-records/AC-8
    base = head_sha(repo2)
    git(repo2, "rm", "-rq", ITEM)
    git(repo2, "commit", "-qm", "chore: no item yet", "--no-verify")
    git(repo2, "checkout", "-q", "-b", "feat", base)
    write(repo2, f"{ITEM}/evidence/demo.webm", "x")
    set_status(repo2, "shipped")
    stage_all(repo2)
    for kind in ("design", "code"):
        code, out, err = do_write(capsys, repo2, tmp_path, kind=kind, commit_sha=base if kind == "code" else None,
                                  name=f"{kind}.md")
        assert code == 0, err
    stage_all(repo2)
    git(repo2, "commit", "-qm", "chore: shipped on a branch", "--no-verify")
    git(repo2, "checkout", "-q", "main")
    git(repo2, "merge", "--no-commit", "--no-ff", "feat", check=False)
    git(repo2, "checkout", "feat", "--", ITEM)
    if edited:  # the merge resolution writes content neither side reviewed
        edit_item(repo2, "components.md", "\nEdited while merging.\n")
    stage_all(repo2)
    r = commit(repo2, "-m", "Merge branch 'feat'")
    if edited:
        assert r.returncode != 0 and "record is stale" in r.stderr, r.stderr
    else:
        assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("target", ["spec-locked", "building"])
def test_ac8_repairing_an_unreadable_head_status_needs_the_records_of_the_chain(repo2: Path, tmp_path: Path, capsys, clock,
                                                                               target: str) -> None:
    # review-records/AC-8
    p = repo2 / README_REL
    good = p.read_text(encoding="utf-8")
    p.write_text(good.replace("status: building", "status: [building"), encoding="utf-8", newline="\n")
    stage_all(repo2)
    git(repo2, "commit", "-qm", "chore: break", "--no-verify")
    p.write_text(good.replace("status: building", f"status: {target}"), encoding="utf-8", newline="\n")
    stage_all(repo2)
    refused = commit(repo2, "-m", "docs: repair")
    assert refused.returncode != 0 and "needs a fresh design review" in refused.stderr, refused.stderr
    code, _, err = do_write(capsys, repo2, tmp_path)
    assert code == 0, err
    assert land(repo2, "docs: repair").returncode == 0


def test_ac8_two_branches_that_lock_differently_need_a_record_for_the_merged_content(repo2: Path, tmp_path: Path, capsys,
                                                                                     clock) -> None:
    # review-records/AC-8
    seed_status(repo2, "draft")
    for branch, text in (("a", "Content from branch a.\n"), ("b", "Content from branch b.\n")):
        git(repo2, "checkout", "-q", "-b", branch, "main")
        (repo2 / ITEM / "functional.md").write_text(
            (repo2 / ITEM / "functional.md").read_text(encoding="utf-8") + text, encoding="utf-8", newline="\n")
        set_status(repo2, "spec-locked")
        stage_all(repo2)
        code, _, err = do_write(capsys, repo2, tmp_path, name=f"{branch}.md")
        assert code == 0, err
        stage_all(repo2)
        git(repo2, "commit", "-qm", f"chore: lock on {branch}", "--no-verify")
    git(repo2, "checkout", "-q", "a")
    merged = git(repo2, "merge", "--no-commit", "--no-ff", "b", check=False)
    assert "CONFLICT" in merged.stdout, merged.stdout
    (repo2 / ITEM / "functional.md").write_text(
        (repo2 / ITEM / "functional.md").read_text(encoding="utf-8").split("<<<<<<<")[0] + "Merged content.\n",
        encoding="utf-8", newline="\n")
    stage_all(repo2)
    refused = commit(repo2, "-m", "Merge branch 'b' into a")
    assert refused.returncode != 0 and "record is stale" in refused.stderr, refused.stderr
    clock.set("2030-01-01T00:00:00Z")
    code, _, err = do_write(capsys, repo2, tmp_path, name="merged.md")
    assert code == 0, err
    assert land(repo2, "Merge branch 'b' into a").returncode == 0


def test_ac8_merging_main_into_a_branch_that_was_built_after_its_lock_is_not_a_lock_move(repo2: Path, tmp_path: Path, capsys,
                                                                                         clock) -> None:
    # review-records/AC-8 + AC-9: free edits at a status, then a merge that moves nothing, need no record
    seed_status(repo2, "draft")
    git(repo2, "checkout", "-q", "-b", "feat")
    set_status(repo2, "spec-locked")
    stage_all(repo2)
    do_write(capsys, repo2, tmp_path)
    stage_all(repo2)
    git(repo2, "commit", "-qm", "chore: lock", "--no-verify")
    edit_item(repo2)
    git(repo2, "commit", "-qm", "docs: free edit at spec-locked", "--no-verify")
    git(repo2, "checkout", "-q", "main")
    write(repo2, "NOTES.md", "main moves on\n")
    git(repo2, "add", "-A")
    git(repo2, "commit", "-qm", "docs: notes", "--no-verify")
    git(repo2, "checkout", "-q", "feat")
    r = git(repo2, "merge", "--no-ff", "-q", "-m", "Merge main", "main", check=False)
    assert r.returncode == 0, r.stderr


# ---------------------------------------------------------------- AC-9: no check at rest

@pytest.mark.parametrize("status", ["draft", "spec-locked", "building"])
def test_ac9_edits_at_a_status_need_no_record(repo2: Path, status: str) -> None:
    # review-records/AC-9
    seed_status(repo2, status)
    edit_item(repo2, "components.md", "\nOne more sentence.\n")
    edit_item(repo2, "README.md", "\nOne more sentence.\n")  # the README is staged too: the gate looks at it, asks no record
    r = commit(repo2, "-m", "docs: edit demo")
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("frm", ["draft", "spec-locked", "building", "shipped"])
def test_ac9_a_move_into_killed_needs_no_record(repo2: Path, frm: str) -> None:
    # review-records/AC-9
    if frm == "shipped":
        write(repo2, f"{ITEM}/evidence/demo.webm", "x")
    seed_status(repo2, frm)
    set_status(repo2, "killed")
    stage_all(repo2)
    r = commit(repo2, "-m", "docs: kill demo")
    assert r.returncode == 0, r.stderr


def test_ac9_a_move_into_promoted_needs_no_record(repo2: Path) -> None:
    # review-records/AC-9
    p = repo2 / README_REL
    p.write_text(p.read_text(encoding="utf-8").replace("  architecture: added", "  architecture: none"), encoding="utf-8")
    (repo2 / ITEM / "architecture.md").unlink()
    p.write_text(p.read_text(encoding="utf-8").replace("type: feature", "type: experiment"), encoding="utf-8", newline="\n")
    seed_status(repo2, "building")
    set_status(repo2, "promoted")
    stage_all(repo2)
    r = commit(repo2, "-m", "docs: promote demo")
    assert r.returncode == 0, r.stderr


# ---------------------------------------------------------------- AC-10: deleting or moving out

def test_ac10_deleting_a_building_readme_is_refused(repo2: Path) -> None:
    # review-records/AC-10
    git(repo2, "rm", "-q", README_REL)
    r = commit(repo2, "-m", "docs: drop demo")
    assert r.returncode != 0 and "deleting or moving a building work item" in r.stderr, r.stderr
    assert "set status: killed instead" in r.stderr


def test_ac10_renaming_a_building_readme_out_of_the_pattern_is_refused(repo2: Path) -> None:
    # review-records/AC-10
    git(repo2, "mv", README_REL, f"{ITEM}/README.old.md")
    r = commit(repo2, "-m", "docs: move readme aside")
    assert r.returncode != 0 and "deleting or moving a building work item" in r.stderr, r.stderr


def test_ac10_replacing_a_building_readme_with_a_symlink_is_refused(repo2: Path) -> None:
    # review-records/AC-10
    add_entry(repo2, "120000", README_REL, b"../elsewhere.md")
    r = commit(repo2, "-m", "docs: link readme")
    assert r.returncode != 0 and "building work item" in r.stderr, r.stderr


def test_ac10_deleting_a_readme_in_a_merge_whose_other_side_moved_it_is_refused(repo2: Path) -> None:
    # review-records/AC-10: draft at HEAD, building at MERGE_HEAD: the later status counts
    seed_status(repo2, "draft")
    git(repo2, "checkout", "-q", "-b", "feat")
    seed_status(repo2, "building")
    git(repo2, "checkout", "-q", "main")
    write(repo2, "NOTES.md", "main moves on\n")
    git(repo2, "add", "-A")
    git(repo2, "commit", "-qm", "docs: notes", "--no-verify")
    git(repo2, "merge", "--no-commit", "--no-ff", "feat")
    git(repo2, "rm", "-q", "-f", README_REL)
    r = commit(repo2, "-m", "Merge branch 'feat'")
    assert r.returncode != 0 and "deleting or moving a building work item" in r.stderr, r.stderr


def test_ac10_a_heavily_edited_move_paired_as_delete_plus_add_gets_the_rename_hint(repo2: Path) -> None:
    # review-records/AC-10
    git(repo2, "mv", ITEM, "docs/work/demo-b")
    new = repo2 / "docs/work/demo-b/README.md"
    new.write_text("---\nid: demo-b\n---\n# Something else entirely\n\n" + "\n".join(f"line {i}" for i in range(40)) + "\n",
                   encoding="utf-8", newline="\n")
    stage_all(repo2)
    r = commit(repo2, "-m", "docs: move and rewrite demo")
    assert r.returncode != 0 and "deleting or moving a building work item" in r.stderr, r.stderr
    assert "rename in its own commit with the README unchanged" in r.stderr


def test_ac10_deleting_a_committed_review_record_is_refused(repo2: Path) -> None:
    # review-records/AC-10
    p = put_record(repo2, rec_name(repo2))
    stage_all(repo2)
    git(repo2, "commit", "-qm", "chore: record", "--no-verify")
    git(repo2, "rm", "-q", f"{REVIEWS}/{p.name}")
    r = commit(repo2, "-m", "docs: drop the record")
    assert r.returncode != 0 and f"review records cannot be deleted: {REVIEWS}/{p.name}" in r.stderr, r.stderr


def test_ac10_deleting_a_readme_whose_status_cannot_be_read_is_refused(repo2: Path) -> None:
    # review-records/AC-10: a damaged item is never taken for a draft
    p = repo2 / README_REL
    p.write_text(p.read_text(encoding="utf-8").replace("status: building", "status: [building"), encoding="utf-8", newline="\n")
    stage_all(repo2)
    git(repo2, "commit", "-qm", "chore: break", "--no-verify")
    git(repo2, "rm", "-q", README_REL)
    r = commit(repo2, "-m", "docs: drop demo")
    assert r.returncode != 0 and "deleting or moving a (unreadable) work item" in r.stderr, r.stderr


def test_ac10_deleting_a_draft_readme_lands(repo2: Path) -> None:
    # review-records/AC-10
    seed_status(repo2, "draft")
    git(repo2, "rm", "-q", README_REL)
    r = commit(repo2, "-m", "docs: drop the draft")
    assert r.returncode == 0, r.stderr


def test_ac10_deleting_a_whole_draft_item_with_a_fix_first_record_lands(repo2: Path) -> None:
    # review-records/AC-10
    seed_status(repo2, "draft")
    put_record(repo2, rec_name(repo2), verdict="fix-first")
    stage_all(repo2)
    git(repo2, "commit", "-qm", "chore: record", "--no-verify")
    git(repo2, "rm", "-rq", ITEM)
    r = commit(repo2, "-m", "docs: drop the draft item")
    assert r.returncode == 0, r.stderr


def test_ac10_deleting_a_record_beside_a_draft_readme_that_stays_is_refused(repo2: Path) -> None:
    # review-records/AC-10: the exception needs the README deleted in the same commit
    seed_status(repo2, "draft")
    p = put_record(repo2, rec_name(repo2))
    stage_all(repo2)
    git(repo2, "commit", "-qm", "chore: record", "--no-verify")
    git(repo2, "rm", "-q", f"{REVIEWS}/{p.name}")
    r = commit(repo2, "-m", "docs: drop the record")
    assert r.returncode != 0 and "review records cannot be deleted" in r.stderr, r.stderr


def test_ac10_renaming_the_item_folder_with_its_readme_unchanged_is_not_a_removal(repo2: Path) -> None:
    # review-records/AC-10: a rename inside the pattern is a move, judged by the lifecycle rules, never a removal
    git(repo2, "mv", ITEM, "docs/work/demo-renamed")
    r = commit(repo2, "-m", "docs: rename the item")
    assert "deleting or moving" not in r.stderr and "cannot be deleted" not in r.stderr, r.stderr


# ---------------------------------------------------------------- AC-11: verify

def three_records(repo: Path) -> dict[str, str]:
    put_record(repo, rec_name(repo), verdict="pass")                                  # fresh
    put_record(repo, rec_name(repo, "design", "-2"), content="sha256:" + "3" * 64)   # stale
    bad_path = put_record(repo, rec_name(repo, "design", "-3"))
    bad_path.write_text("no frontmatter at all\n", encoding="utf-8")                  # invalid
    stage_all(repo)
    git(repo, "commit", "-qm", "chore: records", "--no-verify")
    return {"fresh": f"{REVIEWS}/{rec_name(repo)}", "stale": f"{REVIEWS}/{rec_name(repo, 'design', '-2')}",
            "invalid": f"{REVIEWS}/{rec_name(repo, 'design', '-3')}"}


def test_ac11_verify_shows_fresh_stale_and_invalid_per_tree(repo2: Path, capsys) -> None:
    # review-records/AC-11
    paths = three_records(repo2)
    code, out, err = run(capsys, repo2, "verify", "--tree", "head")
    assert code == 1 and {paths[k]: k for k in paths} == {p: s for p, s in states(out).items() if p in paths.values()}, out
    edit_item(repo2)
    code, out, err = run(capsys, repo2, "verify", "--tree", "index")
    assert code == 1 and states(out)[paths["fresh"]] == "stale" and states(out)[paths["invalid"]] == "invalid"
    code, out, _ = run(capsys, repo2, "verify")  # default is the head tree: the edit is not committed
    assert states(out)[paths["fresh"]] == "fresh"


def test_ac11_a_repo_without_invalid_records_exits_zero(repo2: Path, capsys) -> None:
    # review-records/AC-11
    put_record(repo2, rec_name(repo2))
    put_record(repo2, rec_name(repo2, "design", "-2"), content="sha256:" + "4" * 64)
    code, out, err = run(capsys, repo2, "verify", "--tree", "index")
    assert code == 0 and sorted(states(out).values()) == ["fresh", "stale"], (out, err)


def test_ac11_on_an_unborn_branch_every_record_is_stale(tmp_path: Path, capsys) -> None:
    # review-records/AC-11
    r = tmp_path / "unborn"
    git(tmp_path, "init", "-q", "-b", "main", str(r))
    shutil.copytree(CLAUDE / "tests/fixtures/work-items/base/docs", r / "docs", dirs_exist_ok=True)
    stage_all(r)
    put_record(r, rec_name(r))
    put_record(r, rec_name(r, "design", "-2"), content="sha256:" + "5" * 64)
    stage_all(r)
    code, out, err = run(capsys, r, "verify", "--tree", "head")
    assert code == 0 and set(states(out).values()) == {"stale"} and len(states(out)) == 2, (out, err)


def test_ac11_verify_accepts_the_real_record_the_writer_makes(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-11
    code, out, err = do_write(capsys, repo2, tmp_path)
    assert code == 0, err
    stage_all(repo2)
    code, out, err = run(capsys, repo2, "verify", "--tree", "index")
    assert code == 0 and list(states(out).values()) == ["fresh"], (out, err)


# ---------------------------------------------------------------- AC-12: latency

def test_ac12_hashing_a_twenty_file_staged_item_takes_under_a_second(tmp_path: Path) -> None:
    # review-records/AC-12
    r = golden_repo(tmp_path)
    for i in range(20):
        put_bytes(r, f"layer{i}.md", (f"# file {i}\n" + "line\n" * 200).encode())
    tree = sc().IndexTree(r)
    start = time.perf_counter()
    rr().content_hash(tree, GOLDEN_ITEM)
    assert time.perf_counter() - start < 1.0


# ---------------------------------------------------------------- AC-13: one enum source

def make_toolkit(tmp_path: Path, contract: dict | str | None = None, name: str = "toolkit") -> Path:
    """A copy of the scripts and contracts, so a changed or corrupt contract reaches both the writer and the gate."""
    tk = tmp_path / name
    shutil.copytree(CLAUDE / "scripts", tk / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(CLAUDE / "contracts", tk / "contracts")
    if (CLAUDE / "cache").is_dir():
        shutil.copytree(CLAUDE / "cache", tk / "cache")
    modules = tk / "node_modules"
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(CLAUDE / "node_modules"), str(modules))
    else:
        modules.symlink_to(CLAUDE / "node_modules")
    if contract is not None:
        (tk / "contracts" / "review-record.v1.json").write_text(
            contract if isinstance(contract, str) else json.dumps(contract), encoding="utf-8")
    return tk


def hook_with(repo: Path, tk: Path) -> None:
    hooks = Path(git(repo, "config", "core.hooksPath").stdout.strip())
    (hooks / "commit-msg").write_text(f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" '
                                      f'"{(tk / "scripts" / "spec_gate.py").as_posix()}" "$1"\n', encoding="utf-8", newline="\n")


def contract_with_verdicts(verdicts: list[str]) -> dict:
    c = json.loads(CONTRACT.read_text(encoding="utf-8"))
    c["properties"]["verdict"]["enum"] = verdicts
    return c


def test_ac13_the_writer_and_the_gate_both_read_the_verdicts_from_the_contract(repo2: Path, tmp_path: Path) -> None:
    # review-records/AC-13
    base = json.loads(CONTRACT.read_text(encoding="utf-8"))["properties"]["verdict"]["enum"]
    tk = make_toolkit(tmp_path, contract_with_verdicts([*base, "approve-with-nits"]))
    hook_with(repo2, tk)
    staged_lock(repo2)
    h = item_hash(repo2)
    report = put_report(tmp_path, good_report(h, "approve-with-nits"))
    args = ["write", "--item", ITEM, "--kind", "design", "--reviewer", REVIEWER, "--report", str(report)]
    ok = cli(repo2, *args, script=tk / "scripts" / "review_record.py")
    assert ok.returncode == 0, ok.stderr  # the writer accepts the new value
    gate = land(repo2)
    assert gate.returncode != 0 and "newest design record is approve-with-nits" in gate.stderr, gate.stderr
    # ... and the shipped contract, which lacks it, rejects it in both
    refused = cli(repo2, *args)
    assert refused.returncode == 1 and "VERDICT" in refused.stderr


def test_ac13_a_verdict_removed_from_the_contract_is_rejected_by_both(repo2: Path, tmp_path: Path) -> None:
    # review-records/AC-13
    tk = make_toolkit(tmp_path, contract_with_verdicts(["pass", "fix-first"]))
    hook_with(repo2, tk)
    staged_lock(repo2)
    report = put_report(tmp_path, good_report(item_hash(repo2), "block"))
    refused = cli(repo2, "write", "--item", ITEM, "--kind", "design", "--reviewer", REVIEWER, "--report", str(report),
                  script=tk / "scripts" / "review_record.py")
    assert refused.returncode == 1 and "VERDICT" in refused.stderr
    put_record(repo2, rec_name(repo2), verdict="block")
    gate = land(repo2)
    assert gate.returncode != 0 and "record invalid" in gate.stderr, gate.stderr


def test_ac13_the_kinds_come_from_the_contract_too(repo2: Path, tmp_path: Path, capsys) -> None:
    # review-records/AC-13
    c = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert c["properties"]["kind"]["enum"] == ["design", "code", "verify"]
    assert c["properties"]["verdict"]["enum"] == ["pass", "fix-first", "block"]
    assert c["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_ac13_no_module_keeps_its_own_verdict_or_kind_list() -> None:
    # review-records/AC-13 (fitness): two verdict or kind words on one line is a list outside the contract
    words = ("pass", "fix-first", "block", "design", "code", "verify")
    for module in ("review_record.py", "spec_gate.py"):
        for n, line in enumerate((CLAUDE / "scripts" / module).read_text(encoding="utf-8").splitlines(), 1):
            quoted = [w for w in words if re.search(rf"""["']{w}["']""", line)]
            assert len(quoted) < 2, f"{module}:{n}: {line.strip()}"


# ---------------------------------------------------------------- AC-14: a broken file or git never blocks at rest

def test_ac14_a_corrupt_contract_and_record_block_only_the_lock_and_ship_edges(repo2: Path, tmp_path: Path) -> None:
    # review-records/AC-14
    tk = make_toolkit(tmp_path, "{ this is not json")
    hook_with(repo2, tk)
    bad = repo2 / REVIEWS / "2026-10-01-design-00000000.md"
    bad.parent.mkdir(parents=True)
    bad.write_text("\x00 corrupt\n", encoding="utf-8")
    stage_all(repo2)
    git(repo2, "commit", "-qm", "chore: corrupt record", "--no-verify")
    edit_item(repo2, "components.md", "\nan edit at building\n")
    assert commit(repo2, "-m", "docs: edit at rest").returncode == 0  # no lock or ship edge: nothing is read
    seed_status(repo2, "draft")
    set_status(repo2, "spec-locked")
    stage_all(repo2)
    r = commit(repo2, "-m", "docs: lock")
    assert r.returncode != 0 and "review-record.v1.json" in r.stderr, r.stderr


def test_ac14_a_broken_record_module_blocks_only_the_lock_and_ship_edges(repo2: Path, tmp_path: Path) -> None:
    # review-records/AC-14 (FR-11): the module is imported only when an edge needs it
    tk = make_toolkit(tmp_path)
    (tk / "scripts" / "review_record.py").write_text("raise RuntimeError('broken record module')\n", encoding="utf-8")
    hook_with(repo2, tk)
    edit_item(repo2, "README.md", "\nAn edit at building.\n")
    assert commit(repo2, "-m", "docs: edit at rest").returncode == 0
    set_status(repo2, "killed")
    stage_all(repo2)
    assert commit(repo2, "-m", "docs: kill demo").returncode == 0  # a move into killed needs no record
    seed_status(repo2, "draft")
    set_status(repo2, "spec-locked")
    stage_all(repo2)
    r = commit(repo2, "-m", "docs: lock")
    assert r.returncode != 0 and "broken record module" in r.stderr, r.stderr


def test_ac14_a_missing_index_file_is_a_named_git_failure(repo2: Path, tmp_path: Path) -> None:
    # review-records/AC-14
    staged_lock(repo2)
    msg = tmp_path / "msg.txt"
    msg.write_text("docs: lock\n", encoding="utf-8")
    env = {**ENV, "GIT_INDEX_FILE": str(tmp_path / "no-such-dir" / "index")}
    r = subprocess.run([sys.executable, str(GATE), str(msg)], cwd=repo2, capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 1 and "GIT_INDEX_FILE" in r.stderr and "fails closed" in r.stderr, r.stderr


def test_ac14_a_timeout_reading_the_tree_is_refused_by_name(repo2: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                           capsys) -> None:
    # review-records/AC-14
    staged_lock(repo2)
    put_record(repo2, rec_name(repo2))
    stage_all(repo2)
    tree = sc().IndexTree(repo2)

    def timed_out(self, paths):
        raise OSError("git cat-file timed out")

    monkeypatch.setattr(sc().IndexTree, "read_many", timed_out)
    with pytest.raises(OSError, match="timed out"):
        rr().required_records(tree, ITEM, [["draft", "spec-locked"]])
    msg = tmp_path / "msg.txt"
    msg.write_text("docs: lock\n", encoding="utf-8")
    monkeypatch.chdir(repo2)
    gate = importlib_gate()
    assert gate.main([str(msg)]) == 1
    assert "timed out" in capsys.readouterr().err


def importlib_gate():
    import importlib
    return importlib.import_module("spec_gate")


def test_ac14_verify_on_an_unreadable_index_exits_one_naming_the_failure(repo2: Path, tmp_path: Path) -> None:
    # review-records/AC-14
    r = cli(repo2, "verify", "--tree", "index", env={"GIT_INDEX_FILE": str(tmp_path / "no-such-dir" / "index")})
    assert r.returncode == 1 and "GIT_INDEX_FILE" in r.stderr, r.stderr


def test_ac14_the_gate_does_not_import_the_record_module_unless_an_edge_needs_it(repo2: Path, tmp_path: Path,
                                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    # review-records/AC-14 (FR-11)
    text = (CLAUDE / "scripts" / "spec_gate.py").read_text(encoding="utf-8")
    assert not re.search(r"^(import review_record|from review_record)", text, re.M)
    assert re.search(r"^\s+(import review_record|from review_record import)", text, re.M)


# ---------------------------------------------------------------- AC-15: the instructions agree

def test_ac15_the_reviewer_and_the_playbook_require_the_echo_and_name_one_hash_rule() -> None:
    # review-records/AC-15
    reviewer = (CLAUDE / "agents" / "reviewer.md").read_text(encoding="utf-8")
    playbook = (CLAUDE / "playbooks" / "agent-dispatch.md").read_text(encoding="utf-8")
    for label, text in (("agents/reviewer.md", reviewer), ("playbooks/agent-dispatch.md", playbook)):
        assert "REVIEWED: sha256:<hex>" in text, label
        assert "REVIEWED-COMMIT:" in text, label
    assert "review_record.py hash" in playbook and "FR-1" in playbook
    assert re.search(r"only hash rule", playbook)
    assert "sha256sum" not in playbook and "hashlib" not in playbook  # the playbook restates no rule of its own


# ---------------------------------------------------------------- fix round 1 (code review R1, R2)

def lock_build_refine_on_main(repo: Path, tmp_path: Path, capsys) -> None:
    """On main (hooks bypassed, as each commit passed the gate on its own branch): lock with a fresh record, build,
    then refine functional.md, so the final content is newer than the record."""
    set_status(repo, "spec-locked")
    stage_all(repo)
    code, _, err = do_write(capsys, repo, tmp_path)
    assert code == 0, err
    for status in (None, "building"):
        if status:
            set_status(repo, status)
        stage_all(repo)
        git(repo, "commit", "-qm", f"chore: {status or 'lock'}", "--no-verify")
    edit_item(repo)
    git(repo, "commit", "-qm", "docs: refine", "--no-verify")


def test_ac8_merging_main_into_a_branch_after_main_locked_built_and_refined_lands(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-8 (code review R1): the merged item equals MERGE_HEAD's, whose history already passed the gate
    seed_status(repo2, "draft")
    git(repo2, "branch", "feat")
    lock_build_refine_on_main(repo2, tmp_path, capsys)
    git(repo2, "checkout", "-q", "feat")
    write(repo2, "NOTES.md", "branch work\n")
    git(repo2, "add", "-A")
    git(repo2, "commit", "-qm", "docs: notes", "--no-verify")
    r = git(repo2, "merge", "--no-ff", "-q", "-m", "Merge main", "main", check=False)
    assert r.returncode == 0, r.stderr


def test_ac8_merging_main_into_a_branch_that_lacks_the_item_lands(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-8 (code review R1): the item is absent from the branch HEAD (an import)
    git(repo2, "rm", "-rq", ITEM)
    git(repo2, "commit", "-qm", "chore: no item yet", "--no-verify")
    git(repo2, "branch", "feat")
    git(repo2, "checkout", "-q", "main~1", "--", ITEM)
    set_status(repo2, "draft")
    stage_all(repo2)
    git(repo2, "commit", "-qm", "chore: draft", "--no-verify")
    lock_build_refine_on_main(repo2, tmp_path, capsys)
    git(repo2, "checkout", "-q", "feat")
    write(repo2, "NOTES.md", "branch work\n")
    git(repo2, "add", "-A")
    git(repo2, "commit", "-qm", "docs: notes", "--no-verify")
    r = git(repo2, "merge", "--no-ff", "-q", "-m", "Merge main", "main", check=False)
    assert r.returncode == 0, r.stderr


def test_ac8_a_merge_whose_item_equals_neither_side_is_still_checked(repo2: Path, tmp_path: Path, capsys, clock) -> None:
    # review-records/AC-8: the equal-to-a-side exemption does not cover a merge that produces new content
    seed_status(repo2, "draft")
    git(repo2, "branch", "feat")
    lock_build_refine_on_main(repo2, tmp_path, capsys)
    git(repo2, "checkout", "-q", "feat")
    edit_item(repo2, "components.md", "\nBranch-only change.\n")
    git(repo2, "commit", "-qm", "docs: branch edit", "--no-verify")
    git(repo2, "merge", "--no-ff", "--no-commit", "main")
    r = commit(repo2, "-m", "Merge main")
    assert r.returncode != 0 and "record is stale" in r.stderr, r.stderr


def commit_legacy_readme(repo: Path, text: str) -> str:
    rel = "docs/work/legacy/README.md"
    write(repo, rel, text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "chore: legacy", "--no-verify")
    return rel


@pytest.mark.parametrize("text", ["# Legacy plan\n", "", "Just prose.\n\n---\nnot frontmatter\n"])
def test_ac10_deleting_a_legacy_readme_without_frontmatter_lands(repo2: Path, text: str) -> None:
    # review-records/AC-10 (code review R2): no frontmatter block, so not a v2 work item
    rel = commit_legacy_readme(repo2, text)
    git(repo2, "rm", "-q", rel)
    r = commit(repo2, "-m", "docs: drop the legacy plan")
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("front", ["id: x\nowner: me", "id: x\nstatus: weird", "id: x\nstatus: building"])
def test_ac10_deleting_a_readme_with_frontmatter_but_no_draft_status_is_refused(repo2: Path, front: str) -> None:
    # review-records/AC-10 (code review R2): readable frontmatter, status missing, unknown or past draft
    rel = commit_legacy_readme(repo2, f"---\n{front}\n---\n# Plan\n")
    git(repo2, "rm", "-q", rel)
    r = commit(repo2, "-m", "docs: drop the plan")
    assert r.returncode != 0 and "deleting or moving a" in r.stderr, r.stderr
