"""Deterministic harness lint: the checks a model should not spend tokens on.

    python ~/.claude/scripts/harness_lint.py [--json] [--root DIR] [--config FILE] [--out FILE]

Checks (ids are the `check` field of a finding):
  paths     (a) every path / markdown link in CLAUDE.md, rules, playbooks, skills, agents, fleet docs and all
                memory notes resolves
  deny      (b) deny-list patterns (stale names and retired systems) do not appear outside fleet docs
  parity    (c) each memory dir: MEMORY.md links resolve and every note is indexed
  budget    (d) size budgets for CLAUDE.md files and memory indexes
  wikilink  (e) [[wikilink]] targets exist as a note in some memory dir
  drift     (f) the harness repo has no uncommitted or untracked files

Private inventory (deny patterns, repo root, budgets, skipped files) lives in a config file read at runtime,
`<root>/docs/fleet/upkeep.config.json` by default (see upkeep_config.py); every key is optional. Writes the report to
`<root>/state/harness-lint.pending.json`; --commit promotes it to `harness-lint.json` (--out), the baseline. --json
prints it. `newFindings` are findings whose id is absent
from the previous report, which is what the Cortex upkeep job turns into a TeleFi digest. Read-only otherwise.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from upkeep_config import HIDDEN, commit_pending, config_path, load_config, previous_ids, store_pending

WALK_SKIP = {"_Archive", "node_modules", "worktrees", "foreman-worktrees", ".claude", ".git", ".next", ".venv"}
WALK_DEPTH = 3
MD_LINK = re.compile(r"\]\(([^)\s]+)\)")
TICK_PATH = re.compile(r"`((?:~|[A-Za-z]:)/[^`\s]*)`")
WIKILINK = re.compile(r"\[\[([^\]\n|]+)(?:\|[^\]\n]*)?\]\]")
PLACEHOLDER = re.compile(r"[<>*{}$%|]|\.\.\.|…")
INDEX_ENTRY = re.compile(r"\]\(([^)\s]+\.md)\)")
CODE_FENCE = re.compile(r"^\s*```")


def finding(check: str, path: str, detail: str, key: str | None = None) -> dict:
    ident = hashlib.sha1((key or detail).encode()).hexdigest()[:10]
    return {"id": f"{check}:{path}:{ident}", "check": check, "path": path, "detail": detail}


def rel(root: Path, p: Path) -> str:
    try:
        return p.relative_to(root).as_posix()
    except ValueError:
        return p.as_posix()


def memory_dirs(root: Path) -> list[Path]:
    return sorted(d for d in (root / "projects").glob("*/memory") if d.is_dir())


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def scan_files(root: Path) -> list[Path]:
    """Every harness text file the path checks cover."""
    files = [root / "CLAUDE.md"]
    for pattern in ("rules/*.md", "playbooks/*.md", "skills/*/SKILL.md", "agents/*.md", "docs/fleet/*.md"):
        files += sorted(root.glob(pattern))
    for mem in memory_dirs(root):
        files += sorted(mem.glob("*.md"))
    return [f for f in files if f.is_file()]


def lines_outside_fences(text: str):
    fenced = False
    for n, line in enumerate(text.splitlines(), 1):
        if CODE_FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            yield n, line


def candidate_paths(line: str) -> list[str]:
    out = []
    for target in MD_LINK.findall(line):
        if re.match(r"^(https?:|mailto:|#)", target):
            continue
        out.append(target.split("#")[0])
    out += TICK_PATH.findall(line)
    return [t for t in out if t and not PLACEHOLDER.search(t)]


def resolve(file: Path, target: str) -> Path:
    t = re.sub(r":\d+(-\d+)?$", "", target).rstrip("/")
    if t.startswith("~"):
        return Path.home() / t[2:]
    if re.match(r"^[A-Za-z]:/", t):
        return Path(t)
    return file.parent / t


def check_paths(root: Path, cfg: dict, files: list[Path]) -> list[dict]:
    skip = {p for pat in cfg["pathCheckSkip"] for p in root.glob(pat)}
    out = []
    for f in files:
        if f in skip:
            continue
        for n, line in lines_outside_fences(read(f)):
            for target in candidate_paths(line):
                if not resolve(f, target).exists():
                    out.append(finding("paths", rel(root, f), f"line {n}: {target} does not resolve", target))
    return out


def check_deny(root: Path, cfg: dict, files: list[Path]) -> list[dict]:
    patterns = [(re.compile(d["pattern"], re.I), d["label"]) for d in cfg["denyList"]]
    ignore = re.compile(cfg["denyIgnoreLine"], re.I) if cfg["denyIgnoreLine"] else None
    out = []
    for f in files:
        r = rel(root, f)
        if r.startswith("docs/fleet/"):
            continue
        for n, line in enumerate(read(f).splitlines(), 1):
            if ignore and ignore.search(line):
                continue
            for rx, label in patterns:
                if rx.search(line):
                    out.append(finding("deny", r, f"line {n}: {label}: {line.strip()[:100]}", f"{label}|{line.strip()}"))
    return out


def check_parity(root: Path) -> list[dict]:
    out = []
    for mem in memory_dirs(root):
        index = mem / "MEMORY.md"
        r = rel(root, mem)
        notes = {p.name for p in mem.glob("*.md")} - {"MEMORY.md"}
        if not index.exists():
            if notes:
                out.append(finding("parity", r, "notes exist but MEMORY.md is missing", "no-index"))
            continue
        linked = set()
        for target in INDEX_ENTRY.findall(read(index)):
            if re.match(r"^https?:", target):
                continue
            linked.add(Path(target).name)
            if not (mem / target).exists():
                out.append(finding("parity", r, f"index links {target}, which does not exist", f"dangling|{target}"))
        for name in sorted(notes - linked):
            out.append(finding("parity", r, f"{name} is not in MEMORY.md", f"unindexed|{name}"))
    return out


def count_lines(p: Path) -> int:
    return len(read(p).splitlines())


def claude_md_files(base: Path) -> list[Path]:
    found: list[Path] = []
    stack = [(base, 0)]
    while stack:
        d, depth = stack.pop()
        if (d / "CLAUDE.md").is_file():
            found.append(d / "CLAUDE.md")
        if depth < WALK_DEPTH:
            stack += [(c, depth + 1) for c in sorted(d.iterdir())
                      if c.is_dir() and c.name not in WALK_SKIP and not c.name.startswith(".")]
    return found


def check_budget(root: Path, cfg: dict) -> list[dict]:
    b = cfg["budgets"]
    out = []

    def over(path: Path, limit: int, unit: str, value: int) -> None:
        if value > limit:
            out.append(finding("budget", rel(root, path), f"{value} {unit} exceeds the {limit} budget", unit))

    if (root / "CLAUDE.md").exists():
        over(root / "CLAUDE.md", b["globalClaudeMdLines"], "lines", count_lines(root / "CLAUDE.md"))
    for mem in memory_dirs(root):
        idx = mem / "MEMORY.md"
        if not idx.exists():
            continue
        fleet = cfg["fleetMemoryDir"] and mem.parent.name == cfg["fleetMemoryDir"]
        over(idx, b["fleetIndexLines"] if fleet else b["projectIndexLines"], "lines", count_lines(idx))
        if not fleet:
            over(idx, b["projectIndexBytes"], "bytes", idx.stat().st_size)
    if cfg["repoRoot"] and Path(cfg["repoRoot"]).is_dir():
        for f in claude_md_files(Path(cfg["repoRoot"])):
            over(f, b["repoClaudeMdLines"], "lines", count_lines(f))
    return out


def note_names(mem: Path) -> set[str]:
    names = set()
    for p in mem.glob("*.md"):
        names.add(p.stem.replace("_", "-"))
        m = re.search(r"^name:\s*(\S+)", read(p), re.M)
        if m:
            names.add(m.group(1).strip("\"'"))
    return names


def check_wikilinks(root: Path) -> list[dict]:
    out = []
    dirs = memory_dirs(root)
    known = set().union(*(note_names(m) for m in dirs)) if dirs else set()  # a link may cross memory dirs
    for mem in dirs:
        for p in sorted(mem.glob("*.md")):
            for n, line in lines_outside_fences(read(p)):
                for target in WIKILINK.findall(line):
                    if target.strip().replace("_", "-") not in known:
                        out.append(finding("wikilink", rel(root, p), f"line {n}: [[{target}]] has no note", target))
    return out


def check_drift(root: Path) -> list[dict]:
    r = subprocess.run(["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True, timeout=30, **HIDDEN)
    if r.returncode != 0:
        return []  # not a git checkout: nothing to drift from
    out = []
    for line in r.stdout.splitlines():
        status, path = line[:2].strip(), line[3:]
        out.append(finding("drift", path, f"{'untracked' if status == '??' else 'modified'}: {path}", path))
    return out


def run(root: Path, cfg: dict, previous_ids: set[str] | None) -> dict:
    files = scan_files(root)
    findings = (check_paths(root, cfg, files) + check_deny(root, cfg, files) + check_parity(root)
                + check_budget(root, cfg) + check_wikilinks(root) + check_drift(root))
    ids = {f["id"] for f in findings}
    new = ids if previous_ids is None else ids - previous_ids
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["check"]] = counts.get(f["check"], 0) + 1
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": len(findings),
        "counts": counts,
        "newFindings": [f for f in findings if f["id"] in new],
        "resolved": 0 if previous_ids is None else len(previous_ids - ids),
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", type=Path, default=Path.home() / ".claude")
    ap.add_argument("--config", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    ap.add_argument("--commit", action="store_true", help="promote the pending report to the baseline (after delivery)")
    args = ap.parse_args(argv)
    root = args.root
    cfg = load_config(args.config or config_path(root))
    out = args.out or root / "state" / "harness-lint.json"
    if args.commit:
        commit_pending(out)
        return 0
    report = run(root, cfg, previous_ids(out))
    store_pending(out, report)
    if args.json:
        sys.stdout.write(json.dumps(report) + "\n")
    else:
        print(f"harness-lint: {report['total']} findings ({len(report['newFindings'])} new) {report['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
