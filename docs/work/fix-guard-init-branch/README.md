---
id: fix-guard-init-branch
type: bugfix
status: spec-locked
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
# The guard misreads where a `git init` or `git clone` will create a repo

## References

### Local

| Source (file:line) | Status (working / partial / broken) | What it shows | Decision (extract / wrap / replace / ignore) + reason |
|---|---|---|---|
| C:/Users/Michael/.claude/hooks/guard.py:115-130 | broken | `clone_or_init_target` drops tokens starting with `-` but keeps their values, reads only the first `&&` segment, ignores `git -C` and `cd`, finds `git init` anywhere in the text, and returns None (allow) on an unbalanced quote | replace: a command-position, quote-aware parse of every segment |
| C:/Users/Michael/.claude/hooks/guard.py:164 | partial | the target is computed from the raw command; that keeps quoted targets readable (`git init "D:/repo/bad"`) but also reads quoted prose and heredoc bodies as commands | wrap: drop heredoc bodies, then tokenise the raw text with quotes intact and match only at command position |
| C:/Users/Michael/.claude/hooks/guard.py:104-112 | working | `bad_repo_target` allows `D:/repo` itself, a contract pinned by `tests/test_guard.py:134` (fleet-docs-home AC-9) | ignore: unchanged; the init/clone path adds its own "the fleet root itself" check |
| C:/Users/Michael/.claude/tests/test_guard.py:20 | working | `run()` observes only allow or deny | extract: allow cases also assert `clone_or_init_target` directly |

### Web

| Source (URL) | Date checked | What it shows | Decision |
|---|---|---|---|
| https://git-scm.com/docs/git-init | 2026-11-02 | value options: `-b`, `--initial-branch`, `--template`, `--separate-git-dir`, `--object-format`, `--ref-format`; `--shared` takes an optional value only with `=` | extract: the init value-option set; `--shared` is not in it |
| https://git-scm.com/docs/git-clone | 2026-11-02 | value options: `-o`/`--origin`, `-b`/`--branch`, `-u`/`--upload-pack`, `-c`/`--config`, `-j`/`--jobs`, `--reference`, `--reference-if-able`, `--separate-git-dir`, `--depth`, `--template`, `--filter`, `--shallow-since`, `--shallow-exclude`, `--server-option`, `--bundle-uri`, `--revision`, `--ref-format` | extract: the clone value-option set |
| https://git-scm.com/docs/git | 2026-11-02 | global options before the subcommand: `-C <path>` (repeatable, relative ones chain), `-c <name>=<value>`, `--git-dir <path>`, `--work-tree <path>`; `--` ends options | extract: honour `-C`, skip the other values |

## Root cause

The parser treats any token not starting with `-` as positional, so an option's separate value (`-b main`,
`--branch dev`) becomes the target. It also reads only the first `&&` segment, ignores `cd` and `git -C`, matches
`git init` anywhere in the text (`echo git init x`), and allows on a parse error. The theme rule then sees the wrong path.
That gives false denials (`git init -b main D:/repo/Lib/x`) and false allows (`git clone --branch dev <url>` from
`D:/repo`, `git -C D:/repo init x`).

## Observed vs expected

- **Observed:**
  - On 2026-10-31, `git init -b main D:/repo/Lib/spindle` was denied as a repo at `D:/repo/main`.
  - On 2026-11-02, the adversary probes found 4 false allows from `D:/repo`, and two false denials of its own read-only probes.
- **Expected (the rule):**
  - **Removed first:** heredoc bodies.
  - **Segments:** the rest splits on `;`, `&&`, `||`, `|`, `&` and newlines outside quotes. Each segment is tokenised by the rules of the calling tool's shell (`tool_name`): Bash uses POSIX rules (a backslash escapes outside single quotes, so an unquoted `D:\repo\bad` reaches git as the drive-relative `D:repobad`); PowerShell keeps a backslash literal and uses the backtick as its escape. A wrapper's inner command uses the wrapper's shell rules.
  - **Drive-relative tokens:** a target like `D:x` resolves against the cwd when the cwd is on the same drive; on another drive it cannot be inside `D:/repo` and is not judged.
  - **Command position:** a segment is an init or clone only when its command word is `git`, `git.exe` or a path ending in `/git` or `/git.exe`. That word may follow `VAR=x` assignments, `command`, `&` or `(`. Global options follow it, then the subcommand `init` or `clone`.
  - **Wrapper shells:** the quoted argument of `bash -c`, `sh -c`, `pwsh -c`/`-Command`, `powershell -Command` and `cmd /c` is parsed the same way, one level deep.
  - **Value options:** global and subcommand value options skip their value, whether attached (`-bmain`, `--branch=dev`) or separate, and `--` ends the options. A `--` token that is not an exact option counts as the one value option it is a prefix of (`--bra dev`); a prefix of two or more value options (`--b` for clone) makes the segment unparseable (git refuses it too); anything else is a flag.
  - **Working directory:** `cd`, `pushd`, `Set-Location` and `sl` with a literal path change it for the later segments; `git -C` values apply left to right, each relative one against the previous result.
  - **Interface:** `init_targets(cmd, cwd, shell) -> list[Path]`, one path per init or clone, raising `Unresolvable(reason)`; the guard denies when any target is bad or the command is unresolvable. `cd ..` resolves; a target relative to an unresolved directory (`cd $X`, `cd -`, `cd ~`) is denied as unresolvable.
  - **Denied:** a target equal to the fleet root `D:/repo` (this path only), a target `bad_repo_target` rejects, and an unparseable segment (an unbalanced quote) that contains `git` with `init` or `clone`.
  - **Unchanged:** the rest of the theme rule.

## Acceptance criteria

| AC | Traces | Given / when | Pass when | Fail when | Test |
|---|---|---|---|---|---|
| AC-1 | - | cwd `D:/repo`: `git init -b main D:/repo/Lib/x`, `git init --initial-branch main D:/repo/Lib/x`, `git init -qb main D:/repo/Lib/x`, `git init -bmain D:/repo/Lib/x`, `git init --template D:/t D:/repo/Lib/x`, `git init --shared D:/repo/Lib/x`, `git init -- D:/repo/Lib/x` | `init_targets` returns `[D:/repo/Lib/x]` for each and the guard allows it | any target is an option value | tests/test_guard.py |
| AC-2 | - | cwd `D:/repo`: `git clone --branch dev https://h/r.git`, `git clone --bra dev https://h/r.git`, `git clone -c a=b https://h/r.git`, `git clone https://h/r.git --depth 1` | each target is `D:/repo/r` and the guard denies it | any is allowed or targets a value | tests/test_guard.py |
| AC-3 | - | cwd `D:/repo/Lib`: `git -C D:/repo init junk`, `git -c k=v --git-dir D:/g init D:/repo/junk`, `cd D:/repo && git init junk`, `cd D:/repo; git init junk`, the same with a newline separator, `git -C .. init junk`; and `git -C D:/repo -C Lib init x` | the first six target `D:/repo/junk` and are denied; the last targets `D:/repo/Lib/x` and is allowed | any is allowed or mis-targeted | tests/test_guard.py |
| AC-4 | - | cwd `D:/repo`: `cd D:/repo/Lib && git init x`; `git init D:/repo/Lib/x && git init D:/repo/bad`; `cd $X && git init y` | the first targets `D:/repo/Lib/x` and is allowed; the second is denied for its second segment; the third is denied as unresolvable | otherwise | tests/test_guard.py |
| AC-5 | - | cwd `D:/repo`: `git init -b main` and `git init`; and `bad_repo_target("D:/repo")` | both inits target `D:/repo` and are denied; `bad_repo_target("D:/repo")` stays False (its pinned contract) | an init at the root is allowed, or the pinned test changes | tests/test_guard.py |
| AC-6 | - | cwd `D:/repo/Lib`: `git commit -m "git init D:/repo/x"`, a heredoc whose body is `git init D:/repo/x`, `echo git init D:/repo/x`; and `git init "D:/repo/bad"`, `git init "D:/repo/Lib/my proj"`, `bash -c "git init D:/repo/bad"`, `pwsh -Command "git init D:/repo/bad"` | the first three are not inits; the quoted and wrapped ones target their quoted path (`D:/repo/bad` denied, `D:/repo/Lib/my proj` allowed) | prose is judged as an init, or a quoted or wrapped target is missed | tests/test_guard.py |
| AC-7 | - | `git init "D:/repo/bad` (unbalanced quote); `git clone --b dev https://h/r.git` (ambiguous prefix); and `echo "it's fine` (unbalanced, no git) | the first two are denied as unparseable; the last is not judged by this rule | either of the first two is allowed, or the last is denied | tests/test_guard.py |
| AC-8 | - | Bash, cwd `D:/repo`: `git init D:\repo\bad`; Bash, cwd `D:/repo/Lib`: the same; PowerShell, cwd `D:/repo/Lib`: the same; Bash: `git init "D:\repo\bad"`; PowerShell: `git init "D:\repo\Lib\x y"` | targets are `[D:/repo/repobad]` denied, `[D:/repo/Lib/repobad]` allowed, `[D:/repo/bad]` denied, `[D:/repo/bad]` denied, `[D:/repo/Lib/x y]` allowed | any target differs from where git would create the repo | tests/test_guard.py |

## Known limits

Not parsed, by decision D33 (the parser's scope is closed; a filesystem backstop that detects a new `.git` outside the
theme folders is on the backlog): interpreters that run git themselves (python or node subprocesses), script files,
shell variables in a target, `//?/` paths, wrappers nested more than one level, `--separate-git-dir` locations,
`git worktree add`, and folder copies. A new parser case found after this item's last review joins this list unless
it is a false denial of a command already in the AC set.

## Gate plan

| Risk | Kind (deterministic / qualitative) | Check | Blocking / advisory |
|---|---|---|---|
| a value or prose is read as a path, a real target is missed, or the theme rule is weakened | deterministic | python -m pytest tests/test_guard.py -q | blocking |
