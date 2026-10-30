"""The seen-vs-delivered contract shared by the upkeep scripts: a run writes a PENDING report; the committed report
(the baseline for "new") only moves on `--commit`, which Cortex calls after a successful TeleFi publish. A failed
publish therefore re-alerts on the next run. Also: atomic state writes, unreadable baselines, no console windows.

    python -m pytest ~/.claude/tests/test_upkeep_state.py -q
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import ledger_draft  # noqa: E402
import tasks_audit  # noqa: E402
import upkeep_config as uc  # noqa: E402

TASKS = [{"name": "bad", "state": "Ready", "lastRun": "2026-10-29T10:00:00-07:00", "lastResult": 1,
          "nextRun": "2026-10-30T10:00:00-07:00", "triggerCount": 1}]


def test_write_atomic_replaces_content_and_leaves_no_temp_file(tmp_path: Path):
    target = tmp_path / "s" / "r.json"
    uc.write_atomic(target, '{"a": 1}')
    uc.write_atomic(target, '{"a": 2}')
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 2}
    assert [p.name for p in target.parent.iterdir()] == ["r.json"]


def test_previous_ids_missing_or_corrupt_baseline_is_none_not_a_crash(tmp_path: Path):
    f = tmp_path / "r.json"
    assert uc.previous_ids(f) is None
    f.write_text("{torn", encoding="utf-8")
    assert uc.previous_ids(f) is None
    f.write_text(json.dumps({"findings": [{"id": "a"}, {"id": "b"}]}), encoding="utf-8")
    assert uc.previous_ids(f) == {"a", "b"}


def test_commit_pending_promotes_the_pending_report_once(tmp_path: Path):
    out = tmp_path / "r.json"
    assert uc.commit_pending(out) is False
    uc.pending_path(out).write_text('{"findings": []}', encoding="utf-8")
    assert uc.commit_pending(out) is True
    assert out.exists() and not uc.pending_path(out).exists()


def cli(script: str, *args: str) -> dict:
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *args, "--json"], capture_output=True, text=True,
                       check=True)
    return json.loads(r.stdout) if r.stdout.strip() else {}


def commit(script: str, *args: str) -> None:
    subprocess.run([sys.executable, str(SCRIPTS / script), *args, "--commit"], check=True, capture_output=True)


@pytest.fixture(params=["harness_lint", "tasks_audit", "projects_sweep"])
def scenario(request, tmp_path: Path):
    root = tmp_path / "claude"
    (root / "projects" / "C--empty-old").mkdir(parents=True)
    import os
    import time
    old = time.time() - 30 * 86400
    os.utime(root / "projects" / "C--empty-old", (old, old))
    (root / "new.txt").write_text("n\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / ".gitignore").write_text("state/\n", encoding="utf-8")
    tasks = tmp_path / "tasks.json"
    tasks.write_text(json.dumps(TASKS), encoding="utf-8")
    args = ["--root", str(root)] + (["--tasks-file", str(tasks)] if request.param == "tasks_audit" else [])
    return request.param + ".py", args, root


def test_a_run_without_commit_re_alerts_next_run_and_commit_silences_it(scenario):
    script, args, root = scenario
    first = cli(script, *args)
    assert first["newFindings"]
    second = cli(script, *args)  # nothing was delivered/committed: still new
    assert [f["id"] for f in second["newFindings"]] == [f["id"] for f in first["newFindings"]]
    commit(script, *args)
    assert cli(script, *args)["newFindings"] == []


def test_fixed_then_reappears_re_alerts(scenario):
    script, args, root = scenario
    cli(script, *args)
    commit(script, *args)
    if script == "tasks_audit.py":
        tasks = Path(args[args.index("--tasks-file") + 1])
        tasks.write_text("[]", encoding="utf-8")
    elif script == "projects_sweep.py":
        (root / "projects" / "C--empty-old").rmdir()
    else:
        (root / "new.txt").unlink()
    assert cli(script, *args)["newFindings"] == []
    commit(script, *args)  # the fixed state is delivered too
    if script == "tasks_audit.py":
        tasks.write_text(json.dumps(TASKS), encoding="utf-8")
    elif script == "projects_sweep.py":
        import os
        import time
        d = root / "projects" / "C--empty-old"
        d.mkdir()
        old = time.time() - 30 * 86400
        os.utime(d, (old, old))
    else:
        (root / "new.txt").write_text("n\n", encoding="utf-8")
    assert cli(script, *args)["newFindings"]


def test_a_corrupt_committed_report_is_treated_as_no_baseline(scenario):
    script, args, root = scenario
    cli(script, *args)
    commit(script, *args)
    name = script.replace("_", "-").removesuffix(".py")
    (root / "state" / f"{name}.json").write_text("{torn", encoding="utf-8")
    assert cli(script, *args)["newFindings"]


def test_child_processes_get_no_console_window_on_windows(monkeypatch):
    seen = []

    def fake_run(cmd, **kw):
        seen.append(kw.get("creationflags"))
        return subprocess.CompletedProcess(cmd, 0, stdout=b"[]" if cmd[0].startswith("powershell") else "", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    tasks_audit.collect()
    from datetime import date
    ledger_draft.commits(Path("."), date(2026, 10, 28))
    assert seen == [uc.HIDDEN["creationflags"]] * 2
