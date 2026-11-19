---
id: fix-sweep-long-command-line
type: bugfix
status: draft
touches: [harness]
layers:
  architecture: none
  component: none
  functional: none
  data: none
created: "2026-11-18"
owner: harness
lifecycle: false
---
# The weekly context sweep crashed when it moved more paths than fit one Windows command line

## References

### Local

| Source (file:line) | Status (working / partial / broken) | What it shows | Decision (extract / wrap / replace / ignore) + reason |
|---|---|---|---|
| C:/Users/Michael/.claude/scripts/projects_sweep.py:206 | broken | `commit_moves` passed every moved path as git arguments (`ls-files`, `check-ignore`, `add`, `commit`) | replace: paths go to git on stdin |
| C:/Users/Michael/.claude/logs/context-sweep/2026-11-15.log:1 | broken | the 2026-11-15 run moved ~300 paths, then `git ls-files` raised `WinError 206` and nothing was committed | extract: the regression case |
| C:/Users/Michael/.claude/tests/test_context_lifecycle.py:1 | working | real-git tests of `commit_moves` | extract: the regression test goes here |

### Web

| Source (URL) | Date checked | What it shows | Decision |
|---|---|---|---|
| https://git-scm.com/docs/git-add | 2026-11-18 | `--pathspec-from-file=-` with `--pathspec-file-nul` reads pathspecs from stdin (also on `git commit`); `check-ignore --stdin -z` does the same | extract: use both |

## Root cause

Windows caps a process command line at 32767 characters. The sweep built one git command holding every moved path, so a
large run (the first archive of a ~300-file backup folder) could not start git at all.

## Observed vs expected

- **Observed:** on 2026-11-15 the scheduled sweep moved the files, then exited 1 with `WinError 206` before committing; the moves sat uncommitted in the fleet docs repo.
- **Expected:** any number of moves is committed in one commit; the command line length does not grow with the number of paths.

## Acceptance criteria

| AC | Traces | Given / when | Pass when | Fail when | Test |
|---|---|---|---|---|---|
| AC-1 | - | 400 tracked files with long names are archived (their paths together exceed 32767 characters) and `commit_moves` runs | it returns no failures and the repo is clean | it raises or leaves changes uncommitted | tests/test_context_lifecycle.py |

## Gate plan

| Risk | Kind (deterministic / qualitative) | Check | Blocking / advisory |
|---|---|---|---|
| a large sweep cannot commit, or an ignored path gets staged | deterministic | python -m pytest tests/test_context_lifecycle.py tests/test_projects_sweep.py -q | blocking |
