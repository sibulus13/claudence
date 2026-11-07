"""When was each file last used? A file counts as used when its path appears in any tool call of any Claude Code
transcript (Read, Grep, Glob, Bash, Edit), subagents included. Context injected at session start is not counted, so
these are lower bounds: live context (CLAUDE.md files, memory indexes) is never swept on this signal.

    last_reads(projects_dir, [paths]) -> ({key(path): epoch of last use}, epoch of the oldest tool call seen)
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path


def key(path: Path | str) -> str:
    """One spelling per path: forward slashes, lower case (Windows paths are case-insensitive)."""
    return str(path).replace("\\", "/").lower()


SLASHES = re.compile(r"/+")


def _norm(text: str) -> str:
    """Any spelling to one: backslashes (escaped or not) to single forward slashes, lower case."""
    return SLASHES.sub("/", text.replace("\\", "/")).lower()


def _tail(k: str) -> str:
    """The parent folder and file name: matches absolute, relative, ~, $VAR and Git Bash /c/ spellings alike."""
    return "/".join(k.split("/")[-2:])


def _epoch(stamp: object) -> float | None:
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def _tool_inputs(line: str):
    try:
        event = json.loads(line)
    except ValueError:
        return None, []
    content = (event.get("message") or {}).get("content") if isinstance(event, dict) else None
    if not isinstance(content, list):
        return None, []
    inputs = [c.get("input") for c in content if isinstance(c, dict) and c.get("type") == "tool_use"]
    return _epoch(event.get("timestamp")), inputs


def last_reads(projects: Path, targets: list[Path]) -> tuple[dict[str, float], float | None]:
    """A target is read when its parent folder and name appear in a tool call (see _tail); keys are key(target)."""
    by_name: dict[str, list[tuple[str, str]]] = {}
    for k in {key(t) for t in targets}:
        by_name.setdefault(k.rsplit("/", 1)[-1], []).append((k, _tail(k)))
    reads: dict[str, float] = {}
    oldest: float | None = None
    for transcript in projects.rglob("*.jsonl") if projects.is_dir() else []:
        with transcript.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"tool_use"' not in line:
                    continue
                when, inputs = _tool_inputs(line)
                if when is None or not inputs:
                    continue
                oldest = when if oldest is None else min(oldest, when)
                for text in (_norm(s) for s in _strings(inputs)):
                    for name, keys in by_name.items():
                        if name in text:
                            for k, tail in keys:
                                if tail in text and when > reads.get(k, 0.0):
                                    reads[k] = when
    return reads, oldest
