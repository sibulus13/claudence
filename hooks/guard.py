"""PreToolUse guard: the owner's always/never rules, enforced in code instead of prose.

Reads the hook JSON on stdin; prints a permissionDecision JSON (deny or ask) with the reason, or nothing
(allow). Registered in ~/.claude/settings.json for Bash|PowerShell|Write|Edit|MultiEdit|mcp__* tools.
Design: ~/.claude/docs/fleet/HARNESS_AUDIT.md §3. Tests: ~/.claude/tests/test_guard.py.
Unattended runs (Foreman workers in bypassPermissions, scheduled jobs that set CLAUDE_UNATTENDED=1)
skip the interactive-only rules (background long commands, Notion ask).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path("D:/repo")
LEGACY_CATEGORIES = {"ai", "bot", "data"}
SHELL_TOOLS = {"Bash", "PowerShell"}
EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
NOTION_WRITE = re.compile(r"^mcp__.*notion.*__notion-(create|update|move|duplicate|delete|restore|set|upload|"
                          r"convert|spawn|send|stop|calendar-(create|update|cancel))", re.I)
# Destructive Notion actions always ask, even on approved pages.
NOTION_DESTRUCTIVE = re.compile(r"__notion-(delete|move|restore)", re.I)
# Owner-approved Notion targets (2026-10-27): ids of pages, databases and data sources the owner allows interactive
# writes to without a per-action prompt. Kept outside this public repo.
NOTION_ALLOW_NAME = (".cortex", "notion-allow.json")
HEX_ID = re.compile(r"[0-9a-f]{32}")
GOVERNANCE = re.compile(r"(/|\\)(CLAUDE\.md|AGENTS\.md)$|(/|\\)memory(/|\\)|(/|\\)\.claude(/|\\)settings[^/\\]*\.json$|"
                        r"(/|\\)\.claude(/|\\)(agents|hooks|rules|output-styles)(/|\\)", re.I)
LONG_RUNNERS = re.compile(r"\b(pnpm|npm|yarn)\s+(run\s+)?(build|test)\b|\bnext\s+build\b|\bplaywright\s+test\b|"
                          r"\bvitest\b(?!\s+\S*\.(test|spec)\.)|\bpytest\b|\bnpm\s+test\b")
PYTEST_TARGET = re.compile(r"\.py\b|::|/|\\")
QUOTED = re.compile(r"\"(?:\\.|[^\"\\])*\"|'[^']*'")
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?\n\s*\1\s*(?=\n|$)", re.S)
SINGLE_TEST = re.compile(r"\S+\.(test|spec)\.[cm]?[jt]sx?\b|\btest_\w+\.py\b|::")


def decide(kind: str, reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": kind,
                                   "permissionDecisionReason": reason}}


def unattended(event: dict) -> bool:
    return event.get("permission_mode") == "bypassPermissions" or os.environ.get("CLAUDE_UNATTENDED") == "1"


def approved_notion_ids(path: Path | None = None) -> set[str]:
    try:
        path = path or Path.home().joinpath(*NOTION_ALLOW_NAME)
        return {i.replace("-", "").lower() for i in json.loads(path.read_text(encoding="utf-8")).get("ids", [])}
    except (OSError, ValueError, RuntimeError):  # no file, bad JSON, or no home directory: nothing is approved
        return set()


def targets_only_approved(tool_input: dict, allowed: set[str] | None = None) -> bool:
    """True when every Notion id the call names is on the owner's approved list (and it names at least one)."""
    allowed = approved_notion_ids() if allowed is None else allowed
    ids = set(HEX_ID.findall(json.dumps(tool_input).replace("-", "").lower()))
    return bool(ids) and ids <= allowed


def staged_env_files(cwd: str) -> list[str]:
    r = subprocess.run(["git", "-C", cwd, "diff", "--cached", "--name-only"], capture_output=True, text=True,
                       timeout=10)
    return [f for f in r.stdout.splitlines() if re.search(r"(^|/)\.env(\.[^/]+)?$", f) and "example" not in f]


def has_pnpm_lock(cwd: str) -> bool:
    p = Path(cwd)
    return any((d / "pnpm-lock.yaml").exists() for d in [p, *p.parents])


def bad_repo_target(path: Path) -> bool:
    try:
        rel = path.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        return False
    parts = [x.lower() for x in rel.parts]
    if not parts:
        return False
    return len(parts) == 1 or parts[0] in LEGACY_CATEGORIES or (parts[0] == "web" and parts[1:2] != ["personal"])


def clone_or_init_target(cmd: str, cwd: str) -> Path | None:
    m = re.search(r"\bgit\s+(clone|init)\b(.*)", cmd)
    if not m:
        return None
    try:
        args = [a for a in shlex.split(m.group(2).split("&&")[0].split(";")[0], posix=False) if not a.startswith("-")]
    except ValueError:
        return None
    if m.group(1) == "clone":
        if not args:
            return None
        dest = args[1] if len(args) > 1 else re.sub(r"\.git$", "", args[0].rstrip("/").split("/")[-1])
    else:
        dest = args[0] if args else "."
    dest = dest.strip("\"'")
    return Path(dest) if Path(dest).is_absolute() else Path(cwd) / dest


def check_shell(event: dict) -> dict | None:
    ti = event.get("tool_input") or {}
    # Quoted text (commit messages, echo strings) is data, not flags: match rules against the rest only.
    cmd = QUOTED.sub("''", HEREDOC.sub("<<HEREDOC", ti.get("command") or ""))
    cwd = event.get("cwd") or os.getcwd()
    if re.search(r"\bgit\b[^|;&]*\b(commit|push|merge|rebase)\b[^|;&]*--no-verify", cmd):
        return decide("deny", "--no-verify is never allowed: fix the failing hook instead.")
    if re.search(r"\bgit\b[^|;&]*\bpush\b[^|;&]*(\s--force(?!-with-lease)\b|\s-f\b)[^|;&]*\b(main|master)\b", cmd) or \
       re.search(r"\bgit\b[^|;&]*\bpush\b[^|;&]*\+(main|master)\b", cmd):
        return decide("deny", "Never force-push main/master.")
    if re.search(r"\bgit\b[^|;&]*\bstash\b(?!\s+(list|show)\b)|--autostash", cmd):
        return decide("deny", "No git stash: commit to a branch or use a worktree (stash loses work in shared checkouts).")
    if re.search(r"\bpython3\b", cmd) and event.get("tool_name") == "Bash":
        return decide("deny", "Use `python`, not `python3`, on this machine.")
    if re.search(r"(^|[;&|]\s*)(npm\s+(i|install|add)\b|yarn(\s+add)?\b)", cmd) and has_pnpm_lock(cwd):
        return decide("deny", "This repo uses pnpm (pnpm-lock.yaml present): use pnpm, not npm/yarn.")
    if re.search(r"\|\s*vercel\s+env\s+add\b", cmd):
        return decide("deny", "Piping into `vercel env add` from PowerShell corrupts values: pass the value via a file or --value.")
    if re.search(r"\bgit\b[^|;&]*\bcommit\b", cmd) and (bad := staged_env_files(cwd)):
        return decide("deny", f"Refusing to commit secrets: {', '.join(bad)} is staged. Unstage it.")
    if re.search(r"Register-ScheduledTask|New-ScheduledTaskAction|schtasks(\.exe)?\s+/create", cmd, re.I) and \
       not re.search(r"run[-_]hidden\.vbs|pythonw(\.exe)?", cmd, re.I):
        return decide("deny", "Scheduled tasks must run hidden: action = wscript.exe //B //Nologo <repo>\\scripts\\run-hidden.vbs "
                              "<program> (or pythonw.exe). Then smoke it: Start-ScheduledTask + LastTaskResult 0.")
    target = clone_or_init_target(ti.get("command") or "", cwd)
    if target is not None and bad_repo_target(target):
        return decide("deny", f"New repos go in a theme folder (D:/repo/<Finance|Factory|SaaS|Assistant|Lib|Experiment>/...), "
                              f"not {target}.")
    if not unattended(event) and not ti.get("run_in_background") and LONG_RUNNERS.search(cmd):
        m = re.search(r"\bpytest\b(.*)", cmd)
        single = SINGLE_TEST.search(cmd) or (m and PYTEST_TARGET.search(m.group(1).split("|")[0]))
        if not single:
            return decide("deny", "Long command: rerun it with run_in_background: true (owner rule). A single test "
                                  "file or node id may run in the foreground.")
    return None


def check(event: dict) -> dict | None:
    tool = event.get("tool_name") or ""
    if tool in SHELL_TOOLS:
        return check_shell(event)
    if tool in EDIT_TOOLS and event.get("agent_id"):
        path = (event.get("tool_input") or {}).get("file_path") or ""
        if GOVERNANCE.search(path):
            return decide("deny", "Subagents never edit governance (CLAUDE.md, memory, settings, agents, hooks, rules): "
                                  "return the proposed change to the parent session.")
    if NOTION_WRITE.search(tool) and not unattended(event):
        if not NOTION_DESTRUCTIVE.search(tool) and targets_only_approved(event.get("tool_input") or {}):
            return None
        return decide("ask", "Notion write: needs the owner's per-action OK.")
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0  # malformed input: let the harness decide rather than block every tool
    out = check(event)
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
