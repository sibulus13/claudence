"""D:/repo harness router: give a session started in D:/repo each project's own memory and hooks.

Registered only in D:/repo/.claude/settings.json, so it never runs in a session started inside a project
(that session loads the project's harness natively). Design: ~/.claude/docs/fleet/HARNESS_FROM_ROOT.md.

    python harness_router.py pre|post   (PreToolUse / PostToolUse, hook JSON on stdin)

- First touch of a project: inject its memory index + its SessionStart hook output (additionalContext).
- Every tool call on a project path: run the project's own PreToolUse/PostToolUse hooks whose matcher fits,
  with cwd and CLAUDE_PROJECT_DIR = the project root; exit 2 and deny decisions pass through (fail closed).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("D:/repo")
STATE_DIR = Path.home() / ".claude" / "state"
PROJECTS = Path.home() / ".claude" / "projects"
INDEX_CAP_CHARS = 6000
HOOK_TIMEOUT_S = 60
PATH_IN_TEXT = re.compile(r"[A-Za-z]:[\\/]+repo[\\/][^\s\"'|;&<>]+", re.I)


def project_root(p: str) -> Path | None:
    try:
        path = Path(p.strip("\"'")).resolve()
        path.relative_to(ROOT.resolve())
    except (ValueError, OSError):
        return None
    for d in [path, *path.parents]:
        if d == ROOT.resolve() or d == d.parent:
            return None
        if (d / ".git").exists() and "_Archive" not in d.parts:
            return d
    return None


def touched_paths(event: dict) -> list[str]:
    ti = event.get("tool_input") or {}
    found = [ti[k] for k in ("file_path", "path", "notebook_path") if isinstance(ti.get(k), str)]
    found += PATH_IN_TEXT.findall(str(ti.get("command") or ""))
    return found


def memory_dir(root: Path) -> Path:
    return PROJECTS / re.sub(r"[^A-Za-z0-9]", "-", str(root).replace("/", "\\")) / "memory"


def load_state(session: str) -> dict:
    f = STATE_DIR / f"router-{session}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"touched": []}


def save_state(session: str, state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / f"router-{session}.json").write_text(json.dumps(state), encoding="utf-8")


def project_hooks(root: Path, event_name: str) -> list[tuple[str, str]]:
    f = root / ".claude" / "settings.json"
    if not f.exists():
        return []
    groups = json.loads(f.read_text(encoding="utf-8")).get("hooks", {}).get(event_name, [])
    return [(g.get("matcher") or "", h["command"]) for g in groups for h in g.get("hooks", []) if h.get("command")]


def run_hook(cmd: str, root: Path, payload: dict) -> subprocess.CompletedProcess:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root).replace("\\", "/")}
    shell = shutil.which("bash") or "bash"
    return subprocess.run([shell, "-c", cmd], input=json.dumps(payload), capture_output=True, text=True,
                          cwd=root, env=env, timeout=HOOK_TIMEOUT_S)


def first_touch_context(root: Path, event: dict) -> str:
    parts = [f"[router] First touch of {root.as_posix()} from a D:/repo session: its harness follows."]
    idx = memory_dir(root) / "MEMORY.md"
    if idx.exists():
        parts.append(f"Project memory index ({idx.as_posix()}; open a note there when relevant):\n"
                     + idx.read_text(encoding="utf-8")[:INDEX_CAP_CHARS])
    for _, cmd in project_hooks(root, "SessionStart"):
        r = run_hook(cmd, root, {**event, "hook_event_name": "SessionStart", "source": "startup",
                                 "cwd": str(root)})
        out = r.stdout.strip()
        try:
            out = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
        if out:
            parts.append(f"Project SessionStart hook output:\n{out[:INDEX_CAP_CHARS]}")
    return "\n\n".join(parts)


def main() -> int:
    phase = sys.argv[1] if len(sys.argv) > 1 else "post"
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    if project_root(event.get("cwd") or ""):
        return 0  # session started inside a project: its harness is native
    roots = []
    for p in touched_paths(event):
        r = project_root(p)
        if r and r not in roots:
            roots.append(r)
    if not roots:
        return 0
    event_name = "PreToolUse" if phase == "pre" else "PostToolUse"
    tool = event.get("tool_name") or ""
    context = []
    for root in roots:
        for matcher, cmd in project_hooks(root, event_name):
            if matcher and not re.fullmatch(matcher, tool):
                continue
            r = run_hook(cmd, root, {**event, "cwd": str(root)})
            if r.returncode == 2:
                sys.stderr.write(f"[{root.name} hook] {r.stderr.strip()}")
                return 2
            if '"deny"' in r.stdout:
                print(r.stdout.strip())
                return 0
            if r.stdout.strip():
                context.append(f"[{root.name} {event_name} hook] {r.stdout.strip()[:2000]}")
    if phase == "post":
        session = event.get("session_id") or "unknown"
        state = load_state(session)
        for root in roots:
            if root.as_posix() not in state["touched"]:
                state["touched"].append(root.as_posix())
                context.insert(0, first_touch_context(root, event))
        save_state(session, state)
    if context:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event_name,
                                                 "additionalContext": "\n\n".join(context)}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
