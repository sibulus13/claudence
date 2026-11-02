---
id: fix-gate-trailer-hint
type: bugfix
status: draft
touches: [harness]
layers:
  architecture: none
  component: none
  functional: none
  data: none
created: "2026-11-02"
owner: harness
lifecycle: false
---
# The gate reads trailers differently from git, and says "no Spec trailer" without the cause

## References

### Local

| Source (file:line) | Status (working / partial / broken) | What it shows | Decision (extract / wrap / replace / ignore) + reason |
|---|---|---|---|
| C:/Users/Michael/.claude/scripts/spec_gate.py:172-173 | broken | the gate strips `#` lines itself, then runs `git interpret-trailers --parse` without `--no-divider`: a `---` body line or `git commit -v` hides correct trailers | replace: git parses the raw message file |
| C:/Users/Michael/.claude/scripts/spec_gate.py:185-187 | partial | the reject message says the trailer is missing, never why | wrap: name the cause |
| C:/Users/Michael/.claude/scripts/spec_gate.py:219-225 | broken | `git_trailers` ignores the exit code, so a failed parse reads as "no trailer" | replace: a failure is a gate error (fails closed) |
| C:/Users/Michael/.claude/tests/test_spec_gate.py:1 | working | real-commit tests through the commit-msg hook | extract: the regression cases go here |

### Web

| Source (URL) | Date checked | What it shows | Decision |
|---|---|---|---|
| https://git-scm.com/docs/git-interpret-trailers | 2026-11-02 | the trailer block is the final group of lines, preceded by a blank line, all trailers (or 25% with a git-generated one); `--no-divider` stops `---` ending the message; `trailer.*` config changes parsing | extract: run on the raw file with `--no-divider` and `trailer.separators=:` |

## Operating envelope

| Assumption | How it is observed (not hoped) | If violated |
|---|---|---|
| The commit-msg hook receives git's message file, possibly with comments, a scissors line and a diff under `commit -v` | design review probe 2026-11-02 with a real `git commit -v`, an editor stub and a logging hook; AC-2 repeats it | refuse: an unparseable message is a gate error, never "no trailer" |

## Root cause

The gate reimplements part of git's message cleanup (dropping `#` lines) and calls the trailer parser without
`--no-divider`. So it disagrees with git's own reading (`git log --format=%(trailers)`) whenever the body has a `---`
line or `commit -v` appends a diff. On top of that, the message names a missing trailer without the cause.

## Observed vs expected

- **Observed:**
  - On 2026-10-31, a `Spec:` line in its own paragraph above the attribution was rejected as "no trailer".
  - The probes on 2026-11-02 showed every correct commit is rejected under `commit -v`, and under a `---` line in the body.
- **Expected:**
  - **Trailers:** git reads them from the raw message file: `git -c trailer.separators=: interpret-trailers --parse --no-divider <file>`. Git handles comments, `core.commentChar` and the scissors line itself, and a non-zero exit is a gate error.
  - **Revert check:** the body used for it is the text above the scissors line with comment lines removed, as today.
  - **Hint trigger:** a line above the scissors matching `^\s*spec\s*:\s*docs/work/` (any case), whose value git did not return as a `Spec` trailer.
  - **Hint cause:** the first that applies, in this order:
    1. the final paragraph has a non-trailer line, which the hint quotes;
    2. the key is not exactly `Spec`;
    3. text follows the path;
    4. the line is indented;
    5. the line is outside the final paragraph.
  - **No hint:** a `Spec:` line that is not path-shaped never triggers one.

## Acceptance criteria

| AC | Traces | Given / when | Pass when | Fail when | Test |
|---|---|---|---|---|---|
| AC-1 | - | a source commit whose valid `Spec:` sits in the final trailer block, with a `---` line earlier in the body | it lands | it is rejected | tests/test_spec_gate.py |
| AC-2 | - | the same commit made by a real `git commit -v` with an editor stub (scissors line and diff in the hook file, including `+Spec: docs/work/x/README.md` diff lines), and with `core.commentChar` set to `;` | both land, and no hint comes from the diff lines | either is rejected or hints | tests/test_spec_gate.py |
| AC-3 | - | `Spec: docs/work/<id>/README.md` in its own paragraph above a `Co-Authored-By:` block; and as the subject line only | both rejected; stderr says the line is outside the final trailer block | either lands or the cause is missing | tests/test_spec_gate.py |
| AC-4 | - | the final paragraph holds `Spec:` plus `🤖 Generated with …`; `spec:` lower case in a valid block; `Spec: <path> (building)`; `  Spec: <path>` indented | each is rejected with its own cause, by the stated order | a cause is wrong or missing | tests/test_spec_gate.py |
| AC-5 | - | no `Spec` line at all; `Spec: see the README for why` at a line start; `> Spec: x` quoted; `Specs: docs/work/x/README.md` | each rejected with the plain existing message and no hint, except `Specs:`, which gets the key-case cause | a hint appears where none should | tests/test_spec_gate.py |
| AC-6 | - | the repo sets `trailer.separators` to `=`; and a unit test of `git_trailers` with `subprocess.run` patched to return exit 1 (this tests the return-code check, not git) | the first still reads `Spec: x` as a trailer; the second raises a gate error | either reads as "no trailer" | tests/test_spec_gate.py |

## Gate plan

| Risk | Kind (deterministic / qualitative) | Check | Blocking / advisory |
|---|---|---|---|
| the gate loosens (a non-trailer Spec line lands) or rejects a correct commit | deterministic | python -m pytest tests/test_spec_gate.py -q | blocking |
