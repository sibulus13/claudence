"""PreToolUse guard: the owner's always/never rules, enforced in code instead of prose.

Reads the hook JSON on stdin; prints a permissionDecision JSON (deny or ask) with the reason, or nothing
(allow). Registered in ~/.claude/settings.json for Bash|PowerShell|Write|Edit|MultiEdit|mcp__* tools.
Design: $FLEET_DOCS/HARNESS_AUDIT.md §3. Tests: ~/.claude/tests/test_guard.py.
Unattended runs (Foreman workers in bypassPermissions, scheduled jobs that set CLAUDE_UNATTENDED=1)
skip the interactive-only rule (background long commands).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fleet_paths import REPO_ROOT  # noqa: E402  (one owner of the repo-tree root)

LEGACY_CATEGORIES = {"ai", "bot", "data"}
FLEET_DOCS_NAME = "docs"
SHELL_TOOLS = {"Bash", "PowerShell"}
EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
GOVERNANCE = re.compile(r"(/|\\)(CLAUDE\.md|AGENTS\.md)$|(/|\\)memory(/|\\)|(/|\\)\.claude(/|\\)settings[^/\\]*\.json$|"
                        r"(/|\\)\.claude(/|\\)(agents|hooks|rules|output-styles)(/|\\)", re.I)
# The same governance paths anywhere inside a shell command, and a command that writes (redirect, in-place edit,
# move/copy/delete, an interpreter one-liner): together they are a subagent editing governance through the shell.
GOVERNANCE_IN_SHELL = re.compile(r"(/|\\)(CLAUDE|AGENTS)\.md\b|(/|\\)memory(/|\\)|\.claude(/|\\)settings[^/\\\s]*\.json|"
                                 r"\.claude(/|\\)(agents|hooks|rules|output-styles)\b", re.I)
SHELL_WRITE = re.compile(r"\bsed\s+-i|\b(mv|cp|rm|rmdir|tee|touch|truncate)\b|"
                         r"\b(Set-Content|Add-Content|Out-File|Remove-Item|Move-Item|Copy-Item|New-Item)\b|"
                         r"\b(python|node|perl|ruby)\b[^|;&]*\s-[ce]\b|\.write_text\(|writeFileSync|open\([^)]*['\"][wa]",
                         re.I)
# A redirect is judged by its target: null and stream merges write nothing, and only a governance or relative target
# (relative after a `cd`) can reach governance. Work item: docs/work/guard-write-target/.
NULL_REDIRECT = re.compile(r"\d?>{1,2}\s*(/dev/null|\$null|NUL)\b|\d?>&\d", re.I)
REDIRECT_TARGET = re.compile(r"(?<![<>=!])>{1,2}\s*(\"[^\"]+\"|'[^']+'|[^\s;|&]+)")
ABSOLUTE_PATH = re.compile(r"^[\"']?(?:[A-Za-z]:[\\/]|/|~|\$)")


def writes_governance(raw: str) -> bool:
    """A shell command that could change a governance file."""
    if not GOVERNANCE_IN_SHELL.search(raw):
        return False
    text = NULL_REDIRECT.sub(" ", raw)
    if SHELL_WRITE.search(text):
        return True
    return any(GOVERNANCE_IN_SHELL.search(t) or not ABSOLUTE_PATH.match(t) for t in REDIRECT_TARGET.findall(text))


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


def staged_env_files(cwd: str) -> list[str]:
    r = subprocess.run(["git", "-C", cwd, "diff", "--cached", "--name-only"], capture_output=True, text=True,
                       timeout=10)
    return [f for f in r.stdout.splitlines() if re.search(r"(^|/)\.env(\.[^/]+)?$", f) and "example" not in f]


def has_pnpm_lock(cwd: str) -> bool:
    p = Path(cwd)
    return any((d / "pnpm-lock.yaml").exists() for d in [p, *p.parents])


# Incident 2026-10-28: `git worktree remove` followed the npm `file:` junction node_modules/meter into
# D:/repo/Lib/meter and deleted that repo, .git included.
WORKTREE_REMOVE = re.compile(r"\bgit\b[^|;&]*\bworktree\s+remove\s+(?:-\S+\s+)*(\"[^\"]+\"|'[^']+'|\S+)")


def worktree_links(path: str, cwd: str) -> list[str]:
    """Symlinks/junctions under <worktree>/node_modules (top level and @scope): git on Windows recurses through them."""
    root = Path(path.strip("\"'"))
    nm = (root if root.is_absolute() else Path(cwd) / root) / "node_modules"
    if not nm.is_dir():
        return []
    entries = [*nm.iterdir(), *(q for d in nm.glob("@*") if d.is_dir() for q in d.iterdir())]
    return [str(p) for p in entries if p.is_symlink() or p.is_junction()]


def bad_repo_target(path: Path) -> bool:
    try:
        rel = path.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        return False
    parts = [x.lower() for x in rel.parts]
    if not parts:
        return False
    if parts == [FLEET_DOCS_NAME]:
        return False  # the private fleet docs repo lives at <root>/docs
    return len(parts) == 1 or parts[0] in LEGACY_CATEGORIES or (parts[0] == "web" and parts[1:2] != ["personal"])


# --- Where a git init / clone will create a repo (docs/work/fix-guard-init-branch) ---------------------------------
# Value options that take a separate argument, from git-scm.com/docs/git, git-init and git-clone (checked 2026-11-02).
GIT_GLOBAL_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--super-prefix",
                    "--attr-source"}
# Words that put the next word in command position (shell keywords and pass-through launchers).
LEADING_WORDS = {"then", "do", "else", "elif", "if", "while", "until", "{", "}", "!", "time", "env", "exec", "nohup",
                 "sudo", "command"}
PS_HERE_STRING = re.compile(r"@(['\"])\r?\n.*?\r?\n\1@", re.S)
OPEN, CLOSE = "\0open", "\0close"   # subshell / block boundaries: a cd inside does not leak out
INIT_VALUE = {"-b", "--initial-branch", "--template", "--separate-git-dir", "--object-format", "--ref-format"}
CLONE_VALUE = {"-o", "--origin", "-b", "--branch", "-u", "--upload-pack", "-c", "--config", "-j", "--jobs",
               "--reference", "--reference-if-able", "--separate-git-dir", "--depth", "--template", "--filter",
               "--shallow-since", "--shallow-exclude", "--server-option", "--bundle-uri", "--revision", "--ref-format"}
SEP = "\0sep"   # a command separator token, never a real argument
CD_WORDS = {"cd", "pushd", "set-location", "sl", "chdir"}
WRAPPERS = {"bash": ("-c", "bash"), "sh": ("-c", "bash"), "pwsh": ("-c", "powershell"),
            "powershell": ("-c", "powershell"), "cmd": ("/c", "powershell")}
GIT_INIT_OR_CLONE = re.compile(r"\bgit(\.exe)?\b.*\b(init|clone)\b", re.S)


class Unresolvable(Exception):
    """The guard cannot tell where a git init or clone would create a repo: the caller denies."""


def shell_tokens(cmd: str, shell: str) -> list[str]:
    """Split by the calling shell's rules: Bash escapes with a backslash, PowerShell (and cmd) with a backtick and keep
    backslashes literal. Separators outside quotes become SEP. Raises ValueError on an unbalanced quote."""
    esc = "\\" if shell == "bash" else "`"
    tokens: list[str] = []
    buf: list[str] = []
    started = False
    quote = None
    i = 0

    def flush() -> None:
        nonlocal buf, started
        if buf or started:
            tokens.append("".join(buf))
        buf, started = [], False

    while i < len(cmd):
        c = cmd[i]
        if quote == "'":
            if c == "'" and shell != "bash" and cmd[i + 1:i + 2] == "'":
                buf.append("'")
                i += 1
            elif c == "'":
                quote = None
            else:
                buf.append(c)
        elif quote == '"':
            if c == '"':
                quote = None
            elif c == esc and i + 1 < len(cmd):
                nxt = cmd[i + 1]
                if shell == "bash" and nxt not in '"\\$`\n':
                    buf.append(c)              # bash keeps a backslash that escapes nothing inside double quotes
                else:
                    buf.append(nxt)
                    i += 1
            else:
                buf.append(c)
        elif c in "'\"":
            quote, started = c, True
        elif c == esc and i + 1 < len(cmd):
            buf.append(cmd[i + 1])
            started = True
            i += 1
        elif c in " \t\r":
            flush()
        elif c in "()":
            flush()
            tokens.append(OPEN if c == "(" else CLOSE)
        elif c in "\n;&|":
            flush()
            if not tokens or tokens[-1] != SEP:
                tokens.append(SEP)
        else:
            buf.append(c)
        i += 1
    if quote:
        raise ValueError("unbalanced quote")
    flush()
    return tokens


def resolve_dir(cwd: Path | None, arg: str, shell: str = "bash") -> Path | None:
    """`arg` as a directory seen from `cwd`. None when it cannot be on this drive (not judged); raises Unresolvable when
    it depends on something unknown (a variable, `-`, `~`, or a relative path from an unknown directory)."""
    if not arg or arg in ("-", "~") or arg.startswith("~/") or "$" in arg or "%" in arg:
        raise Unresolvable(f"directory `{arg or '(home)'}` is not known statically")
    if shell == "bash" and (msys := re.match(r"^(?:/mnt)?/([A-Za-z])(/.*|$)", arg)):
        arg = f"{msys.group(1).upper()}:{msys.group(2) or '/'}"   # Git Bash / WSL drive form: /d/repo is D:/repo
    m = re.match(r"^([A-Za-z]):(?![\\/])(.*)$", arg)   # drive-relative, e.g. D:repobad
    if m:
        if cwd is None:
            raise Unresolvable(f"`{arg}` is relative to an unknown directory")
        if cwd.drive.upper() != f"{m.group(1).upper()}:":
            return None
        arg = m.group(2)
    p = Path(arg)
    if not p.is_absolute():
        if cwd is None:
            raise Unresolvable(f"`{arg}` is relative to an unknown directory")
        p = cwd / p
    return Path(os.path.normpath(p))


def take_options(args: list[str], value_opts: set[str]) -> list[str]:
    """Drop options and their values (attached, separate, clustered short ones, unique long prefixes); return the
    positionals. A long prefix of two or more value options is ambiguous: Unresolvable."""
    positionals: list[str] = []
    longs = sorted(o for o in value_opts if o.startswith("--"))
    shorts = {o[1] for o in value_opts if len(o) == 2}
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            positionals += args[i + 1:]
            break
        if a.startswith("--"):
            name = a.split("=", 1)[0]
            if "=" not in a:
                hits = [name] if name in value_opts else [o for o in longs if o.startswith(name)]
                if len(hits) > 1:
                    raise Unresolvable(f"`{name}` is an ambiguous option")
                if hits:
                    i += 1             # its value is the next argument
        elif a.startswith("-") and len(a) > 1:
            for k, ch in enumerate(a[1:], start=1):
                if ch in shorts:
                    if k == len(a) - 1:
                        i += 1         # `-qb main`: the value is the next argument; `-bmain`: it is attached
                    break
        else:
            positionals.append(a)
        i += 1
    return positionals


def clone_dir(url: str) -> str:
    tail = re.split(r"[/\\:]", url.rstrip("/\\"))[-1]
    return re.sub(r"\.git$", "", tail)


def init_targets(cmd: str, cwd: str, shell: str = "bash", depth: int = 0) -> list[Path]:
    """Every directory a git init or clone in `cmd` would create a repo in, in order. Raises Unresolvable when that
    cannot be told; the guard denies then. Known limits: docs/work/fix-guard-init-branch/README.md § Known limits."""
    text = PS_HERE_STRING.sub("''", HEREDOC.sub("<<HEREDOC", cmd))   # here-doc and here-string bodies are data
    try:
        tokens = shell_tokens(text, shell)
    except ValueError as e:
        if GIT_INIT_OR_CLONE.search(text):
            raise Unresolvable(str(e)) from e
        return []
    here: Path | None = Path(cwd)
    stack: list[Path | None] = []    # directories saved by `(`, `{`-blocks are not scopes; pushd saves too
    found: list[Path] = []
    segments: list[list[str]] = [[]]
    for t in tokens:
        if t in (SEP, OPEN, CLOSE):
            segments.append([t] if t != SEP else [])
        else:
            segments[-1].append(t)
    for seg in segments:
        if seg and seg[0] == OPEN:
            stack.append(here)
            seg = seg[1:]
        elif seg and seg[0] == CLOSE:
            here = stack.pop() if stack else here
            seg = seg[1:]
        seg = [a for i, a in enumerate(seg) if not re.match(r"^\d?[<>]", a)          # redirections and their file
               and not (i > 0 and re.fullmatch(r"\d?[<>]+&?", seg[i - 1]))]
        while seg and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", seg[0]) or seg[0].lower() in LEADING_WORDS):
            seg = seg[1:]
        if not seg:
            continue
        word = re.split(r"[\\/]", seg[0])[-1].lower().removesuffix(".exe")
        if word in CD_WORDS:
            args = [a for a in seg[1:] if a.lower() not in ("-path", "-literalpath", "/d")]
            if word == "pushd":
                stack.append(here)
            try:
                here = resolve_dir(here, args[0] if args else "", shell)
            except Unresolvable:
                here = None          # judged only if a later init or clone depends on it
            continue
        if word == "popd":
            here = stack.pop() if stack else None
            continue
        if word in WRAPPERS and depth == 0:
            flag, inner_shell = WRAPPERS[word]
            lowered = [a.lower() for a in seg]
            for f in (flag, "-command"):
                if f in lowered and lowered.index(f) + 1 < len(seg):
                    found += init_targets(seg[lowered.index(f) + 1], str(here) if here else cwd, inner_shell, 1)
                    break
            continue
        if word != "git":
            continue
        rest, where = seg[1:], here
        while rest and rest[0].startswith("-"):
            opt = rest[0].split("=", 1)[0]
            if opt in GIT_GLOBAL_VALUE and "=" not in rest[0] and len(rest) > 1:
                if opt == "-C":
                    try:
                        where = resolve_dir(where, rest[1], shell)
                    except Unresolvable:
                        where = None     # only an init or clone needs it (checked below)
                rest = rest[2:]
            else:
                rest = rest[1:]
        if not rest or rest[0] not in ("init", "clone"):
            continue
        sub, args = rest[0], rest[1:]
        if "-h" in args or "--help" in args:
            continue                     # prints usage, creates nothing
        pos = take_options(args, INIT_VALUE if sub == "init" else CLONE_VALUE)
        if sub == "init":
            target = pos[0] if pos else "."
        elif pos:
            target = pos[1] if len(pos) > 1 else clone_dir(pos[0])
        else:
            continue
        if "$" in target or "%" in target:
            continue                     # Known limits: a shell variable in a target is not judged
        if where is None and not re.match(r"^(?:[A-Za-z]:[\\/]|/)", target):
            raise Unresolvable("the working directory is not known statically")
        resolved = resolve_dir(where, target, shell)
        if resolved is not None:
            found.append(resolved)
    return found


def check_shell(event: dict) -> dict | None:
    ti = event.get("tool_input") or {}
    # Quoted text (commit messages, echo strings) is data, not flags: match rules against the rest only.
    raw = ti.get("command") or ""
    if event.get("agent_id") and writes_governance(raw):
        return decide("deny", "Subagents never edit governance (CLAUDE.md, memory, settings, agents, hooks, rules), "
                              "including through the shell: return the proposed change to the parent session.")
    cmd = QUOTED.sub("''", HEREDOC.sub("<<HEREDOC", raw))
    cwd = event.get("cwd") or os.getcwd()
    if re.search(r"\bgit\b[^|;&]*\b(commit|push|merge|rebase)\b[^|;&]*--no-verify", cmd):
        return decide("deny", "--no-verify is never allowed: fix the failing hook instead.")
    if re.search(r"\bgit\b[^|;&]*\bpush\b[^|;&]*(\s--force(?!-with-lease)\b|\s-f\b)[^|;&]*\b(main|master)\b", cmd) or \
       re.search(r"\bgit\b[^|;&]*\bpush\b[^|;&]*\+(main|master)\b", cmd):
        return decide("deny", "Never force-push main/master.")
    if re.search(r"\bgit\b[^|;&]*\bstash\b(?!\s+(list|show)\b)|--autostash", cmd):
        return decide("deny", "No git stash: commit to a branch or use a worktree (stash loses work in shared checkouts).")
    if (m := WORKTREE_REMOVE.search(ti.get("command") or "")) and (links := worktree_links(m.group(1), cwd)):
        return decide("deny", f"Worktree has links that removal would follow into their targets: {', '.join(links[:3])}. "
                              "Delete the links themselves first (cmd /c rmdir <link>), then remove the worktree.")
    if re.search(r"\bpython3\b", cmd) and event.get("tool_name") == "Bash":
        return decide("deny", "Use `python`, not `python3`, on this machine.")
    if re.search(r"(^|[;&|]\s*)(npm\s+(i|install|add)\b|yarn(\s+add)?\b)", cmd) and has_pnpm_lock(cwd):
        return decide("deny", "This repo uses pnpm (pnpm-lock.yaml present): use pnpm, not npm/yarn.")
    if re.search(r"\|\s*vercel\s+env\s+add\b", cmd):
        return decide("deny", "Piping into `vercel env add` from PowerShell corrupts values: pass the value via a file or --value.")
    if re.search(r"\bgit\b[^|;&]*\bcommit\b", cmd) and (bad := staged_env_files(cwd)):
        return decide("deny", f"Refusing to commit secrets: {', '.join(bad)} is staged. Unstage it.")
    if re.search(r"\bRegister-ScheduledTask|New-ScheduledTaskAction|schtasks(\.exe)?\s+/create", cmd, re.I) and \
       not re.search(r"run[-_]hidden\.vbs|pythonw(\.exe)?", cmd, re.I):
        return decide("deny", "Scheduled tasks must run hidden: action = wscript.exe //B //Nologo <repo>\\scripts\\run-hidden.vbs "
                              "<program> (or pythonw.exe). Then smoke it: Start-ScheduledTask + LastTaskResult 0.")
    try:
        targets = init_targets(ti.get("command") or "", cwd, "powershell" if event.get("tool_name") == "PowerShell" else "bash")
    except Unresolvable as e:
        return decide("deny", f"Cannot tell where this git init/clone would create a repo ({e}). Use a literal absolute "
                              "path in a theme folder (D:/repo/<Theme>/<repo>).")
    for target in targets:
        if target == Path(os.path.normpath(REPO_ROOT)) or bad_repo_target(target):
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
