# spec-references-envelope: L2 components

```mermaid
flowchart TD
  subgraph Before
    B1[heading table: 8 L0 headings, no References or envelope]
    B2[spec_check: CK-4 presence, CK-5 table rows, created checked by pattern]
  end
  subgraph After
    A1[heading table plus leading and optional notation]
    A2[section-checks: CK-4 filters, CK-47 order, CK-48 References, CK-49 envelope]
    A3[Row models: LocalRefRow, WebRefRow, EnvelopeRow]
    A4[lifecycle gate: spec_gate checks each staged status move against work-item.lifecycle.v1.json and the staged status against its tier]
  end
```

| Component | Owned files | Public interface |
|---|---|---|
| section-checks | `scripts/spec_check.py`, `scripts/work_item_md.py`, `scripts/work_item_schema.py`, `contracts/work-item.v2.json`, `scripts/gen_heading_config.py`, `contracts/work-item.headings.v2.json` (generated), `scripts/spec_gate.py`, `contracts/work-item.lifecycle.v1.json`, `skills/dark-factory/WORK-ITEM-STANDARD.md`, `skills/dark-factory/templates/work-item/README.md`, `skills/dark-factory/templates/work-item/README.experiment.md`, `tests/test_spec_references_envelope.py`, `tests/test_gen_heading_config.py`, `tests/test_spec_gate_lifecycle.py`, `tests/fixtures/work-items/**` | `spec_check.py README.md [--require-sections]` (new rule ids CK-47, CK-48, CK-49); `spec_gate.py` (unchanged CLI; new trigger) |

One component. Its single responsibility: validate the References and Operating envelope sections of one README against the standard. The generators, the Row models and the standard text are its inputs and are changed with it, in the same pass, because splitting them would let the headings, the table headers and the prose disagree. The reviewer agent text (`agents/reviewer.md`) is governance: this item specifies one added sentence (below) which the parent session applies; a test reads it.

## section-checks

### Interface
Signatures only (names and types are the contract; bodies belong to the Implementer).

```
# scripts/work_item_md.py  (same Row base class and parse_rows as CapRow and NfrRow)
# EVIDENCE_TOKEN already exists at work_item_md.py:18 and is imported, never re-spelled.
LOCAL_STATUSES = ("working", "partial", "broken")
DECISIONS      = ("extract", "wrap", "replace", "ignore")
VIOLATED       = ("keep", "refuse", "flag", "defer")
NO_OBSERVATION = ("-", "n/a", "none", "tbd", "todo", "assumed")   # whole-cell, case-insensitive
LOCAL_CITE     : re.Pattern   # one bare token "path.ext:line[-line]"; the extension starts with a letter, so 3.5:1, v1.2:3 and 127.0.0.1:8080 are prose
citations(cell) -> list[str]  # whole backticked `path with space.ext:line` spans first, then bare LOCAL_CITE tokens outside backticks and URLs
OBSERVED_POINTER : re.Pattern # EVIDENCE_TOKEN | LOCAL_CITE | a backticked command | an http(s) URL
MAX_CITED_BYTES = 5_000_000   # a cited file larger than this is an error "too large to verify"

class LocalRefRow(Row):  # RULE "CK-48"
    HEADER = ["Source (file:line)", "Status (working / partial / broken)", "What it shows",
              "Decision (extract / wrap / replace / ignore) + reason"]
    source: str; status: str; shows: str; decision: str
class WebRefRow(Row):    # RULE "CK-48"
    HEADER = ["Source (URL)", "Date checked", "What it shows", "Decision"]
    source: str; date_checked: str; shows: str; decision: str
class EnvelopeRow(Row):  # RULE "CK-49"
    HEADER = ["Assumption", "How it is observed (not hoped)", "If violated"]
    assumption: str; observed: str; violated: str

def resolve_citation(token: str, root: Path) -> str | None   # None when it resolves, else the error text

# scripts/work_item_schema.py + contracts/work-item.v2.json
def findings(frontmatter: dict) -> list[tuple[str, str]]     # signature unchanged; `created` that matches the pattern but is not a
                                                             # real calendar date (date.fromisoformat) is a CK-1 finding

# scripts/gen_heading_config.py
def generate(standard: Path = STANDARD) -> dict      # adds: "leading": list[str], readme[type]["optional"]: list[str] (key absent when empty)

# scripts/spec_check.py
def sections_required(item: Item, require: bool) -> bool   # True under --require-sections (passed by the lifecycle gate from spec-locked on)
def required_headings(item: Item) -> dict[str, list[tuple[str, str]]]   # signature unchanged; see FR-2
def ck47(item: Item, rep: Report) -> None            # STATIC: order check; a missing section is a warning, an error under --require-sections
def ck48(item: Item, rep: Report) -> None            # References section; STATIC
def ck49(item: Item, rep: Report) -> None            # Operating envelope section; STATIC

# scripts/spec_gate.py
LIFECYCLE = "contracts/work-item.lifecycle.v1.json"   # {initial, states, edges: [[from, to], ...], typeEdges: {experiment: [["*", "promoted"]]}}
def staged_item(tree: IndexTree, path: Path) -> Item   # yaml Item loader over the staged blob; unreadable or out-of-enum status raises
def head_status(path: Path) -> str | None            # None when absent at HEAD (git cat-file -e) or HEAD is unborn
def move_allowed(frm: str | None, to: str, item_type: str, *, merging: bool) -> bool   # (None, draft) or one edge; in a merge or squash, any state reachable by edges (and any state for a new item)
def historical(head_text: str | None, moved: bool) -> bool   # no status move and the HEAD version has neither leading section
```

Config and data contracts (all generated; none hand-written):

| File | Key | Type | Required | Meaning |
|---|---|---|---|---|
| `contracts/work-item.headings.v2.json` | `leading` | list of string | yes | the two headings, in order, that follow `Overview` and precede everything else: `References`, `Operating envelope` |
| `contracts/work-item.headings.v2.json` | `readme.TYPE.optional` | list of string | no (absent when empty) | headings of the type validated if present and never required, nested or not |


The walk roots for the one-shot AC-9 gate: `D:/repo/*/*/docs/work` (this includes `D:/repo/Lib/*/docs/work`), `D:/repo/*/docs/work`, and `~/.claude/docs/work`, derived from `fleet_paths.REPO_ROOT`. A root that does not exist fails the gate, never skipped.

Lifecycle rule (the state machine is data; guards attach to its transitions): `spec_gate.py` runs this check FIRST, before its default-branch and merge or rebase early returns, on every commit. For each staged `docs/work/*/README.md` it reads the staged status with the yaml Item loader and the HEAD status (`head_status`). (1) The move must satisfy `move_allowed`; otherwise reject, naming the move. A merge or squash commit (MERGE_HEAD or SQUASH_MSG present) carries a chain of moves that were each gated on their branch, so it accepts any state reachable from the HEAD status (review finding 1, 2026-10-31). A rename (`git diff -M`) is compared with the HEAD version at its old path, so it is a move, never a creation. The HEAD type decides the type edges, so retyping cannot unlock `promoted` in the same commit. An unreadable HEAD status may be repaired to any lifecycle state; the tier check still applies. (2) The staged status must pass its tier (`spec_check.py` at that status, with `--require-sections` from spec-locked on), unless the status did not change and the HEAD version has neither leading section (a historical item), in which case the findings are warnings. An unreadable or out-of-enum staged status rejects; an unreadable HEAD version counts as absent.

Cell rules (each failing cell is one finding, rule `CK-48` or `CK-49`, line format `rule: README.md: message` as for CK-5):

| Table | Cell | Accepts | Rejects |
|---|---|---|---|
| Local | Source | exactly `none found`, or text containing one or more `citations()` tokens (the path may start with a drive letter and may use `/` or `\`; a path with a space is cited inside backticks) | anything else |
| Local | Status | one of LOCAL_STATUSES; exactly `-` on a `none found` row | other words |
| Local | What it shows | non-empty; on a `none found` row it must start `Searched`, then a path containing `/`, then a backtick-quoted pattern | empty; a `none found` row with no search |
| Local | Decision | `word: reason` with word in DECISIONS and a non-empty reason; `n/a: reason` on a `none found` row only | a bare word, other words, an empty reason |
| Local | row set | a `none found` row is the only row of the table | `none found` beside other rows |
| Local, Envelope | every `citations()` token in Source, What it shows, and How it is observed | resolves per `resolve_citation` (below) | a token that does not resolve |
| Web | Source | `http://` or `https://` followed by non-space characters, with no angle brackets; or `n/a: reason` | a bare domain, text |
| Web | Date checked | a real calendar date `YYYY-MM-DD` no later than today (`date.fromisoformat` and a comparison with `date.today()`); exactly `-` on an `n/a` row | other formats, impossible dates, a future date |
| Web | What it shows, Decision | Decision uses the same `word: reason` form; both are exactly `-` on an `n/a` row | empty cells |
| Envelope | Assumption | non-empty | empty |
| Envelope | How it is observed | matches OBSERVED_POINTER (a typed pointer: an `AC-n`, `config:` or `decision:` token, a local `path.ext:line`, a backticked command, or a URL) and is not a NO_OBSERVATION word | empty, `TBD`, prose with no pointer |
| Envelope | If violated | `word: detail`, word in VIOLATED (lower case), non-empty detail | a bare word, other words, upper case |

`If violated` is checked syntactically only: the first word and a non-empty detail. The checker cannot tell whether the stated outcome is really safe; design review and the reviewer rating rule do that.

`resolve_citation(token, root)` (the canonical form, per cross-platform-path-identity): replace `\` with `/`; expand a leading `~/` to the home folder; a token with a drive letter or a leading `/` is absolute, anything else is relative to `root` (the repo root, `--root`); compare and open through `os.path.normcase(os.path.normpath(...))` so `d:\repo\x.js` and `D:/repo/x.js` are the same file; the file must exist and be at most MAX_CITED_BYTES; every cited line number must be at least 1 and at most the file's line count (`splitlines()` of the UTF-8 text with replacement); in a range `a-b`, `a <= b`. CK-48 and CK-49 report an unresolved token as an ERROR at `spec-locked` and `building`, and as a WARNING at `shipped` (history may drift).

Allowed `If violated` outcomes (the fail-safe vocabulary; the cell starts with the word, a colon, a space, then what happens). It is not a single word, because a bare word does not say what is kept, refused or deferred:
- `keep`: leave the current state untouched; take no action on the affected item.
- `refuse`: reject the request or action and report a named reason (non-zero exit, error response).
- `flag`: take no action on the affected item and raise a visible alert (finding, warning line, notification).
- `defer`: take no action now; retry later within a stated bound.
All four mean: no destructive or irreversible action happens on the violated path.

Reviewer sentence to add to `agents/reviewer.md` (applied by the parent session, asserted by AC-10): "Open each cited local path:line and confirm the code says what the References row claims; spot-check at least one web citation per spec."

### Functional requirements
| FR | Requirement |
|---|---|
| FR-1 | `generate()` reads the standard's heading table and emits `References` then `Operating envelope` at the start of both L0 lists, `leading`, and `optional` for experiment, research and bugfix (`Operating envelope`); the counts are pinned by AC-1; `--check` fails on a stale JSON |
| FR-2 | `required_headings` never requires a heading in the type's `optional` list (nested items included); a missing leading heading is a CK-47 warning, and an error under `--require-sections` |
| FR-3 | `ck47` requires the leading headings present in a README to be the first level-2 headings after an optional `Overview`, in `leading` order; the finding names the offending heading |
| FR-4 | `ck48` requires the `References` section to hold exactly two tables, Local then Web, each with the exact header (compared case- and whitespace-insensitively like every Row model), at least one row, and rows that pass LocalRefRow and WebRefRow |
| FR-5 | `ck49` validates the `Operating envelope` section when present: exact header, at least one row, rows that pass EnvelopeRow including the typed observed pointer |
| FR-6 | `spec_gate.py`, before its branch and in-progress early returns, checks every staged work-item README: the status move must be an edge of `contracts/work-item.lifecycle.v1.json` (creation only as draft), and the staged status must pass its tier; a pre-existing README whose status did not change only warns; an unreadable or out-of-enum status rejects |
| FR-7 | The standard, both README templates and the reviewer rating wording carry the sections, tables, vocabularies and rule; a test reads them and compares with the constants |
| FR-8 | CK-47, CK-48 and CK-49 bind at STATIC; present sections are always fully checked (malformed is an error); a missing section is a warning unless `--require-sections`; a `killed` or `promoted` item gets no check |
| FR-9 | `resolve_citation` resolves every `citations()` token as defined above; unresolved is an error at `spec-locked` and `building`, a warning at `shipped` |
| FR-10 | The schema layer rejects a `created` that is not a real calendar date as a CK-1 finding, before any other rule; a CK-1 failure ends the run |

### Data
Reads: the README body through `Doc` (level-2 headings, tables), frontmatter `type`, `status`, `parent`; `contracts/work-item.headings.v2.json`; the cited files; for the gate, the staged version of each work-item README, and its HEAD version for the historical exception only. The authoritative sources: the heading table and the sentence naming the leading headings in the standard (for the heading config); the staged README itself for whether the sections are required (HEAD only to recognise an untouched historical spec), which no author-editable field or list can change; the cited file itself for citation resolution. Writes: nothing at check time. The heading generator writes its config; nothing else is generated.

Standard text added (the Implementer writes the prose; this is its required content):
1. L0 description: `## References` and `## Operating envelope` are items 1 and 2 of the section order, after the optional `## Overview` and before `## Purpose`; each table's exact header and cell rules (the tables above); the typed observed pointer; the `If violated` vocabulary with its four definitions and the statement that it is checked syntactically only.
2. L0 full and lite heading lists begin with `References`, `Operating envelope`.
3. Heading table rows: refactor gains both; bugfix, research and experiment gain `References` and the notation `(optional: `Operating envelope`)`; the sentence naming the leading headings.
4. Per-type profile table: a References/envelope column (feature, integration, data-collection, refactor: required/required; experiment, research, bugfix: required/optional).
5. Checker rules: rows CK-47, CK-48, CK-49 with pass and fail fixtures; line 23 becomes CK-1..CK-49; the STATIC list at line 326 gains CK-47, CK-48 and CK-49; the CK-1 row notes the real-date check; the spec gate row notes the lifecycle rule and points to contracts/work-item.lifecycle.v1.json.
6. Migration section (below).
7. A short section "Reviewer rating against the envelope": a finding that needs an envelope assumption broken is rated F, not R, unless the assumption can break silently; then a cheap detector (a check that ends in keep, refuse, flag or defer) is required and its absence is rated R. A spec that rebuilds something its References list as working, without a stated reason, is flagged. The reviewer opens each cited local line and spot-checks a web citation.
8. `wrap` means extend in place; `extract` means lift the code into the new thing (so the Decision words cover all reuse).

Migration (chosen: the lifecycle as data, owner-approved 2026-10-31; no exemption list, no date cutoff, no flag): specs that predate this item and make no status move only warn. Their next real move (for example building to shipped) must pass its tier, so the Spindle drafts convert when they lock and the building items convert when they ship. Rejected first: an editable `created` cutoff, a regenerable frozen list, a delta rule with four bypasses, and a staged-state invariant that still had to cover invalid states such as creation at shipped; the lifecycle makes those states unreachable instead.

### Failure modes
| Failure | Detection | Handling |
|---|---|---|
| a References or envelope table does not parse as a table | zero tables in the section | CK-48 or CK-49 error, exit 1 |
| a cell is outside its vocabulary or form | the Row model validator | one finding per cell, naming rule, row and column |
| a cited path does not exist, is too large, or has fewer lines than cited | `resolve_citation` | CK-48 or CK-49 error at spec-locked and building, warning at shipped |
| `created` is missing or not a real date | CK-1 (schema layer plus `date.fromisoformat`; runs first) | CK-1 error and no further rules |
| the gate cannot read the HEAD or staged status of a README | `git show` error, or no status | the commit is rejected (fail closed) |
| `leading` missing from the heading config | key lookup at start | error exit 2 naming the key; the gate rejects (never defaults to lenient) |
| the committed config is stale | `gen_heading_config.py --check` exits 1 | the gate fails |
| node helper missing or timed out | existing ToolError | exit 2, the gate rejects |

### Budget
| Dimension | Budget |
|---|---|
| Latency | at most 200 ms added to a spec_check run (table parsing plus up to 50 cited-file reads of at most MAX_CITED_BYTES each) |
| Cost | none: local process, no tokens |
