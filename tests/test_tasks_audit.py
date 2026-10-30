"""Tests for scripts/tasks_audit.py: the audit rules over injected task rows (no Windows needed), and the CLI.

    python -m pytest ~/.claude/tests/test_tasks_audit.py -q
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import tasks_audit as ta  # noqa: E402
from upkeep_config import DEFAULTS  # noqa: E402

NOW = datetime.fromisoformat("2026-10-29T12:00:00-07:00")


def iso(delta_days: float) -> str:
    return (NOW + timedelta(days=delta_days)).isoformat(timespec="seconds")


def task(name="T", state="Ready", last=-1, result=0, nxt=1, triggers=1) -> dict:
    return {"name": name, "state": state, "lastRun": None if last is None else iso(last), "lastResult": result,
            "nextRun": None if nxt is None else iso(nxt), "triggerCount": triggers}


def kinds(tasks: list[dict]) -> set[str]:
    return {f"{f['kind']}:{f['task']}" for f in ta.audit(tasks, DEFAULTS, NOW)}


def test_healthy_ready_task_has_no_findings():
    assert kinds([task()]) == set()


def test_nonzero_last_result_is_failing_but_running_and_not_yet_run_are_not():
    assert kinds([task("bad", result=1)]) == {"failing:bad"}
    assert kinds([task("running", result=267009), task("fresh", result=267011)]) == set()


def test_disabled_longer_than_the_window_is_dead_and_recently_disabled_is_not():
    assert kinds([task("old", state="Disabled", last=-60, nxt=None)]) == {"disabled-long:old"}
    assert kinds([task("recent", state="Disabled", last=-3, nxt=None)]) == set()


def test_never_run_enabled_task_is_dead():
    never = task("never", last=-9999, result=267011, nxt=1)
    assert kinds([never]) == {"never-run:never"}


def test_next_run_beyond_a_year_is_a_dead_trigger():
    assert kinds([task("far", nxt=26000)]) == {"next-run-far:far"}


def test_vendor_updater_tasks_are_ignored():
    assert kinds([task("OneDrive Standalone", last=-9999, result=267011)]) == set()


def test_findings_carry_a_stable_id_and_detail():
    f = ta.audit([task("bad", result=1)], DEFAULTS, NOW)[0]
    assert f["id"] == "tasks-audit:failing:bad" and "0x1" in f["detail"]


def test_report_marks_only_findings_absent_from_the_previous_report_as_new():
    rows = [task("bad", result=1), task("far", nxt=26000)]
    first = ta.report(rows, DEFAULTS, NOW, None)
    assert len(first["newFindings"]) == 2
    second = ta.report(rows, DEFAULTS, NOW, {f["id"] for f in first["findings"]})
    assert second["newFindings"] == []


def test_cli_reads_a_tasks_file_and_writes_the_report(tmp_path: Path):
    src = tmp_path / "tasks.json"
    src.write_text(json.dumps([task("bad", result=1)]), encoding="utf-8")
    out = tmp_path / "state" / "tasks-audit.json"
    cmd = [sys.executable, str(Path(ta.__file__)), "--root", str(tmp_path), "--tasks-file", str(src), "--json"]
    report = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
    assert report["total"] == 1 and out.with_name("tasks-audit.pending.json").exists()


def test_empty_inventory_prints_an_empty_json_array_not_null():
    inv = Path(ta.__file__).with_name("tasks_inventory.ps1")
    out = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(inv),
                          "-TaskPath", r"\NoSuchFolder" + "\\"], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == []
