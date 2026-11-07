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


# notion-prompt-removal/AC-1, notion-prompt-removal/MNC-1
def test_notion_writes_never_prompt() -> None:
    for name in ("update-page", "create-view", "delete-pages", "move-pages"):
        assert run(f"mcp__plugin_Notion_notion__notion-{name}", {}) is None


def _bad_repo_target(path: str) -> bool:
    out = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import guard; "
                          "from pathlib import Path; print(guard.bad_repo_target(Path(sys.argv[2])))",
                          str(HOOK.parent), path], capture_output=True, text=True, timeout=30,
                         env={"PATH": "", "SYSTEMROOT": "C:/Windows"})
    return out.stdout.strip() == "True"


def test_repo_root_docs_is_allowed():
    """fleet-docs-home/AC-8: the fleet docs repo may live at D:/repo/docs."""
    assert not _bad_repo_target("D:/repo/docs")
    assert not _bad_repo_target("D:/repo/Docs")
    assert not _bad_repo_target("D:/repo/docs/x")


@pytest.mark.parametrize("name", ["foo", "docs2", "ai", "web"])
def test_other_bare_root_names_stay_denied(name):
    """fleet-docs-home/AC-9: only the single name docs is exempt; the root itself is still not a target."""
    assert _bad_repo_target(f"D:/repo/{name}")
    assert not _bad_repo_target("D:/repo")


# ---------------------------------------------------------------- fix-guard-init-branch (2026-11-02)

def _targets(cmd: str, cwd: str, shell: str = "bash") -> list[str] | str:
    """init_targets as POSIX strings, or 'UNRESOLVABLE' when the guard cannot resolve the command."""
    code = ("import sys, json; sys.path.insert(0, sys.argv[1]); import guard\n"
            "try:\n"
            "    print(json.dumps([p.as_posix() for p in guard.init_targets(sys.argv[2], sys.argv[3], sys.argv[4])]))\n"
            "except guard.Unresolvable:\n"
            "    print(json.dumps('UNRESOLVABLE'))\n")
    out = subprocess.run([sys.executable, "-c", code, str(HOOK.parent), cmd, cwd, shell], capture_output=True,
                         text=True, timeout=30, env={"PATH": "", "SYSTEMROOT": "C:/Windows"})
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _decision(cmd: str, cwd: str, tool: str = "Bash") -> str | None:
    return run(tool, {"command": cmd}, cwd=cwd)


@pytest.mark.parametrize("cmd", [
    "git init -b main D:/repo/Lib/x", "git init --initial-branch main D:/repo/Lib/x", "git init -qb main D:/repo/Lib/x",
    "git init -bmain D:/repo/Lib/x", "git init --template D:/t D:/repo/Lib/x", "git init --shared D:/repo/Lib/x",
    "git init -- D:/repo/Lib/x"])
def test_init_option_values_are_not_targets(cmd):
    """fix-guard-init-branch/AC-1"""
    assert _targets(cmd, "D:/repo") == ["D:/repo/Lib/x"]
    assert _decision(cmd, "D:/repo") != "deny"


@pytest.mark.parametrize("cmd", [
    "git clone --branch dev https://h/r.git", "git clone --bra dev https://h/r.git", "git clone -c a=b https://h/r.git",
    "git clone https://h/r.git --depth 1"])
def test_clone_values_are_skipped_and_the_root_denied(cmd):
    """fix-guard-init-branch/AC-2"""
    assert _targets(cmd, "D:/repo") == ["D:/repo/r"]
    assert _decision(cmd, "D:/repo") == "deny"


@pytest.mark.parametrize("cmd", [
    "git -C D:/repo init junk", "git -c k=v --git-dir D:/g init D:/repo/junk", "cd D:/repo && git init junk",
    "cd D:/repo; git init junk", "cd D:/repo\ngit init junk", "git -C .. init junk"])
def test_working_directory_changes_are_followed(cmd):
    """fix-guard-init-branch/AC-3"""
    assert _targets(cmd, "D:/repo/Lib") == ["D:/repo/junk"]
    assert _decision(cmd, "D:/repo/Lib") == "deny"


def test_chained_dash_c_applies_left_to_right():
    """fix-guard-init-branch/AC-3"""
    assert _targets("git -C D:/repo -C Lib init x", "D:/repo/Lib") == ["D:/repo/Lib/x"]


def test_every_segment_is_judged():
    """fix-guard-init-branch/AC-4"""
    assert _targets("cd D:/repo/Lib && git init x", "D:/repo") == ["D:/repo/Lib/x"]
    assert _decision("git init D:/repo/Lib/x && git init D:/repo/bad", "D:/repo") == "deny"
    assert _decision("cd $X && git init y", "D:/repo") == "deny"


@pytest.mark.parametrize("cmd", ["git init -b main", "git init"])
def test_an_init_at_the_fleet_root_is_denied(cmd):
    """fix-guard-init-branch/AC-5 (bad_repo_target('D:/repo') stays False: test_other_bare_root_names_stay_denied)"""
    assert _targets(cmd, "D:/repo") == ["D:/repo"]
    assert _decision(cmd, "D:/repo") == "deny"


@pytest.mark.parametrize("cmd", [
    'git commit -m "git init D:/repo/x"', "cat > notes.txt <<'EOF'\ngit init D:/repo/x\nEOF",
    "echo git init D:/repo/x"])
def test_prose_is_not_an_init(cmd):
    """fix-guard-init-branch/AC-6"""
    assert _targets(cmd, "D:/repo/Lib") == []


@pytest.mark.parametrize("cmd,tool,target,denied", [
    ('git init "D:/repo/bad"', "Bash", "D:/repo/bad", True),
    ('git init "D:/repo/Lib/my proj"', "Bash", "D:/repo/Lib/my proj", False),
    ('bash -c "git init D:/repo/bad"', "Bash", "D:/repo/bad", True),
    ('pwsh -Command "git init D:/repo/bad"', "PowerShell", "D:/repo/bad", True)])
def test_quoted_and_wrapped_targets_are_read(cmd, tool, target, denied):
    """fix-guard-init-branch/AC-6"""
    assert _targets(cmd, "D:/repo/Lib", tool.lower()) == [target]
    assert (_decision(cmd, "D:/repo/Lib", tool) == "deny") is denied


def test_unparseable_inits_are_denied_and_other_commands_untouched():
    """fix-guard-init-branch/AC-7"""
    assert _targets('git init "D:/repo/bad', "D:/repo/Lib") == "UNRESOLVABLE"
    assert _targets("git clone --b dev https://h/r.git", "D:/repo/Lib") == "UNRESOLVABLE"
    assert _decision('git init "D:/repo/bad', "D:/repo/Lib") == "deny"
    assert _targets('echo "it\'s fine', "D:/repo/Lib") == []


@pytest.mark.parametrize("cmd,cwd,tool,target,denied", [
    (r"git init D:\repo\bad", "D:/repo", "Bash", "D:/repo/repobad", True),
    (r"git init D:\repo\bad", "D:/repo/Lib", "Bash", "D:/repo/Lib/repobad", False),
    (r"git init D:\repo\bad", "D:/repo/Lib", "PowerShell", "D:/repo/bad", True),
    (r'git init "D:\repo\bad"', "D:/repo/Lib", "Bash", "D:/repo/bad", True),
    (r'git init "D:\repo\Lib\x y"', "D:/repo/Lib", "PowerShell", "D:/repo/Lib/x y", False)])
def test_backslash_paths_follow_the_calling_shell(cmd, cwd, tool, target, denied):
    """fix-guard-init-branch/AC-8"""
    assert _targets(cmd, cwd, tool.lower()) == [target]
    assert (_decision(cmd, cwd, tool) == "deny") is denied


# ---------------------------------------- fix-guard-init-branch, code review round 1 regressions (2026-11-02)

@pytest.mark.parametrize("cmd,tool", [
    ('for d in */; do git -C "$d" pull; done', "Bash"), ('git -C "$(pwd)" status', "Bash"),
    ("git -C $DIR log --oneline", "Bash"), ("git status; git -C $x log", "Bash"), ("git -C ~ status", "Bash"),
    ("git -C $env:USERPROFILE status", "PowerShell"), ("cd $X && git -C sub status", "Bash")])
def test_dash_c_with_an_unknown_directory_is_fine_for_other_subcommands(cmd, tool):
    """fix-guard-init-branch/AC-3 (code review R1: only an init or clone needs the directory)"""
    assert _decision(cmd, "D:/repo/Lib/telefi", tool) != "deny"


@pytest.mark.parametrize("cmd", [
    "git commit -m @'\nfix: git init handling doesn't break\n'@",
    "$msg = @'\nthe guard's git init rule\n'@\ngit commit -m $msg",
    'Set-Content f.md @"\nnote: "don\'t" git init here\n"@'])
def test_powershell_here_strings_are_prose(cmd):
    """fix-guard-init-branch/AC-6 (code review R2)"""
    assert _targets(cmd, "D:/repo/Lib", "powershell") == []
    assert _decision(cmd, "D:/repo/Lib", "PowerShell") != "deny"


@pytest.mark.parametrize("cmd,tool", [
    ("if true; then git init D:/repo/bad; fi", "Bash"), ("for d in a b; do git init D:/repo/bad; done", "Bash"),
    ("{ git init D:/repo/bad; }", "Bash"), ("env git init D:/repo/bad", "Bash"), ("time git init D:/repo/bad", "Bash"),
    ("if ($true) { git init D:/repo/bad }", "PowerShell")])
def test_keywords_before_git_still_count_as_command_position(cmd, tool):
    """fix-guard-init-branch/AC-6 (code review F1)"""
    assert _targets(cmd, "D:/repo/Lib", tool.lower()) == ["D:/repo/bad"]


def test_msys_drive_paths_are_judged():
    """fix-guard-init-branch/AC-8 (code review F2)"""
    assert _targets("git init /d/repo/bad", "D:/repo/Lib") == ["D:/repo/bad"]


@pytest.mark.parametrize("cmd", ["git init D:/repo/Lib/$NAME", "git clone https://x/$R.git"])
def test_variable_targets_are_not_judged(cmd):
    """fix-guard-init-branch/AC-4 (code review F3: Known limits lists shell variables in a target)"""
    assert _targets(cmd, "D:/repo/Lib") == []


@pytest.mark.parametrize("cmd", ["git init --help", "git init -h"])
def test_help_creates_no_repo(cmd):
    """fix-guard-init-branch/AC-5 (code review H1)"""
    assert _targets(cmd, "D:/repo") == []


def test_a_subshell_cd_does_not_leak():
    """fix-guard-init-branch/AC-4 (code review H2)"""
    assert _targets("(cd D:/repo && git status); git init newrepo", "D:/repo/Lib") == ["D:/repo/Lib/newrepo"]


def test_another_drive_is_not_judged():
    """fix-guard-init-branch/AC-8 (code review T1)"""
    assert _targets("git init C:x", "D:/repo/Lib") == []
