"""Acceptance tests for ~/.claude/hooks/guard.py: one case per always/never rule (HARNESS_AUDIT.md §3),
plus the allow cases that must stay allowed. Runs the hook as Claude Code does: JSON on stdin.

    python -m pytest ~/.claude/tests/test_guard.py -q
"""
from __future__ import annotations

import _winapi
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "guard.py"
CWD = "D:/repo"


def run(tool: str, tool_input: dict, **extra: object) -> str | None:
    event = {"tool_name": tool, "tool_input": tool_input, "cwd": CWD, "permission_mode": "default", **extra}
    out = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), capture_output=True, text=True,
                         timeout=30, env={"PATH": "", "SYSTEMROOT": "C:/Windows"})
    return json.loads(out.stdout)["hookSpecificOutput"]["permissionDecision"] if out.stdout.strip() else None


@pytest.mark.parametrize("cmd", [
    "git commit --no-verify -m x",
    "git push --force origin main",
    "git stash",
    "python3 script.py",
    "schtasks /create /tn x /tr notepad.exe",
    "git clone https://github.com/x/newrepo D:/repo/newrepo",
    "git clone https://github.com/x/newrepo D:/repo/AI/newrepo",
    "echo v | vercel env add KEY production",
    "pnpm build",
    "python -m pytest -q",
])
def test_always_never_rules_are_denied(cmd: str) -> None:
    assert run("Bash", {"command": cmd}) == "deny"


@pytest.mark.parametrize("cmd", [
    "git commit -m 'feat: x'",
    # regression 2026-10-25: a commit message that merely mentions the flag was blocked
    'git commit -q -m "feat: deny --no-verify and git stash in hooks"',
    # regression 2026-10-25: a heredoc writing a doc that mentions pytest was blocked as a long command
    "cat > notes.md <<'EOF'\n| rules | pytest and pnpm build |\nEOF\necho ok",
    "git push --force-with-lease origin feature",
    "git stash list",
    "python -m pytest tests/test_x.py -q",
    "git clone https://github.com/x/newrepo D:/repo/SaaS/newrepo",
    "wscript.exe //B //Nologo D:\\repo\\x\\scripts\\run-hidden.vbs; Register-ScheduledTask -TaskName t",
    "Unregister-ScheduledTask -TaskName t -Confirm:$false",
])
def test_normal_commands_stay_allowed(cmd: str) -> None:
    assert run("Bash", {"command": cmd}) is None


def test_worktree_remove_denied_while_node_modules_holds_a_link(tmp_path: Path) -> None:
    # regression 2026-10-28: removal followed node_modules/meter (a junction) and deleted the linked repo
    target = tmp_path / "target"
    target.mkdir()
    (tmp_path / "wt" / "node_modules").mkdir(parents=True)
    cmd = f'git worktree remove --force "{tmp_path / "wt"}"'
    assert run("Bash", {"command": cmd}) is None
    _winapi.CreateJunction(str(target), str(tmp_path / "wt" / "node_modules" / "meter"))  # what npm `file:` makes
    assert run("Bash", {"command": cmd}) == "deny"


def test_long_command_allowed_in_background_and_unattended() -> None:
    assert run("Bash", {"command": "pnpm build", "run_in_background": True}) is None
    assert run("Bash", {"command": "pnpm build"}, permission_mode="bypassPermissions") is None


def test_subagent_cannot_edit_governance_but_parent_can() -> None:
    target = {"file_path": "C:/Users/Michael/.claude/CLAUDE.md", "old_string": "a", "new_string": "b"}
    assert run("Edit", target, agent_id="sub-1") == "deny"
    assert run("Edit", target) is None


@pytest.mark.parametrize("cmd", [
    "sed -i 's/a/b/' C:/Users/M/.claude/projects/D--repo/memory/note.md",
    "rm C:/Users/M/.claude/projects/D--repo/memory/old.md",
    "python -c \"open('C:/Users/M/.claude/CLAUDE.md','w')\"",
    "echo x >> D:/repo/Lib/meter/CLAUDE.md",
])
def test_subagent_cannot_write_governance_through_shell(cmd: str) -> None:
    assert run("Bash", {"command": cmd}, agent_id="sub-1") == "deny"
    assert run("Bash", {"command": cmd}) is None


def test_subagent_can_read_governance_through_shell() -> None:
    assert run("Bash", {"command": "grep -n hook C:/Users/M/.claude/projects/D--repo/memory/MEMORY.md"},
               agent_id="sub-1") is None


def test_notion_write_to_owner_approved_ids_does_not_ask() -> None:
    sys.path.insert(0, str(HOOK.parent))
    from guard import targets_only_approved
    ok = {"1675eed4845d8056992fd03c7227da76"}
    assert targets_only_approved({"page_id": "1675eed4-845d-8056-992f-d03c7227da76", "command": "update_content"}, ok)
    assert not targets_only_approved({"page_id": "1675eed4845d8056992fd03c7227da76",
                                      "new_str": "<page url=\"https://n.so/p/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\">"}, ok)
    assert not targets_only_approved({"query": "x"}, ok)


def test_notion_write_asks_unless_unattended() -> None:
    tool = "mcp__plugin_Notion_notion__notion-update-page"
    assert run(tool, {}) == "ask"
    assert run(tool, {}, permission_mode="bypassPermissions") is None
    assert run("mcp__plugin_Notion_notion__notion-fetch", {}) is None
