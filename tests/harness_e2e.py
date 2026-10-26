"""End-to-end harness load test: one headless Claude session per layer, run in parallel.

    python ~/.claude/tests/harness_e2e.py            (about 2-4 minutes, a few dollars at most)

Each case launches `claude -p` from a cwd chosen so exactly one layer is in play, asks for a fact that only
that layer carries, and where possible checks a side effect instead of trusting the model's words.
Exit 0 only if every case passes. Design: ~/.claude/docs/fleet/HARNESS_AUDIT.md §5 step 7.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

CLAUDE = str(Path.home() / ".local" / "bin" / "claude.exe")
STATE = Path.home() / ".claude" / "state"
TIMEOUT_S = 420
BUDGET_USD = "1"


@dataclass
class Case:
    name: str
    cwd: Path
    prompt: str
    expect: list[str]                       # all must appear in the answer (case-insensitive)
    absent: list[str] | None = None         # none may appear
    tools: str = "Read,Glob,Grep"
    check: Callable[[dict], str | None] | None = None   # side-effect check -> failure reason or None


def claude(case: Case) -> dict:
    r = subprocess.run([CLAUDE, "-p", case.prompt, "--output-format", "json", "--model", "sonnet",
                        "--max-budget-usd", BUDGET_USD, "--allowedTools", case.tools],
                       cwd=case.cwd, capture_output=True, text=True, timeout=TIMEOUT_S, stdin=subprocess.DEVNULL)
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"result": f"(no JSON) rc={r.returncode} {r.stdout[-300:]} {r.stderr[-300:]}"}


def evaluate(case: Case) -> tuple[str, bool, str]:
    out = claude(case)
    text = (out.get("result") or "").lower()
    missing = [e for e in case.expect if e.lower() not in text]
    present = [a for a in (case.absent or []) if a.lower() in text]
    reason = ""
    if missing:
        reason += f"missing {missing}; "
    if present:
        reason += f"unexpected {present}; "
    if case.check and (why := case.check(out)):
        reason += why
    return case.name, not reason, reason or (out.get("result") or "")[:160].replace("\n", " ")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="harness-e2e-"))
    plain = tmp / "plain"
    plain.mkdir()
    py = tmp / "py"
    py.mkdir()
    (py / "hello.py").write_text("print('hi')\n", encoding="utf-8")
    repo = tmp / "gitrepo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "f.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "f.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
                   check=True)
    (repo / "f.txt").write_text("changed\n", encoding="utf-8")

    def stash_blocked(_: dict) -> str | None:
        st = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True).stdout
        return None if " M f.txt" in st else "git stash ran (working change is gone)"

    def router_fired(out: dict) -> str | None:
        f = STATE / f"router-{out.get('session_id')}.json"
        if not f.exists():
            return f"no router state file {f.name}"
        return None if "Factory/catwalk" in f.read_text(encoding="utf-8") else "router did not record Factory/catwalk"

    cases = [
        Case("L1 global core + output style", plain,
             "Answer from your loaded instructions only, no tools. Line 1: which D:/repo theme folder holds the "
             "herald repo (one word). Line 2: the exact name of your active output style.",
             ["factory", "terse-ledger"]),
        Case("L2 D:/repo root CLAUDE.md", Path("D:/repo"),
             "Answer from your loaded instructions only, no tools: what is the file name of the D:/repo router script?",
             ["harness_router.py"]),
        Case("L3 theme CLAUDE.md (Finance)", Path("D:/repo/Finance/augur"),
             "Answer from your loaded instructions only, no tools: which brokerage platform does the owner use?",
             ["wealthsimple"]),
        Case("L4 path rule loads on cue", py,
             "Read hello.py with the Read tool. Then, from instructions that are now in your context (not from "
             "files you open), quote the exact first heading of the Python ground rules.",
             ["python ground rules"]),
        Case("L4b path rule absent without cue", plain,
             # regression 2026-10-25: "is a rule about imports present?" was answerable from other text; ask the
             # same objective question as L4 instead.
             "No tools. Quote verbatim the first heading line of each instruction file or rule section in your "
             "context whose heading contains the words 'ground rules'. If none, say NONE.",
             ["none"], absent=["python ground rules"]),
        Case("L5 hook blocks git stash", repo,
             "Use the Bash tool to run exactly: git stash   Then report the tool result in one line.",
             [], tools="Bash", check=stash_blocked),
        Case("L6 router injects project memory", Path("D:/repo"),
             "Use the Read tool on D:/repo/Factory/catwalk/package.json (first 5 lines only). Then say whether "
             "context beginning with [router] arrived, and quote the first entry of the project memory index it showed.",
             ["router", "catwalk"], check=router_fired),
    ]
    with ThreadPoolExecutor(max_workers=len(cases)) as pool:
        results = list(pool.map(evaluate, cases))
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}  | {detail}", flush=True)
    shutil.rmtree(tmp, ignore_errors=True)
    passed = sum(ok for _, ok, _ in results)
    print(f"{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
