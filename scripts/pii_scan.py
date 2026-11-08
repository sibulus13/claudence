"""pre-commit hook: refuse a staged file that adds personal data to a public repo.

    python pii_scan.py <path>...                 (pre-commit stage: the staged text files)
    python pii_scan.py --commit-msg <file>       (commit-msg stage: the message, author and committer)

Flags email addresses (attribution and example domains excepted), Spotify user IDs (URI or profile link), and the
owner's private terms (names, handles, IDs) listed one per line in a file that is never committed: PII_TERMS_FILE,
default ~/.claude/private/pii_terms.txt. A marked repo without that file is refused, never scanned half-way. Compares
each staged file with its HEAD version (its old path when renamed), so data already committed never blocks unrelated
work. Refusals mask what they found (email local part, term by its number). Opt-in per repo: it runs only where the repo root holds a `.pii-scan` marker. Wired in claudence's own
.pre-commit-config.yaml; the fleet installer copies git-hooks/fleet-pre-commit-config.yaml, which does not carry it
yet. Work item: docs/work/pii-scan/.
"""
from __future__ import annotations

import collections
import os
import re
import subprocess
import sys
from pathlib import Path

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SPOTIFY_ID = r"([^\s/?#:\"'<>()\[\]]+)"
SPOTIFY_USER = (re.compile(r"spotify:user:" + SPOTIFY_ID),
                re.compile(r"(?:open|api)\.spotify\.com/(?:intl-[a-z-]+/)?(?:v1/)?users?/" + SPOTIFY_ID))
ALLOWED_EMAIL_DOMAINS = ("anthropic.com", "example.com", "example.test", "example.org", "users.noreply.github.com")
ALLOWED_EMAILS = ("git@github.com", "git@gitlab.com")  # SSH remotes, not people
DEFAULT_TERMS_FILE = Path.home() / ".claude" / "private" / "pii_terms.txt"
GIT_TIMEOUT_S = 30
MARKER = ".pii-scan"
WHITESPACE = re.compile(r"\s+")
SCISSORS = "# ------------------------ >8 ------------------------"


def load_terms(path: Path) -> list[str] | None:
    """The private terms, or None when the file is missing or holds none (both refuse the commit)."""
    if not path.is_file():
        return None
    lines = (ln.strip() for ln in path.read_text(encoding="utf-8").splitlines())
    return [ln for ln in lines if ln and not ln.startswith("#")] or None


def _allowed(email: str) -> bool:
    if email.lower() in ALLOWED_EMAILS:
        return True
    domain = email.rsplit("@", 1)[1].lower()
    return any(domain == d or domain.endswith("." + d) for d in ALLOWED_EMAIL_DOMAINS)


def hits(text: str, terms: list[str]) -> collections.Counter:
    found: collections.Counter = collections.Counter()
    for email in EMAIL.findall(text):
        if not _allowed(email):
            found[f"email {email}"] += 1
    for pattern in SPOTIFY_USER:
        for match in pattern.finditer(text):
            found[f"spotify user {match.group(1)}"] += 1
    flat = WHITESPACE.sub(" ", text).lower()
    for term in terms:
        n = flat.count(WHITESPACE.sub(" ", term).lower())
        if n:
            found[f"private term '{term}'"] += n
    return found


def new_hits(head: str, staged: str, terms: list[str]) -> list[str]:
    return sorted(hits(staged, terms) - hits(head, terms))


def masked(label: str, terms: list[str]) -> str:
    """A hit as printed: enough to find it, never the data itself (the refusal may be copied into a commit)."""
    kind, _, value = label.partition(" ")
    if kind == "email":
        local, _, domain = value.partition("@")
        return f"email {local[:1]}***@{domain}"
    if label.startswith("spotify user "):
        return f"spotify user {label[13:15]}***"
    term = label[len("private term '"):-1]
    return f"private term #{terms.index(term) + 1}" if term in terms else "private term"


def refuse(where: str, found: list[str], terms: list[str]) -> None:
    shown = "; ".join(masked(f, terms) for f in found)
    note = " (terms are numbered as in the private terms file)" if "private term" in shown else ""
    print(f"pii-scan: {where} adds {shown}{note}; remove it or generalise it before a public commit", file=sys.stderr)


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=GIT_TIMEOUT_S)


def git_show(ref: str) -> str:
    run = git("show", ref)
    return run.stdout if run.returncode == 0 else ""


def head_paths() -> dict[str, str]:
    """Staged new path -> its HEAD path, for renames and copies."""
    out = git("diff", "--cached", "--name-status", "-M", "-C", "-z").stdout.split("\0")
    renames, i = {}, 0
    while i < len(out) - 1:
        if out[i][:1] in "RC":
            renames[out[i + 2]] = out[i + 1]
            i += 3
        else:
            i += 2
    return renames


def opted_in() -> bool:
    run = git("rev-parse", "--show-toplevel")
    return run.returncode == 0 and (Path(run.stdout.strip()) / MARKER).is_file()


def message_body(text: str) -> str:
    """The message git will keep: drop comment lines and everything below the `commit -v` scissors line."""
    kept = []
    for line in text.splitlines():
        if line.startswith(SCISSORS):
            break
        if not line.startswith("#"):
            kept.append(line)
    return "\n".join(kept)


def scan_message(message_file: str, terms: list[str]) -> int:
    """commit-msg stage: the message and the author and committer identities, in full (they have no HEAD side)."""
    sources = {"commit message": message_body(Path(message_file).read_text(encoding="utf-8", errors="replace"))}
    for who in ("author", "committer"):
        sources[f"commit {who}"] = git("var", f"GIT_{who.upper()}_IDENT").stdout
    failed = 0
    for where, text in sources.items():
        found = sorted(hits(text, terms))
        if found:
            refuse(where, found, terms)
            failed = 1
    return failed


def main(args: list[str]) -> int:
    if not opted_in():
        return 0
    terms_file = Path(os.environ.get("PII_TERMS_FILE", DEFAULT_TERMS_FILE))
    terms = load_terms(terms_file)
    if terms is None:
        print(f"pii-scan: no private terms at {terms_file} (missing or empty); this repo is marked {MARKER}, so the "
              "commit is refused until the file lists them", file=sys.stderr)
        return 1
    if args[:1] == ["--commit-msg"]:
        return scan_message(args[1], terms)
    renames = head_paths()
    failed = 0
    for path in args:
        found = new_hits(git_show(f"HEAD:{renames.get(path, path)}"), git_show(f":{path}"), terms)
        if found:
            refuse(path, found, terms)
            failed = 1
    return failed


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
