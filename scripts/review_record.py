"""Review records: bind an independent review to the exact content it judged (work item docs/work/review-records).

    python review_record.py hash   --item docs/work/<id> [--root <repo>]
    python review_record.py write  --item docs/work/<id> --kind <k> --reviewer <r> --report <file> [--verifies <record>]
    python review_record.py verify [--tree head|index] [--root <repo>]

`hash` prints the content hash of the STAGED item (FR-1). `write` turns a reviewer's report file into
`reviews/<date>-<kind>-<hash8>.md` and prints its path. `verify` lists every record as fresh, stale or invalid.
`content_hash` and `required_records` are the library entry points; the commit gate (spec_gate.py) calls
`required_records` on the lock and ship moves.

What each tool owns (a rule with an off-the-shelf tool does not get a hand-written one):
  digest                 hashlib.sha256 over the serialisation FR-1 defines (nothing off the shelf defines it)
  frontmatter parsing    PyYAML safe_load, the checker's own loader
  record schema          jsonschema (Draft 2020-12) against contracts/review-record.v1.json, the ONLY list of kinds and verdicts
  tree contents          git itself: `ls-files -s`, `ls-tree -r` and one `cat-file --batch` (spec_check.IndexTree / HeadTree)
  unstaged changes       `git status --porcelain`
  command line           argparse
The reviewer rule (FR-5), the report checks (FR-4) and the newest-record order (FR-8) are this item's own rules.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spec_check  # noqa: E402

CLAUDE = Path(__file__).resolve().parents[1]
RECORD_SCHEMA = CLAUDE / "contracts" / "review-record.v1.json"
EXCLUDED_DIRS = ("reviews", "evidence", "cycles")   # FR-1: first path segments that are not item content
GENERATED = ("trace.jsonl", "drift.md")             # FR-1: generated files at the item root
LINK_MODES = ("120000", "160000")                   # FR-2: symlink, gitlink
BOM = b"\xef\xbb\xbf"
MAX_REPORT_BYTES = 1_000_000
MAX_RECORD_BYTES = 1_048_576
MAX_NAME_SUFFIX = 1000                              # bound on the concurrent-writer retry (FR-6)
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
NOT_REVIEWERS = {"", "self", "me", "-", "n/a", "none"}   # FR-5, compared case-folded
ITEM_README = re.compile(r"^docs/work/([\w.-]+)/README\.md$")
FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)
LINES = re.compile(r"\r\n|\r|\n")
OPEN_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
CLOSE_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*$")
REVIEWED = re.compile(r"REVIEWED: (sha256:[0-9a-f]{64})")
REVIEWED_COMMIT = re.compile(r"REVIEWED-COMMIT: ([0-9a-f]{7,40})")
RECORD_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z]+-[0-9a-f]{8}(?:-(\d+))?\.md$")
SHORT_ITEM_TYPES = ("research", "experiment")       # FR-8: these ship on a design-class record


class RecordError(Exception):
    """A refusal with its reason. Nothing is written."""


class HashError(RecordError):
    """FR-2: the item cannot be hashed."""


class ContractError(spec_check.ToolError):
    """The record contract cannot be read or is not a schema."""


def now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- the contract

def schema() -> dict:
    try:
        return json.loads(RECORD_SCHEMA.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ContractError(f"{RECORD_SCHEMA.name} cannot be read: {e}") from e


def validator() -> jsonschema.Draft202012Validator:
    loaded = schema()
    try:
        jsonschema.Draft202012Validator.check_schema(loaded)
    except jsonschema.SchemaError as e:
        raise ContractError(f"{RECORD_SCHEMA.name} is not a valid schema: {e.message}") from e
    return jsonschema.Draft202012Validator(loaded)


def enum(name: str) -> list[str]:
    try:
        return list(schema()["properties"][name]["enum"])
    except (KeyError, TypeError) as e:
        raise ContractError(f"{RECORD_SCHEMA.name} has no `{name}` enum") from e


# ---------------------------------------------------------------- FR-1, FR-2: the hash

def excluded(rel: str) -> bool:
    """A path relative to the item folder that is not item content."""
    return rel.split("/", 1)[0] in EXCLUDED_DIRS or rel in GENERATED


def without_status(text: str) -> str:
    """The README text with its one frontmatter `status:` line (and that line's newline) removed."""
    lines = text.split("\n")
    if lines[0] != "---":
        raise HashError("README.md: the frontmatter must open with a first line that is exactly `---`")
    close = next((i for i in range(1, len(lines)) if lines[i] == "---"), None)
    if close is None:
        raise HashError("README.md: the frontmatter must close with a line that is exactly `---`")
    hits = [i for i in range(1, close) if lines[i].startswith("status:")]
    if len(hits) != 1:
        raise HashError(f"README.md: the frontmatter needs exactly one `status:` line at column 0, found {len(hits)}")
    del lines[hits[0]]
    return "\n".join(lines)


def content_hash(tree: spec_check.Tree, item_dir: str) -> str:
    """FR-1: the digest of the item's files as `tree` holds them. Raises HashError for the FR-2 refusals."""
    prefix = item_dir.rstrip("/") + "/"
    inputs: list[tuple[str, str]] = []
    for mode, path in tree.entries(prefix):
        rel = path[len(prefix):]
        if excluded(rel):
            continue
        first = rel.split("/", 1)[0]
        if first.lower() in EXCLUDED_DIRS:
            raise HashError(f"{rel}: folder `{first}` differs from an excluded folder only in letter case")
        if mode in LINK_MODES:
            raise HashError(f"{rel}: a symlink or gitlink cannot be hashed")
        if "/" in rel and posixpath.basename(rel) == "README.md":
            raise HashError(f"{rel}: a nested work item inside an item cannot be hashed")
        inputs.append((rel, path))
    if "README.md" not in {rel for rel, _ in inputs}:
        raise HashError(f"{item_dir} has no README.md in this tree")
    keyed = []
    for rel, path in inputs:
        try:
            keyed.append((rel.encode("utf-8"), rel, path))
        except UnicodeEncodeError as e:
            raise HashError(f"{rel!r}: the path is not valid UTF-8") from e
    data = tree.read_many([path for _, _, path in keyed])
    parts = []
    for rel_bytes, rel, path in sorted(keyed):
        raw = data[path]
        if raw.startswith(BOM):
            raise HashError(f"{rel}: starts with a BOM")
        try:
            text = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n").decode("utf-8")
        except UnicodeDecodeError as e:
            raise HashError(f"{rel}: not valid UTF-8") from e
        if rel == "README.md":
            text = without_status(text)
        parts.append(f"{len(rel_bytes)}:{rel}\n{len(text.encode('utf-8'))}:{text}\n")
    return "sha256:" + hashlib.sha256("".join(parts).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- FR-5, FR-7: records

def folded(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value)).strip().casefold()


def reviewer_problem(reviewer: object, owner: object | None) -> str | None:
    """FR-5: the reviewer must name someone other than the author."""
    who = folded(reviewer)
    if who in NOT_REVIEWERS or (who.startswith("<") and who.endswith(">")):
        return f"reviewer `{reviewer}` does not name an independent reviewer"
    if owner is not None and who == folded(owner):
        return f"reviewer `{reviewer}` is the item owner, not an independent reviewer"
    return None


def last_line(lines: list[str]) -> str:
    return next((line.rstrip(" ") for line in reversed(lines) if line.strip()), "")


@dataclass
class Record:
    name: str
    fm: dict = field(default_factory=dict)
    body: str = ""
    invalid: str | None = None
    cls: str | None = None
    order: tuple = ()


def parse_record(name: str, data: bytes, owner: object | None) -> Record:
    """FR-7: a record is valid when it is small, its frontmatter fits the schema, its reviewer passes FR-5 and its
    verdict equals the body's last non-blank line."""
    rec = Record(name)
    try:
        if len(data) > MAX_RECORD_BYTES:
            raise RecordError("the file is larger than 1 MB")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise RecordError("the file is not valid UTF-8") from e
        m = FRONTMATTER.match(text)
        if not m:
            raise RecordError("no frontmatter block")
        try:
            fm = yaml.safe_load(m.group(1))
        except yaml.YAMLError as e:
            raise RecordError(f"frontmatter does not parse: {str(e).splitlines()[0]}") from e
        if not isinstance(fm, dict):
            raise RecordError("frontmatter is not a mapping")
        errors = sorted(validator().iter_errors(fm), key=lambda e: list(map(str, e.path)))
        if errors:
            raise RecordError(f"frontmatter breaks the schema: {'/'.join(map(str, errors[0].path)) or 'record'}: "
                              f"{errors[0].message[:120]}")
        if problem := reviewer_problem(fm["reviewer"], owner):
            raise RecordError(problem)
        rec.body = text[m.end():]
        if last_line(LINES.split(rec.body)) != f"VERDICT: {fm['verdict']}":
            raise RecordError(f"the frontmatter verdict `{fm['verdict']}` differs from the body's last VERDICT: line")
        try:
            when = datetime.strptime(fm["recorded"], TIME_FORMAT)
        except ValueError as e:
            raise RecordError(f"recorded `{fm['recorded']}` is not a date") from e
        rec.fm = fm
        suffix = RECORD_NAME.match(name)
        rec.order = (when, int(suffix.group(1)) if suffix and suffix.group(1) else 1)
    except RecordError as e:
        rec.invalid = str(e)
    return rec


def load_records(files: dict[str, bytes], owner: object | None) -> list[Record]:
    """Parse every record and give each its class: `design` or `code` (a `verify` record has its target's class)."""
    records = {name: parse_record(name, data, owner) for name, data in files.items()}

    def class_of(rec: Record, seen: tuple[str, ...]) -> str | None:
        if rec.invalid:
            return None
        if rec.fm["kind"] != "verify":
            return rec.fm["kind"]
        target = records.get(rec.fm["verifies"])
        if target is None or target.name in seen or target.name == rec.name:
            return None
        return class_of(target, (*seen, rec.name))

    for rec in records.values():
        rec.cls = class_of(rec, ())
        if rec.cls is None and not rec.invalid:
            rec.invalid = f"verifies `{rec.fm['verifies']}`, which is not a valid record of this item"
    return list(records.values())


def readme_facts(tree: spec_check.Tree, item_dir: str) -> dict:
    text = tree.read(f"{item_dir}/README.md") or ""
    m = FRONTMATTER.match(text)
    try:
        fm = yaml.safe_load(m.group(1)) if m else None
    except yaml.YAMLError:
        fm = None
    return fm if isinstance(fm, dict) else {}


def tree_records(tree: spec_check.Tree, item_dir: str, owner: object | None) -> list[Record]:
    prefix = f"{item_dir}/reviews/"
    paths = [path for _, path in tree.entries(prefix)
             if "/" not in path[len(prefix):] and path.endswith(".md") and not path[len(prefix):].startswith(".")]
    data = tree.read_many(paths)
    return load_records({path[len(prefix):]: data[path] for path in paths}, owner)


def disk_records(root: Path, item_dir: str, owner: object | None) -> list[Record]:
    folder = root / item_dir / "reviews"
    files = {}
    for p in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        if p.is_file() and not p.name.startswith("."):
            with p.open("rb") as f:
                files[p.name] = f.read(MAX_RECORD_BYTES + 1)
    return load_records(files, owner)


# ---------------------------------------------------------------- FR-8: the gate's entry point

def required_records(tree: spec_check.Tree, item_dir: str, edges: list, item_type: str | None = None, *,
                     live: bool | None = None) -> str | None:
    """None when the records the edges need are fresh passes in `tree`, else the reason. A lock needs the design
    class unless the staged README is a v3 T1 feature or an unflagged v3 bugfix (spec_v3.lock_exempt: the computed tier,
    read through the one v3 reader; `live` is the repo's tier, None reads it from `tree`); a ship needs the code class
    (design class for a research or experiment item). Code freshness is not judged here (decision D32, work item gate-ci)."""
    facts = readme_facts(tree, item_dir)
    kind = str(item_type if item_type is not None else facts.get("type"))
    needs: list[str] = []
    for _, to in edges:
        if to == "spec-locked":
            import spec_v3  # lazy: only a lock edge reads the v3 rules
            wanted = None if spec_v3.lock_exempt(tree, item_dir, live) else "design"
        elif to == "shipped":
            wanted = "code"
            if kind in SHORT_ITEM_TYPES:
                wanted = "design"
        else:
            wanted = None
        if wanted and wanted not in needs:
            needs.append(wanted)
    if not needs:
        return None
    validator()  # a broken contract is a named failure, whatever the records hold
    records = tree_records(tree, item_dir, facts.get("owner"))
    current: str | None = None
    for need in needs:
        candidates = sorted((r for r in records if r.cls == need), key=lambda r: r.order)
        if not candidates:
            invalid = [f"record invalid: {r.name}: {r.invalid}" for r in records if r.invalid][:3]
            return "; ".join([f"needs a fresh {need} review", *invalid])
        newest = candidates[-1]
        if newest.fm["verdict"] != "pass":
            return f"newest {need} record is {newest.fm['verdict']} ({newest.name})"
        if current is None:
            try:
                current = content_hash(tree, item_dir)
            except HashError as e:
                return f"cannot hash item: {e}"
        if newest.fm["content"] != current:
            return (f"record is stale (reviewed {newest.fm['content'][7:15]}, committing {current[7:15]}): "
                    f"{newest.name}")
    return None


# ---------------------------------------------------------------- git helpers for the commands

def git(root: Path, *args: str, ok_codes: tuple[int, ...] = (0,)) -> str:
    spec_check.require_index_file()
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=spec_check.GIT_TIMEOUT_S)
    except subprocess.TimeoutExpired as e:
        raise OSError(f"git {args[0]} timed out") from e
    if r.returncode not in ok_codes:
        raise OSError(f"git {' '.join(args[:2])} exited {r.returncode}: {r.stderr.strip()[:200]}")
    return r.stdout


def resolve_item(root: Path, given: str) -> str:
    """FR-3: the exact indexed `docs/work/<id>` folder named by `given` (backslashes, a trailing slash, an absolute
    path inside the repo and letter case normalised); anything else is refused."""
    raw = given.replace("\\", "/").strip()
    if raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
        try:
            raw = Path(raw).resolve().relative_to(root.resolve()).as_posix()
        except ValueError as e:
            raise RecordError(f"--item `{given}` is outside the repository") from e
    wanted = posixpath.normpath(raw)
    items = {path.rsplit("/", 1)[0] for path in spec_check.IndexTree(root).files if ITEM_README.match(path)}
    exact = wanted if wanted in items else None
    loose = [i for i in items if i.casefold() == wanted.casefold()]
    if exact is None and len(loose) == 1:
        exact = loose[0]
    if exact is None:
        raise RecordError(f"--item must name an indexed docs/work/<id> folder with a README.md, got `{given}`")
    return exact


def require_staged(root: Path, item: str) -> None:
    """FR-3: the hash in the reviewer's brief is the hash the gate will see, so hash inputs must be staged."""
    out = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames", "--", item)
    dirty = []
    for entry in out.split("\0"):
        if entry and (entry[:2] == "??" or entry[1] != " ") and not excluded(entry[3:][len(item) + 1:]):
            dirty.append(entry[3:])
    if dirty:
        raise RecordError(f"stage the item first: {item} has unstaged or untracked changes ({', '.join(dirty[:3])})")


def outside_fences(lines: list[str]) -> list[str]:
    kept, fence = [], None
    for line in lines:
        if fence is None:
            if m := OPEN_FENCE.match(line):
                fence = (m.group(1)[0], len(m.group(1)))
            else:
                kept.append(line)
        elif (m := CLOSE_FENCE.match(line)) and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]:
            fence = None
    return kept


# ---------------------------------------------------------------- the commands

def cmd_hash(root: Path, item_arg: str) -> str:
    item = resolve_item(root, item_arg)
    require_staged(root, item)
    return content_hash(spec_check.IndexTree(root), item)


def verifies_target(root: Path, item: str, given: str, owner: object | None) -> Record:
    folder = f"{item}/reviews"
    name = posixpath.basename(given.replace("\\", "/"))
    where = posixpath.dirname(given.replace("\\", "/"))
    if where and (root / where).resolve() != (root / folder).resolve():
        raise RecordError(f"--verifies `{given}` is not a record of {item}")
    target = next((r for r in disk_records(root, item, owner) if r.name == name), None)
    if target is None or target.invalid:
        raise RecordError(f"--verifies `{given}` is not a valid record of {item}"
                          + (f" ({target.invalid})" if target else ""))
    if target.fm["verdict"] != "fix-first":
        raise RecordError(f"--verifies must name a fix-first record; `{name}` is {target.fm['verdict']}")
    return target


def read_report(path: Path) -> tuple[bytes, list[str]]:
    try:
        size = path.stat().st_size
    except OSError as e:
        raise RecordError(f"the report cannot be read: {e}") from e
    if size > MAX_REPORT_BYTES:
        raise RecordError("the report is larger than 1 MB")
    raw = path.read_bytes()
    if not raw.strip():
        raise RecordError("the report is empty")
    try:
        return raw, LINES.split(raw.decode("utf-8"))
    except UnicodeDecodeError as e:
        raise RecordError("the report is not valid UTF-8") from e


def cmd_write(root: Path, item_arg: str, kind: str, reviewer: str, report: Path, verifies: str | None) -> Path:
    item = resolve_item(root, item_arg)
    require_staged(root, item)
    if kind not in enum("kind"):
        raise RecordError(f"kind `{kind}` is not one of: {', '.join(enum('kind'))}")
    if (kind == "verify") != bool(verifies):
        raise RecordError("--verifies is required for kind verify and only allowed there")
    tree = spec_check.IndexTree(root)
    current = content_hash(tree, item)
    owner = readme_facts(tree, item).get("owner")
    if problem := reviewer_problem(reviewer, owner):
        raise RecordError(problem)
    target = verifies_target(root, item, verifies, owner) if verifies else None
    code_class = (target.cls if target else kind) == "code"

    raw, lines = read_report(report)
    verdicts = enum("verdict")
    last = last_line(lines)
    if last not in {f"VERDICT: {v}" for v in verdicts}:
        raise RecordError("the report's last non-blank line must be exactly one of: "
                          + ", ".join(f"`VERDICT: {v}`" for v in verdicts))
    verdict = last[len("VERDICT: "):]
    outside = outside_fences(lines)
    reviewed = [m.group(1) for line in outside if (m := REVIEWED.fullmatch(line))]
    if len(reviewed) != 1:
        raise RecordError(f"the report needs exactly one `REVIEWED: sha256:<hex>` line outside code fences, found {len(reviewed)}")
    if reviewed[0] != current:
        raise RecordError(f"the report's REVIEWED hash {reviewed[0][7:15]} is not the item's current hash "
                          f"{current[7:15]}: the item changed since the brief, so brief the reviewer again")
    claimed = [m.group(1) for line in outside if (m := REVIEWED_COMMIT.fullmatch(line))]
    commit_lines = [line for line in outside if line.startswith("REVIEWED-COMMIT:")]
    full_commit = None
    if code_class:
        if len(claimed) != 1 or len(commit_lines) != 1:
            raise RecordError(f"a code report needs exactly one `REVIEWED-COMMIT: <sha>` line, found {len(commit_lines)}")
        resolved = git(root, "rev-parse", "--verify", "-q", f"{claimed[0]}^{{commit}}", ok_codes=(0, 1)).strip()
        if not resolved:
            raise RecordError(f"REVIEWED-COMMIT {claimed[0]} is not a commit in this repository")
        full_commit = resolved
    elif commit_lines:
        raise RecordError("a design report must not carry a REVIEWED-COMMIT line")

    for rec in disk_records(root, item, owner):  # the same report recorded again is a no-op (FR-6)
        if (not rec.invalid and rec.fm["kind"] == kind and rec.fm["content"] == current
                and rec.body.encode("utf-8") == raw):
            return root / item / "reviews" / rec.name

    stamp = now()  # one reading: the file name's date and `recorded` agree
    fm = {"kind": kind, "reviewer": reviewer, "verdict": verdict, "content": current, "commit": full_commit,
          "verifies": target.name if target else None, "recorded": stamp.strftime(TIME_FORMAT)}
    head = "\n".join(["---", *[f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fm.items() if v is not None], "---"])
    return link_record(root / item / "reviews", f"{stamp.strftime('%Y-%m-%d')}-{kind}-{current[7:15]}",
                       f"{head}\n".encode("utf-8") + raw)


def link_record(folder: Path, base: str, content: bytes) -> Path:
    """FR-6: build the record in `.<name>.<pid>.tmp`, then link it to the first free name (-2, -3 on a clash)."""
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f".{base}.md.{os.getpid()}.tmp"
    try:
        tmp.write_bytes(content)
        for n in range(1, MAX_NAME_SUFFIX + 1):
            final = folder / (f"{base}.md" if n == 1 else f"{base}-{n}.md")
            try:
                os.link(tmp, final)
                return final
            except FileExistsError:
                continue
        raise RecordError(f"no free record name after {MAX_NAME_SUFFIX} tries for {base}")
    finally:
        tmp.unlink(missing_ok=True)


def cmd_verify(root: Path, which: str) -> int:
    """FR-9: fresh, stale or invalid for every record on disk, judged against the chosen tree."""
    tree = spec_check.HeadTree(root) if which == "head" else spec_check.IndexTree(root)
    _ = tree.listing  # a tree git cannot read fails here, before any output
    bad = False
    for readme in sorted((root / "docs" / "work").glob("*/README.md")) if (root / "docs" / "work").is_dir() else []:
        item = f"docs/work/{readme.parent.name}"
        folder = root / item / "reviews"
        if not folder.is_dir():
            continue
        facts = readme_facts(tree, item)
        try:
            current: str | None = content_hash(tree, item)
            why = ""
        except HashError as e:
            current, why = None, f"cannot hash the item in the {which} tree: {e}"
        for rec in sorted(disk_records(root, item, facts.get("owner")), key=lambda r: r.name):
            if rec.invalid:
                state, detail, bad = "invalid", rec.invalid, True
            elif current is not None and rec.fm["content"] == current:
                state, detail = "fresh", rec.fm["verdict"]
            else:
                state, detail = "stale", why or f"{rec.fm['verdict']}; reviewed {rec.fm['content'][7:15]}"
            print(f"{state}\t{item}/reviews/{rec.name}\t{detail}")
        for tmp in sorted(folder.glob(".*.tmp")):
            print(f"info\t{item}/reviews/{tmp.name}\tleftover temp file of a crashed writer; never a record")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", type=Path, help="the repository (default: the one holding the current directory)")
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = parser.add_subparsers(dest="command", required=True)
    h = sub.add_parser("hash", parents=[common], help="print the content hash of the staged item")
    h.add_argument("--item", required=True)
    w = sub.add_parser("write", parents=[common], help="record a reviewer's report")
    w.add_argument("--item", required=True)
    w.add_argument("--kind", required=True)
    w.add_argument("--reviewer", required=True)
    w.add_argument("--report", required=True, type=Path)
    w.add_argument("--verifies")
    v = sub.add_parser("verify", parents=[common], help="list every record as fresh, stale or invalid")
    v.add_argument("--tree", choices=("head", "index"), default="head")
    args = parser.parse_args(argv)
    try:
        root = args.root or Path(git(Path.cwd(), "rev-parse", "--show-toplevel").strip())
        if args.command == "hash":
            print(cmd_hash(root, args.item))
        elif args.command == "write":
            print(cmd_write(root, args.item, args.kind, args.reviewer, args.report, args.verifies)
                  .relative_to(root).as_posix())
        else:
            return cmd_verify(root, args.tree)
    except RecordError as e:
        print(f"review_record: refused: {e}", file=sys.stderr)
        return 1
    except (OSError, spec_check.ToolError, subprocess.TimeoutExpired) as e:
        print(f"review_record: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
