"""fleet-docs-home: one resolver for the fleet docs location (scripts/fleet_paths.py) and every reader of it.

    python -m pytest ~/.claude/tests/test_fleet_docs.py -q

fleet-docs-home/AC-11 (nothing else regresses) is proven by running the whole tests directory against this change.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME / "scripts"))
sys.path.insert(0, str(HOME / "hooks"))

import fleet_paths  # noqa: E402


def py(code: str, **env: str) -> str:
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30, check=True,
                         env={"PATH": "", "SYSTEMROOT": "C:/Windows", "PYTHONPATH": str(HOME / "scripts"), **env})
    return out.stdout.strip()


def test_resolver(tmp_path: Path, monkeypatch):
    """fleet-docs-home/AC-1: FLEET_ROOT and FLEET_DOCS override; empty or unset falls back to D:/repo and REPO_ROOT/docs."""
    code = "import fleet_paths as f; print(f.REPO_ROOT.as_posix()); print(f.fleet_docs_dir().as_posix())"
    assert py(code).splitlines() == ["D:/repo", "D:/repo/docs"]
    assert py(code, FLEET_ROOT="", FLEET_DOCS="").splitlines() == ["D:/repo", "D:/repo/docs"]
    root = (tmp_path / "r").as_posix()
    assert py(code, FLEET_ROOT=root).splitlines() == [root, f"{root}/docs"]
    docs = (tmp_path / "d").as_posix()
    assert py(code, FLEET_ROOT=root, FLEET_DOCS=docs).splitlines() == [root, docs]
    monkeypatch.setenv("FLEET_DOCS", str(tmp_path))  # read at call time, so tests can retarget it
    assert fleet_paths.fleet_docs_dir() == tmp_path


def test_guard_shares_repo_root(tmp_path: Path):
    """fleet-docs-home/AC-1: guard imports REPO_ROOT (same object), has no own literal, and importing it is silent."""
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import guard, fleet_paths; "
            "print(guard.REPO_ROOT is fleet_paths.REPO_ROOT)")
    assert py(code.replace("sys.argv[1]", repr(str(HOME / "hooks")))) == "True"
    assert 'Path("D:/repo")' not in (HOME / "hooks" / "guard.py").read_text(encoding="utf-8")


def test_default_out(tmp_path: Path, monkeypatch):
    """fleet-docs-home/AC-2: fleet_status and path_pins default --out to the resolver; an explicit --out wins."""
    import fleet_status
    import path_pins

    monkeypatch.setenv("FLEET_DOCS", str(tmp_path))
    for mod in (fleet_status, path_pins):
        assert Path(mod.build_parser().parse_args([]).out) == tmp_path
        assert Path(mod.build_parser().parse_args(["--out", "x"]).out) == Path("x")


def test_repo_move_log(tmp_path: Path, monkeypatch):
    """fleet-docs-home/AC-5: repo_move reads path_pins.json and writes MOVES.jsonl under FLEET_DOCS."""
    import repo_move

    monkeypatch.setenv("FLEET_DOCS", str(tmp_path))
    assert repo_move.moves_log() == tmp_path / "MOVES.jsonl"
    assert repo_move.pins_for("a") == ["path_pins.json missing: run path_pins.py"]
    (tmp_path / "path_pins.json").write_text(json.dumps(
        {"projects": [{"project": "a", "other_code": ["f.py"], "machine": [], "tasks": []}]}), encoding="utf-8")
    assert repo_move.pins_for("a") == ["other_code: f.py"]


def test_no_hardcoded_fleet_path():
    """fleet-docs-home/AC-7: no code, test or skill spells the old fleet folder; the ledger skill names $FLEET_DOCS."""
    pattern = re.compile(r"docs/fleet|docs\\fleet|\"docs\"\s*/\s*\"fleet\"")
    hits = []
    for folder in ("scripts", "hooks", "tests", "skills"):
        for f in (HOME / folder).rglob("*"):
            if f.suffix in {".py", ".md", ".ps1", ".json", ".mjs", ".js"} and f.name != Path(__file__).name \
                    and "__pycache__" not in f.parts and pattern.search(f.read_text(encoding="utf-8", errors="replace")):
                hits.append(f.relative_to(HOME).as_posix())
    assert hits == []
    assert "$FLEET_DOCS" in (HOME / "skills" / "ledger" / "SKILL.md").read_text(encoding="utf-8")


def test_gitignore_note():
    """fleet-docs-home/AC-10: the ignore line is gone and a comment says where the folder went."""
    lines = (HOME / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert not [x for x in lines if not x.startswith("#") and "fleet" in x]
    assert any(x.startswith("#") and "FLEET_DOCS" in x for x in lines)


def test_e2e_sessions_get_a_private_fleet_docs(tmp_path: Path, monkeypatch):
    """fleet-docs-home/AC-6: harness_e2e launches its headless sessions with a temp FLEET_DOCS."""
    sys.path.insert(0, str(HOME / "tests"))
    import harness_e2e

    monkeypatch.setenv("FLEET_DOCS", "D:/real-fleet-docs")
    env = harness_e2e.session_env(tmp_path)
    assert env["FLEET_DOCS"] == str(tmp_path / "fleet-docs")
