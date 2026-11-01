"""Validate a work item against the Work-Item Standard v2 (rules CK-1..CK-26), or a legacy docs/specs file.

    python spec_check.py <repo>/docs/work/<id>/README.md [--root <repo>] [--for-source-commit]

Output: `CK-n: <file>: <message>` per error, `warn: CK-n: <file>: <message>` per warning. Exit 0 with no errors
(warnings alone exit 0), 1 on any error, 2 on unreadable input or a failed tool. Standard:
~/.claude/skills/dark-factory/WORK-ITEM-STANDARD.md. Work items: docs/work/spec-gate-checker/ (this checker) and
docs/work/spec-gate/ (the commit gate that calls it).

What each tool owns:
  frontmatter (CK-1/2/3 profiles/17 keys/21/25 types)  contracts/work-item.v2.json, validated with jsonschema
  tables (CK-5/7/8/9/10 format/11/13)                  markdown-it-py rows validated by the pydantic models in work_item_md
  required headings (CK-4)                             markdownlint MD043, config generated from the standard
  diagrams (CK-6/15/22)                                the Mermaid parser (scripts/spec_lint.mjs)
  everything else is custom: cross-references (traces, mirror, nesting size, test citation), status tiers, file existence.
A file is read through a Tree: the working tree for the CLI, the git index for the commit gate.
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
from functools import cached_property
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import work_item_schema  # noqa: E402
from work_item_md import (AcRow, CapRow, ChosenRow, Doc, EnvelopeRow, Fence, FrRow, LocalRefRow, citations, NfrRow,  # noqa: E402
                          PatternRow, Section, Table, TradeoffRow, WebRefRow, parse_rows)

CLAUDE = Path(__file__).resolve().parents[1]
HEADINGS = json.loads((CLAUDE / "contracts" / "work-item.headings.v2.json").read_text(encoding="utf-8"))
LINT_SCRIPT = CLAUDE / "scripts" / "spec_lint.mjs"
CACHE_DIR = CLAUDE / "cache" / "spec_check"
LINT_TIMEOUT_S = 90
GIT_TIMEOUT_S = 10

LAYER_FILES = {"architecture": "architecture.md", "component": "components.md", "functional": "functional.md",
               "data": "data.md"}
MAX_ACS = 15
MAX_PARTICIPANTS = 5
MAX_CITED_BYTES = 5_000_000  # a cited file larger than this cannot be verified (CK-48, CK-49)
COMPONENT_H3S = ["Interface", "Functional requirements", "Data", "Failure modes", "Budget"]
AC_TYPES = {"feature", "integration", "bugfix", "refactor", "data-collection"}  # types that must carry an AC table
L0_TYPES = {"feature", "integration", "data-collection"}  # types with a Capabilities section

ALWAYS = {"CK-1", "CK-2", "CK-3", "CK-18"}
STATIC = ALWAYS | {f"CK-{n}" for n in (*range(4, 18), 19, 21, 22, 23, 47, 48, 49)}
EXEC = STATIC | {"CK-20", "CK-24"}
SHIPPED = EXEC | {"CK-25"}
TIERS = {"draft": ALWAYS, "spec-locked": STATIC, "building": EXEC, "shipped": SHIPPED, "killed": ALWAYS | {"CK-21"},
         "promoted": ALWAYS | {"CK-21"}}

TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|e2e)/|(^|/)test_[^/]*$|\.(test|spec)\.[^/]+$", re.I)
PLACEHOLDER = re.compile(r"<(?:\.\.\.|[A-Za-z_][^<>]*)>|YYYY-MM-DD|\bEXAMPLE\b")
EXEMPT_IN_CELL = re.compile(r"`[^`]*`|<br\s*/?>")  # inline code and line breaks are not placeholders (CK-19)
NESTED_STUB = re.compile(r"^Nested spec: `?docs/work/([\w.-]+)/")
ID_PART = re.compile(r"^[\w.-]+$")


class ToolError(RuntimeError):
    """A helper tool (node, markdownlint, the Mermaid parser) failed or timed out. Never treated as a pass."""


# ---------------------------------------------------------------- trees: where files are read from

class Tree:
    """Repo-relative file access. `DiskTree` is the working tree; `IndexTree` is what git is about to commit."""

    def read(self, rel: str) -> str | None:
        raise NotImplementedError

    def is_file(self, rel: str) -> bool:
        raise NotImplementedError

    def exists(self, rel: str) -> bool:
        raise NotImplementedError


class DiskTree(Tree):
    def __init__(self, root: Path) -> None:
        self.root = root

    def read(self, rel: str) -> str | None:
        p = self.root / rel
        return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None

    def is_file(self, rel: str) -> bool:
        return (self.root / rel).is_file()

    def exists(self, rel: str) -> bool:
        return (self.root / rel).exists()


class IndexTree(Tree):
    """The staged content: the commit gate must judge what will be committed, never the working tree."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _git(self, *args: str) -> bytes:
        try:
            r = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, timeout=GIT_TIMEOUT_S)
        except subprocess.TimeoutExpired as e:
            raise OSError(f"git {args[0]} timed out") from e
        if r.returncode:
            raise OSError(f"git {' '.join(args[:2])} exited {r.returncode}: {r.stderr.decode(errors='replace')[:200]}")
        return r.stdout

    @cached_property
    def files(self) -> set[str]:
        return {f for f in self._git("ls-files", "-z").decode("utf-8", "replace").split("\0") if f}

    def read(self, rel: str) -> str | None:
        return self._git("show", f":{rel}").decode("utf-8", "replace") if rel in self.files else None

    def is_file(self, rel: str) -> bool:
        return rel in self.files

    def exists(self, rel: str) -> bool:
        return rel in self.files or any(f.startswith(rel.rstrip("/") + "/") for f in self.files)


def inside(base: str, rel: str) -> str | None:
    """`rel` joined to `base` and normalised, or None when it escapes `base` (absolute, drive-letter or `..`)."""
    if not rel or posixpath.isabs(rel) or re.match(r"^[A-Za-z]:", rel) or "\\" in rel:
        return None
    p = posixpath.normpath(posixpath.join(base, rel))
    return p if p != "." and (p == base or p.startswith(base.rstrip("/") + "/") or not base) and not p.startswith("..") else None


# ---------------------------------------------------------------- tools: markdownlint MD043 and the Mermaid parser

def _tool_versions() -> str:
    modules = CLAUDE / "node_modules"
    if not modules.is_dir():
        raise ToolError(f"node_modules is missing: run `pnpm install` in {CLAUDE}")
    return "|".join(json.loads((modules / p / "package.json").read_text(encoding="utf-8"))["version"]
                    for p in ("markdownlint-cli2", "mermaid", "jsdom"))


def run_lint(headings: list[dict], diagrams: list[dict]) -> tuple[dict, dict]:
    """Results by key. Units are cached on disk by content hash, so only unseen units start node."""
    versions = _tool_versions()
    keyed = [("h", u, hashlib.sha256(f"{versions}\0{u['heading']}\0{u['text']}".encode()).hexdigest()) for u in headings]
    keyed += [("d", u, hashlib.sha256(f"{versions}\0{u['text']}".encode()).hexdigest()) for u in diagrams]
    results: dict[str, dict] = {}
    missing = []
    for kind, unit, digest in keyed:
        cached = CACHE_DIR / f"{digest}.json"
        if cached.is_file():
            results[digest] = json.loads(cached.read_text(encoding="utf-8"))
        else:
            missing.append((kind, unit, digest))
    if missing:
        payload = {"headings": [{**u, "key": d} for k, u, d in missing if k == "h"],
                   "diagrams": [{**u, "key": d} for k, u, d in missing if k == "d"]}
        try:
            r = subprocess.run(["node", str(LINT_SCRIPT)], input=json.dumps(payload), capture_output=True, text=True,
                               encoding="utf-8", timeout=LINT_TIMEOUT_S, cwd=CLAUDE)
        except subprocess.TimeoutExpired as e:
            raise ToolError(f"spec_lint.mjs timed out after {LINT_TIMEOUT_S}s") from e
        except FileNotFoundError as e:
            raise ToolError("node is not on PATH") from e
        if r.returncode:
            raise ToolError(f"spec_lint.mjs exited {r.returncode}: {r.stderr.strip()[:300]}")
        out = json.loads(r.stdout)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        for digest, res in {**out["headings"], **out["diagrams"]}.items():
            (CACHE_DIR / f"{digest}.json").write_text(json.dumps(res), encoding="utf-8")
            results[digest] = res
    heading_results = {u["key"]: results[d] for k, u, d in keyed if k == "h"}
    diagram_results = {u["key"]: results[d] for k, u, d in keyed if k == "d"}
    return heading_results, diagram_results


# ---------------------------------------------------------------- the work item

class Item:
    """A work item folder read through a tree. Layer files that do not exist are None."""

    def __init__(self, tree: Tree, readme: str) -> None:
        self.tree, self.readme = tree, readme
        self.dir = posixpath.dirname(readme)
        self.id = posixpath.basename(self.dir)
        self.work = posixpath.dirname(self.dir)
        text = tree.read(readme)
        if text is None:
            raise OSError(f"{readme} does not exist")
        m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?", text, re.S)
        self.fm_error: str | None = None
        self.fm: dict = {}
        if not m:
            self.fm_error = "no frontmatter block"
        else:
            try:
                loaded = yaml.safe_load(m.group(1))
            except yaml.YAMLError as e:
                loaded, self.fm_error = None, f"frontmatter does not parse: {str(e).splitlines()[0]}"
            if self.fm_error is None and not isinstance(loaded, dict):
                self.fm_error = "frontmatter is not a mapping"
            elif isinstance(loaded, dict):
                self.fm = loaded
        self.body = text[m.end():] if m else text
        self.doc = Doc(self.body)
        self.texts = {n: tree.read(f"{self.dir}/{n}") for n in LAYER_FILES.values()}
        self.files = {n: Doc(t) if t is not None else None for n, t in self.texts.items()}
        self.lint_headings: dict[str, dict] = {}
        self.lint_diagrams: dict[str, dict] = {}

    @property
    def type(self) -> str:
        return str(self.fm.get("type"))

    @property
    def status(self) -> str:
        return str(self.fm.get("status"))

    @property
    def parent(self) -> str | None:
        return self.fm.get("parent") or None

    @property
    def children(self) -> list[str]:
        c = self.fm.get("children")
        return [str(x) for x in c] if isinstance(c, list) else []

    @property
    def is_full(self) -> bool:
        return self.type in ("feature", "integration") and not self.parent

    @property
    def is_lite(self) -> bool:
        return self.type == "data-collection" or (self.type in ("feature", "integration") and bool(self.parent))

    def layer(self, name: str) -> str:
        layers = self.fm.get("layers")
        return str(layers.get(name)) if isinstance(layers, dict) else "none"

    def all_docs(self) -> list[tuple[str, Doc]]:
        return [("README.md", self.doc), *[(n, d) for n, d in self.files.items() if d]]

    def declared_docs(self) -> list[tuple[str, Doc]]:
        return [("README.md", self.doc), *[(n, self.files[n]) for layer, n in LAYER_FILES.items()
                                           if self.layer(layer) != "none" and self.files[n]]]

    @cached_property
    def ac_source(self) -> tuple[str, Section | None]:
        """File label and the `Acceptance criteria` section where the profile puts the AC table."""
        func = self.files["functional.md"]
        if self.type in ("bugfix", "refactor"):
            return "README.md", self.doc.section("Acceptance criteria")
        if self.type in ("feature", "integration"):
            return "functional.md", func.section("Acceptance criteria") if func else None
        if func and func.section("Acceptance criteria"):
            return "functional.md", func.section("Acceptance criteria")
        return "README.md", self.doc.section("Acceptance criteria")

    @cached_property
    def acs(self) -> tuple[list[AcRow], list[tuple[str, str]]]:
        section = self.ac_source[1]
        return parse_rows(section.first_table if section else None, AcRow)

    @cached_property
    def caps(self) -> tuple[list[CapRow], list[tuple[str, str]]]:
        section = self.doc.section("Capabilities")
        return parse_rows(section.first_table if section else None, CapRow)

    @cached_property
    def nfrs(self) -> tuple[list[NfrRow], list[tuple[str, str]]]:
        section = self.doc.section("Non-functional requirements")
        return parse_rows(section.first_table if section else None, NfrRow)

    @cached_property
    def frs(self) -> tuple[list[FrRow], list[tuple[str, str]]]:
        rows: list[FrRow] = []
        found: list[tuple[str, str]] = []
        comp = self.files["components.md"]
        for sec in comp.sections(2) if comp else []:
            fr = next((s for s in sec.subs if s.title.lower() == "functional requirements"), None)
            r, f = parse_rows(fr.first_table if fr else None, FrRow)
            rows, found = rows + r, found + f
        return rows, found


def _row_ids(item: Item, title: str) -> list[str]:
    section = item.doc.section(title)
    return [r[0] for r in section.first_table.rows if r] if section and section.first_table else []


Item.row_ids = _row_ids  # ids of every row of a README table, including rows that failed validation


def load_sibling(item: Item, item_id: str) -> Item | None:
    readme = f"{item.work}/{item_id}/README.md"
    return Item(item.tree, readme) if ID_PART.match(item_id) and item.tree.is_file(readme) else None


# ---------------------------------------------------------------- reporting and the entry points

class Report:
    def __init__(self, enabled: set[str]) -> None:
        self.enabled = enabled
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, rule: str, file: str, msg: str) -> None:
        if rule in self.enabled:
            self.errors.append(f"{rule}: {file}: {msg}")

    def warn(self, rule: str, file: str, msg: str) -> None:
        if rule in self.enabled:
            self.warnings.append(f"warn: {rule}: {file}: {msg}")

    def failed(self, *rules: str) -> bool:
        return any(e.split(":", 1)[0] in rules for e in self.errors)

    def add(self, file: str, findings: list[tuple[str, str]]) -> None:
        for rule, msg in findings:
            self.err(rule, file, msg)


def check_item(readme: Path, root: Path | None = None, for_source_commit: bool = False,
               require_sections: bool = False) -> tuple[list[str], list[str]]:
    """Check a work item on disk. Returns (error lines, warning lines). Raises OSError when the README is unreadable."""
    root = (root or readme.resolve().parents[3]).resolve()
    rel = readme.resolve().relative_to(root).as_posix()
    return check_work_item(DiskTree(root), rel, for_source_commit, require_sections)


def check_work_item(tree: Tree, readme: str, for_source_commit: bool = False,
                    require_sections: bool = False) -> tuple[list[str], list[str]]:
    item = Item(tree, readme)
    item.require_sections = require_sections
    enabled = set(TIERS.get(item.status, ALWAYS)) | ({"CK-26"} if for_source_commit else set())
    rep = Report(enabled)
    if for_source_commit and item.status not in ("building", "shipped"):
        rep.err("CK-26", "README.md", f"status is `{item.status}`; a source commit needs `building` or `shipped`")
    if item.fm_error:
        rep.err("CK-1", "README.md", item.fm_error)
        return rep.errors, rep.warnings
    rep.add("README.md", work_item_schema.findings(item.fm))
    if str(item.fm["id"]) != item.id:
        rep.err("CK-2", "README.md", f"`id` ({item.fm['id']}) must equal the folder name ({item.id})")
    ck18(item, rep)
    if rep.failed("CK-1", "CK-2"):
        return rep.errors, rep.warnings
    ck3(item, rep)
    if enabled & {"CK-4", "CK-6", "CK-15", "CK-22"}:
        run_tools(item)
    for rule_id, rule in RULES:
        if rule_id in enabled:
            rule(item, rep)
    return rep.errors, rep.warnings


RULES = []  # (first rule id, function), filled at the end of the module


def required_headings(item: Item) -> dict[str, list[tuple[str, str]]]:
    """File -> [(heading, rule id)], selected from the generated config (contracts/work-item.headings.v2.json)."""
    entry = HEADINGS["readme"][item.type]
    heads = list(entry["headings"])
    if item.parent:  # a nested spec has the lite L0 plus its type's own headings
        heads = HEADINGS["nestedBase"] + [h for h in heads if h not in HEADINGS["l0"]["full"]]
    heads += [c["heading"] for c in entry.get("conditional", []) if c["status"] == item.status]
    out = {"README.md": [(h, "CK-4") for h in dict.fromkeys(heads) if h not in HEADINGS["leading"]]}
    for layer, name in LAYER_FILES.items():
        if item.layer(layer) == "none" or item.files[name] is None:
            continue
        out[name] = []
        for e in HEADINGS["files"][name]:
            if e.get("types") and item.type not in e["types"]:
                continue
            if e.get("when") == "lifecycle" and item.fm.get("lifecycle") is not True:
                continue
            if e.get("when") == "multi-package":
                continue  # CK-27+ (work breakdown) is a later pass
            out[name].append((e["heading"], "CK-4"))
    return {f: [(h, "CK-11" if h == "Acceptance criteria" else rule) for h, rule in hs] for f, hs in out.items()}


def run_tools(item: Item) -> None:
    wanted = required_headings(item)
    texts = {"README.md": item.body, **{n: t for n, t in item.texts.items() if t is not None}}
    heads = [{"key": f"{f}|{h}", "text": texts[f], "heading": h} for f, hs in wanted.items() for h, _ in hs]
    diagrams = [{"key": f"{n}|{fence.line}", "text": fence.body} for n, d in item.all_docs() for fence in d.fences
                if fence.lang == "mermaid"]
    item.lint_headings, item.lint_diagrams = run_lint(heads, diagrams)
    item.wanted_headings = wanted


def diagram(item: Item, name: str, fence: Fence) -> dict:
    return item.lint_diagrams[f"{name}|{fence.line}"]


def parsed(item: Item, name: str, fences: list[Fence]) -> list[dict]:
    return [diagram(item, name, f) for f in fences if f.lang == "mermaid"]


# ---------------------------------------------------------------- rules

def ck18(item: Item, rep: Report) -> None:
    if item.parent:
        parent = load_sibling(item, str(item.parent))
        if parent is None:
            rep.err("CK-18", "README.md", f"parent `{item.parent}` does not exist")
        elif item.id not in parent.children:
            rep.err("CK-18", "README.md", f"parent `{item.parent}` does not list `{item.id}` in `children`")
    for cid in item.children:
        child = load_sibling(item, cid)
        if child is None:
            rep.err("CK-18", "README.md", f"child `{cid}` does not exist")
        elif child.parent != item.id:
            rep.err("CK-18", "README.md", f"child `{cid}` does not name `{item.id}` as its `parent`")


def ck3(item: Item, rep: Report) -> None:
    """File existence per declared layer. The per-type layer profile is in the JSON Schema."""
    for layer, name in LAYER_FILES.items():
        value, has_file = item.layer(layer), item.files[name] is not None
        if value != "none" and not has_file:
            rep.err("CK-3", name, f"layer `{layer}` is `{value}` but {name} does not exist")
        elif value == "none" and has_file:
            rep.warn("CK-3", name, f"layer `{layer}` is `none` but {name} exists")


def ck4(item: Item, rep: Report) -> None:
    for name, heads in item.wanted_headings.items():
        for heading, rule in heads:
            res = item.lint_headings[f"{name}|{heading}"]
            if not res["ok"]:
                rep.err(rule, name, f"missing section `## {heading}` ({res['detail']})")
    comp = item.files["components.md"]
    if comp and item.type in ("feature", "integration") and item.layer("component") != "none" and not comp.sections(2):
        rep.err("CK-4", "components.md", "needs one `## <component>` section per component")


def ck5(item: Item, rep: Report) -> None:
    if not item.is_full:
        return
    for title, model, min_rows in (("Trade-offs", TradeoffRow, 2), ("Components chosen", ChosenRow, 1),
                                   ("Patterns applied", PatternRow, 1)):
        section = item.doc.section(title)
        if section is None or section.first_table is None:
            continue
        rows, found = parse_rows(section.first_table, model)
        rep.add("README.md", [(r, f"`{title}`: {m}") for r, m in found])
        if rows and len(rows) < min_rows or not rows and not found:
            rep.err("CK-5", "README.md", f"`{title}` needs at least {min_rows} row(s), has {len(rows)}")
        if title == "Trade-offs" and rows and sum(r.verdict.lower() == "chosen" for r in rows) != 1:
            rep.err("CK-5", "README.md", "`Trade-offs` needs exactly one verdict `chosen`")


def ck6(item: Item, rep: Report) -> None:
    for name, doc in item.declared_docs():
        if name == "README.md" and item.type in ("bugfix", "research"):
            continue
        first = doc.first_block_after_h1()
        if not isinstance(first, Fence) or first.lang != "mermaid":
            rep.err("CK-6", name, "the first block after the H1 must be a ```mermaid fence")
        elif not diagram(item, name, first)["ok"]:
            continue
        elif name == "README.md" and not first.body.lstrip().startswith("flowchart"):
            rep.err("CK-6", name, "the README diagram must be a `flowchart`")
        elif name in ("architecture.md", "components.md") and not {"Before", "After"} <= set(diagram(item, name, first)["subgraphs"]):
            rep.err("CK-6", name, "the diagram needs `subgraph Before` and `subgraph After`")
    for name, doc in item.all_docs():
        for fence in doc.fences:
            res = diagram(item, name, fence) if fence.lang == "mermaid" else {"ok": True}
            if not res["ok"]:
                rep.err("CK-6", name, f"mermaid diagram at line {fence.line + 1} does not parse: {res['error']}")


def ck7(item: Item, rep: Report) -> None:
    if not (item.is_full or item.is_lite):
        return
    rows, found = item.caps
    rep.add("README.md", [(r, f"`Capabilities`: {m}") for r, m in found])
    ids = [r.cap for r in rows]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        rep.err("CK-7", "README.md", f"duplicate {dup}")
    n = len(rows)
    if item.is_full and not 5 <= n <= 10:
        rep.warn("CK-7", "README.md", f"{n} capabilities; guidance is 5-10 (fewer is too thin, more is two items)")
    if item.is_lite and not 1 <= n <= 10:
        rep.err("CK-7", "README.md", f"{n} capabilities; a lite L0 needs 1-10")


def ck8(item: Item, rep: Report) -> None:
    rows, found = item.nfrs
    rep.add("README.md", [(r, f"`Non-functional requirements`: {m}") for r, m in found])
    ids = [r.nfr for r in rows]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        rep.err("CK-8", "README.md", f"duplicate {dup}")


def ck10(item: Item, rep: Report) -> None:
    acs = {r.ac: r for r in item.acs[0]}
    for r in item.nfrs[0]:
        if not any(r.nfr in a.trace_ids for a in acs.values()):
            rep.err("CK-10", "README.md", f"{r.nfr} is not traced by any AC")
        parts = r.evidence.split(" + ")
        for p in parts:
            if p.startswith("AC-") and not (p in acs and r.nfr in acs[p].trace_ids):
                rep.err("CK-10", "README.md", f"{r.nfr} evidence {p} is not an AC row that traces {r.nfr}")
        kind = next((k for k in ("fitness", "spike") if r.method.startswith(k)), "")
        has = lambda prefix: any(p.startswith(prefix) for p in parts)  # noqa: E731
        if kind == "fitness" and not (has("AC-") and has("config:")):
            rep.err("CK-10", "README.md", f"{r.nfr} `fitness` evidence needs an AC and a config: token")
        if kind == "spike" and not (has("AC-") and has("decision:")):
            rep.err("CK-10", "README.md", f"{r.nfr} `spike` evidence needs an AC and a decision: token")
        if not kind and not has("AC-"):
            rep.err("CK-10", "README.md", f"{r.nfr} evidence needs an AC token")


def ck11(item: Item, rep: Report) -> None:
    label, section = item.ac_source
    if item.type == "research" or (item.type not in AC_TYPES and section is None):
        return
    if section is None:
        if item.type == "data-collection":
            rep.err("CK-11", label, "no acceptance criteria table")
        return
    if section.first_table is None:
        rep.err("CK-11", label, "no acceptance criteria table")
        return
    rows, found = item.acs
    rep.add(label, found)
    if not rows and not found:
        rep.err("CK-11", label, "acceptance criteria table has no AC-n rows")
    ids = [r.ac for r in rows]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        rep.err("CK-11", label, f"duplicate {dup}")
    for r in rows:
        if r.traces == "-" and item.type not in ("bugfix", "refactor"):
            rep.err("CK-11", label, f"{r.ac} Traces `-` is only allowed for bugfix and refactor")


def ck12_13_14(item: Item, rep: Report) -> None:
    rows, _ = item.acs
    traced = {t for r in rows for t in r.trace_ids}
    caps, nfrs = item.row_ids("Capabilities"), item.row_ids("Non-functional requirements")
    frs, fr_found = item.frs
    rep.add("components.md", fr_found)
    fr_ids = [r.fr for r in frs]
    if item.type in L0_TYPES or item.parent:
        for cap in caps:
            if cap not in traced:
                rep.err("CK-12", "README.md", f"{cap} is not traced by any AC")
    known = {*caps, *nfrs, *fr_ids}
    for r in rows:
        for t in r.trace_ids:
            if t != "-" and t not in known:
                rep.err("CK-13", item.ac_source[0], f"{r.ac} traces `{t}` which is not defined in this work item")
    for f in sorted({f for f in fr_ids if fr_ids.count(f) > 1}):
        rep.err("CK-13", "components.md", f"duplicate {f}")
    for f in fr_ids:
        if f not in traced:
            rep.warn("CK-14", "components.md", f"{f} is not traced by any AC")


def ck15(item: Item, rep: Report) -> None:
    arch = item.files["architecture.md"]
    if item.fm.get("lifecycle") is True and item.layer("architecture") == "none":
        rep.err("CK-15", "README.md", "`lifecycle: true` needs an architecture layer (architecture is `none`)")
    if arch is None or item.layer("architecture") == "none":
        return
    life = arch.section("Lifecycle")
    if life is not None and item.fm.get("lifecycle") is not True:
        rep.err("CK-15", "architecture.md", "`## Lifecycle` exists but README does not say `lifecycle: true`")
    if life is not None and not any(d["type"].startswith("stateDiagram") for d in parsed(item, "architecture.md", life.fences)):
        rep.err("CK-15", "architecture.md", "`## Lifecycle` must hold a stateDiagram")
    calls = arch.section("Call chains")
    if item.type in ("feature", "integration") and calls is not None \
            and not any(d["type"] == "sequence" for d in parsed(item, "architecture.md", calls.fences)):
        rep.err("CK-15", "architecture.md", "`## Call chains` must hold at least one sequenceDiagram")


def ck16(item: Item, rep: Report) -> None:
    comp = item.files["components.md"]
    if comp is None or item.type not in ("feature", "integration"):
        return
    for sec in comp.sections(2):
        first = sec.first_text
        if first.startswith("Nested spec: ") and not sec.subs:
            stub = NESTED_STUB.match(first)
            if not stub or stub.group(1) not in item.children:
                rep.err("CK-16", "components.md", f"nested stub `{sec.title}` must name a child listed in `children`")
            continue
        titles = iter(t.lower() for t in (s.title for s in sec.subs))
        if not all(h.lower() in titles for h in COMPONENT_H3S):
            rep.err("CK-16", "components.md", f"`## {sec.title}` needs the H3s in order: {', '.join(COMPONENT_H3S)}")


def family_acs(parent: Item) -> int:
    return len(parent.acs[0]) + sum(len(c.acs[0]) for cid in parent.children if (c := load_sibling(parent, cid)))


def ck17(item: Item, rep: Report) -> None:
    """The nesting keys are in the JSON Schema; the size trigger needs the sibling items."""
    triggers = item.fm.get("nestTrigger")
    if item.parent and isinstance(triggers, list) and "size" in triggers:
        parent = load_sibling(item, str(item.parent))
        if parent and family_acs(parent) <= MAX_ACS:
            rep.err("CK-17", "README.md", f"trigger `size` but parent plus children total {family_acs(parent)} ACs (needs > {MAX_ACS})")


def ck19(item: Item, rep: Report) -> None:
    def walk(value: object, path: str) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, f"{path}.{k}")
        elif isinstance(value, list):
            for v in value:
                walk(v, path)
        elif isinstance(value, str) and PLACEHOLDER.search(EXEMPT_IN_CELL.sub("", value)):
            rep.err("CK-19", "README.md", f"frontmatter `{path}` still holds a placeholder: {value}")

    walk(item.fm, "")
    for name, doc in item.all_docs():
        for table in doc.tables:
            for cell in [*table.header, *(c for row in table.rows for c in row)]:
                if PLACEHOLDER.search(EXEMPT_IN_CELL.sub("", cell)):
                    rep.err("CK-19", name, f"placeholder left in table cell: {cell[:60]}")


def cites(text: str, ref: str) -> bool:
    """An exact citation: `demo/AC-1` does not match `demo/AC-10` or `x-demo/AC-1`."""
    return re.search(rf"(?<![\w/-]){re.escape(ref)}(?!\d)", text) is not None


def ck20(item: Item, rep: Report) -> None:
    label = item.ac_source[0]
    for r in item.acs[0]:
        names = [t.strip().strip("`").split("::")[0] for t in re.split(r",|<br\s*/?>", r.test) if t.strip()]
        texts = []
        for n in names:
            path = inside("", n)
            if path is None:
                rep.err("CK-20", label, f"{r.ac}: test path `{n}` must resolve inside the repo")
            elif not TEST_PATH.search(path):
                rep.err("CK-20", label, f"{r.ac}: `{n}` is not a test file (under tests/, test_*, *.test.*, *.spec.*)")
            elif (text := item.tree.read(path)) is None:
                rep.err("CK-20", label, f"{r.ac}: test file `{n}` not found")
            else:
                texts.append(text)
        if texts and len(texts) == len(names) and not any(cites(t, f"{item.id}/{r.ac}") for t in texts):
            rep.err("CK-20", label, f"{r.ac}: {', '.join(names)} does not cite `{item.id}/{r.ac}`")


def ck21(item: Item, rep: Report) -> None:
    """Types and the killed-only key are in the JSON Schema; the superseding item must exist."""
    sup = item.fm.get("supersededBy")
    if sup is not None and not (ID_PART.match(str(sup)) and item.tree.is_file(f"{item.work}/{sup}/README.md")):
        rep.err("CK-21", "README.md", f"`supersededBy` names `{sup}` which is not an existing work item")


def ck22(item: Item, rep: Report) -> None:
    for name, doc in item.all_docs():
        for f in doc.fences:
            res = diagram(item, name, f) if f.lang == "mermaid" else {"actors": []}
            if len(res["actors"]) > MAX_PARTICIPANTS:
                rep.err("CK-22", name, f"a sequenceDiagram has {len(res['actors'])} participants; the limit is {MAX_PARTICIPANTS}")


def ck23(item: Item, rep: Report) -> None:
    n = len(item.acs[0])
    if n > MAX_ACS:
        if item.children:
            rep.warn("CK-23", item.ac_source[0], f"{n} ACs (> {MAX_ACS}); move rows into the children")
        else:
            rep.err("CK-23", item.ac_source[0], f"{n} ACs (> {MAX_ACS}) and no `children`; split the item")


def confirmed_decisions(tree: Tree) -> set[str]:
    text = tree.read("docs/DECISIONS.md") or ""
    ids: set[str] = set()
    for t in Doc(text).tables:
        col = next((i for i, h in enumerate(t.header) if h.strip().lower() == "status"), None)
        ids |= {r[0] for r in t.rows if col is not None and len(r) > col and r[col].strip().lower() == "confirmed"}
    return ids


def ck24(item: Item, rep: Report) -> None:
    decisions = None
    for r in item.nfrs[0]:
        for part in r.evidence.split(" + "):
            if part.startswith("config:"):
                path = inside("", part[7:])
                if path is None or not item.tree.exists(path):
                    rep.err("CK-24", "README.md", f"{r.nfr}: {part} does not exist in the repo")
            elif part.startswith("decision:"):
                decisions = confirmed_decisions(item.tree) if decisions is None else decisions
                if part[9:] not in decisions:
                    rep.err("CK-24", "README.md", f"{r.nfr}: decision row `{part[9:]}` is not in docs/DECISIONS.md with status `confirmed`")


def ck25(item: Item, rep: Report) -> None:
    ev = item.fm.get("evidence")
    paths = list(ev.values()) if isinstance(ev, dict) else ev if isinstance(ev, list) else []
    for p in paths:
        resolved = inside(item.dir, str(p))
        if resolved is None:
            rep.err("CK-25", "README.md", f"evidence path `{p}` must resolve inside the item folder")
        elif not item.tree.exists(resolved):
            rep.err("CK-25", "README.md", f"evidence path `{p}` does not exist under the item folder")


# ---------------------------------------------------------------- References and Operating envelope (CK-47..49)

def resolve_citation(token: str, root: Path) -> str | None:
    """None when `path.ext:line[-line]` names an existing file with that many lines, else the reason it does not."""
    path_part, _, lines = token.rpartition(":")
    path = path_part.replace("\\", "/")
    if path.startswith("~/"):
        path = str(Path.home()) + path[1:]
    p = Path(path) if re.match(r"^([A-Za-z]:/|/)", path) else root / path
    target = Path(os.path.normcase(os.path.normpath(p)))
    a, _, b = lines.partition("-")
    first, last = int(a), int(b or a)
    if first < 1:
        return f"`{token}`: line number must be at least 1"
    if first > last:
        return f"`{token}`: range {first}-{last} runs backwards"
    if not target.is_file():
        return f"`{token}`: {path_part} does not exist"
    if target.stat().st_size > MAX_CITED_BYTES:
        return f"`{token}`: file is too large to verify"
    count = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
    if last > count:
        return f"`{token}`: {path_part} has fewer lines ({count}) than cited"
    return None


def cite_findings(item: Item, rule: str, rep: Report, cells: list[str]) -> None:
    say = rep.warn if item.status == "shipped" else rep.err  # shipped history may drift; anything live must resolve
    for cell in cells:
        for token in citations(cell):
            why = resolve_citation(token, item.tree.root)
            if why:
                say(rule, "README.md", why)


def leading_required(item: Item) -> list[str]:
    optional = set(HEADINGS["readme"].get(item.type, {}).get("optional", []))
    return [h for h in HEADINGS["leading"] if h not in optional or item.parent]


def ck47(item: Item, rep: Report) -> None:
    """Presence and order of the leading sections: right after an optional Overview, References then the envelope."""
    seq = [t for lvl, t, _ in item.doc.headings if lvl == 2]
    lower = [t.lower() for t in seq]
    say = rep.err if getattr(item, "require_sections", False) else rep.warn
    for h in leading_required(item):
        if h.lower() not in lower:
            say("CK-47", "README.md", f"missing section `## {h}`")
    present = [h for h in HEADINGS["leading"] if h.lower() in lower]
    if not present:
        return
    if "overview" in lower and lower.index("overview") > lower.index(present[0].lower()):
        rep.err("CK-47", "README.md", f"`## Overview` must come before `## {present[0]}`")
        return
    start = 1 if lower and lower[0] == "overview" else 0
    actual = seq[start:start + len(present)]
    for got, want in zip(actual, present):
        if got.lower() != want.lower():
            rep.err("CK-47", "README.md", f"`## {got}` must come after `## {want}`")
            return


def ck48(item: Item, rep: Report) -> None:
    section = item.doc.section("References")
    if section is None:
        return
    tables = section.tables
    if len(tables) != 2:
        rep.err("CK-48", "README.md", f"`References` needs exactly two tables, has {len(tables)}")
        return
    for name, table, model in (("Local", tables[0], LocalRefRow), ("Web", tables[1], WebRefRow)):
        rows, found = parse_rows(table, model)
        rep.add("README.md", [(r, f"`{name}`: {m}") for r, m in found])
        if not rows and not found:
            rep.err("CK-48", "README.md", f"`{name}` needs at least 1 row")
        if model is LocalRefRow:
            if any(r.none_found for r in rows) and len(table.rows) > 1:
                rep.err("CK-48", "README.md", "`Local`: `none found` must be the only row")
            cite_findings(item, "CK-48", rep, [c for r in rows for c in (r.source, r.shows)])


def ck49(item: Item, rep: Report) -> None:
    section = item.doc.section("Operating envelope")
    if section is None:
        return
    rows, found = parse_rows(section.first_table, EnvelopeRow) if section.first_table else ([], [])
    rep.add("README.md", [(r, f"`Operating envelope`: {m}") for r, m in found])
    if not rows and not found:
        rep.err("CK-49", "README.md", "`Operating envelope` needs at least 1 row")
    cite_findings(item, "CK-49", rep, [r.observed for r in rows])


RULES.extend([("CK-47", ck47), ("CK-48", ck48), ("CK-49", ck49), ("CK-4", ck4), ("CK-5", ck5), ("CK-6", ck6), ("CK-7", ck7), ("CK-8", ck8), ("CK-10", ck10), ("CK-11", ck11),
              ("CK-12", ck12_13_14), ("CK-15", ck15), ("CK-16", ck16), ("CK-17", ck17), ("CK-19", ck19), ("CK-20", ck20),
              ("CK-21", ck21), ("CK-22", ck22), ("CK-23", ck23), ("CK-24", ck24), ("CK-25", ck25)])


# ---------------------------------------------------------------- legacy v1 (docs/specs/*.md), until migration ends

LEGACY_REQUIRED = ("id", "kind", "status", "created")
LEGACY_ENUMS = {"kind": {"feature", "fix", "build"}, "status": {"draft", "locked", "done", "superseded"}}
TRACED_STATUSES = {"locked", "done"}
LEGACY_AC_HEADER = re.compile(r"^\|\s*AC\s*\|\s*Given\s*/\s*when\s*\|\s*Pass when\s*\|\s*Fail when\s*\|\s*Test\s*\|\s*$", re.I | re.M)
LEGACY_AC_ROW = re.compile(r"^\|\s*(AC-\d+)\s*\|(.*)\|\s*$", re.M)
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def legacy_frontmatter(text: str) -> dict[str, str] | None:
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        return None
    pairs = (line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
    return {k.strip(): v.strip() for k, v in pairs}


def legacy_problems(rel: str, tree: Tree) -> list[str]:
    """Legacy v1 check of a docs/specs file."""
    text = tree.read(rel)
    if text is None:
        return [f"spec not found: {rel}"]
    fm = legacy_frontmatter(text)
    if fm is None:
        return ["no frontmatter block (--- id/kind/status/created ---)"]
    out = [f"frontmatter missing `{k}`" for k in LEGACY_REQUIRED if not fm.get(k)]
    out += [f"frontmatter `{k}` must be one of {sorted(v)}, got `{fm[k]}`" for k, v in LEGACY_ENUMS.items()
            if fm.get(k) and fm[k] not in v]
    stem = posixpath.splitext(posixpath.basename(rel))[0]
    if fm.get("id") and fm["id"] != stem:
        out.append(f"frontmatter `id` ({fm['id']}) must equal the file name ({stem})")
    if fm.get("created") and not DATE.match(fm["created"]):
        out.append("frontmatter `created` must be YYYY-MM-DD")
    header = LEGACY_AC_HEADER.search(text)
    if not header:
        out.append("no acceptance criteria table (| AC | Given / when | Pass when | Fail when | Test |)")
        return out
    rows = LEGACY_AC_ROW.findall(legacy_table(text, header.end()))
    if not rows:
        out.append("acceptance criteria table has no AC-<n> rows")
    if fm.get("status") in TRACED_STATUSES:
        for ac, rest in rows:
            out += legacy_trace_problems(ac, rest, f"{fm.get('id')}/{ac}", tree)
    return out


def legacy_table(text: str, start: int) -> str:
    """Only the rows of the AC table itself: it ends at the first line that is not a table row."""
    lines = []
    for line in text[start:].splitlines()[1:]:
        if not line.strip().startswith("|"):
            break
        lines.append(line)
    return "\n".join(lines)


def legacy_trace_problems(ac: str, rest: str, ref: str, tree: Tree) -> list[str]:
    cell = [c.strip() for c in rest.split("|")][-1].strip("` ")
    tests = [t.strip().strip("`").split("::")[0] for t in re.split(r",|<br\s*/?>", cell) if t.strip()]
    if not tests:
        return [f"{ac}: no test named"]
    paths = {t: inside("", t) for t in tests}
    texts = {t: tree.read(p) if p else None for t, p in paths.items()}
    missing = [t for t, text in texts.items() if text is None]
    if missing:
        return [f"{ac}: test file `{t}` not found" for t in missing]
    if not any(cites(text, ref) for text in texts.values()):
        return [f"{ac}: {', '.join(tests)} does not cite `{ref}`"]
    return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec", type=Path, help="docs/work/<id>/README.md (or a legacy docs/specs/<slug>.md)")
    ap.add_argument("--root", type=Path, help="repo root that test paths are relative to (default: README.parents[3])")
    ap.add_argument("--for-source-commit", action="store_true", help="also require status building or shipped (CK-26)")
    ap.add_argument("--require-sections", action="store_true",
                    help="a missing References or Operating envelope is an error, not a warning (the lifecycle gate)")
    a = ap.parse_args(argv)
    parts = a.spec.resolve().parts
    legacy = any(x == "docs" and y == "specs" for x, y in zip(parts, parts[1:]))
    root = (a.root or (next(p.parent for p in a.spec.resolve().parents if p.name == "docs") if legacy
                       else a.spec.resolve().parents[3])).resolve()
    try:
        rel = a.spec.resolve().relative_to(root).as_posix()
        if legacy:
            tree = DiskTree(root)
            found = legacy_problems(rel, tree)
            status = (legacy_frontmatter(tree.read(rel) or "") or {}).get("status")
            if a.for_source_commit and not found and status not in TRACED_STATUSES:
                found = ["a source commit needs a locked or done spec"]
            if found:
                print("\n".join(found))
            return 1 if found else 0
        errors, warnings = check_work_item(DiskTree(root), rel, a.for_source_commit, a.require_sections)
    except (OSError, ValueError, ToolError) as e:
        print(f"spec_check: {a.spec}: {e}", file=sys.stderr)
        return 2
    if errors or warnings:
        print("\n".join([*errors, *warnings]))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
