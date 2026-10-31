# branch-conventions: L1 architecture

```mermaid
flowchart TD
  subgraph Before
    B1["Foreman withLock in memory"] --> B2[".git/foreman-worktrees"]
    B3["Ad hoc branch names"] --> B4["Manual cleanup"]
  end
  subgraph After
    A1["Dispatcher"] --> A2["claim registry: claims schema in Postgres"]
    A2 --> A3["D:/wt worktrees"]
    A3 --> A4["branch lint: pre-push and PR check"]
    A4 --> A5["GitHub squash merge"]
    A5 --> A6["worktree-reaper: nested item"]
    A7["GitHub settings and release-please"] --> A5
  end
```

Before: Foreman holds an in-memory lock and keeps worktrees under each repo's `.git/foreman-worktrees`; branch names are free-form and cleanup is manual. After: a Postgres-backed claim registry gates every worktree under `D:/wt/<repo>/<id>`, a lint gates names at push and on PRs, settings are applied as code, and the nested reaper item applies one delete predicate.

## Components
| Component | Role (one line) | Spec |
|---|---|---|
| branch-lint | validates `<type>/<id>-<slug>` at pre-push and on PRs | components.md `## branch-lint` |
| claim-registry | claims, liveness, takeover, critical section, push guard, mirrors, ClaimStore port | components.md `## claim-registry` |
| github-settings | rulesets, squash-only, PR-title check, release-please | components.md `## github-settings` |
| boundary-gate | import-boundary and isolation gate commands | components.md `## boundary-gate` |
| worktree-reaper | safe-delete predicate and weekly reaper | nested: docs/work/worktree-reaper/ |

## Lifecycle
Lifecycle of a work claim. Stored states are active, expired and released; the phases inside active are derived from git and GitHub at read time and are never stored.

```mermaid
stateDiagram-v2
  [*] --> active: claim acquired
  state active {
    [*] --> working
    working --> pr_open: first push and draft PR
    pr_open --> working: more commits
    pr_open --> merged: PR squash merged
  }
  active --> needs_human: no progress past bound while process alive
  needs_human --> active: owner acts
  active --> expired: holder process absent
  expired --> reclaimed: atomic compare and set
  reclaimed --> active: new holder resumes
  active --> released: holder releases on merge or reaper releases after proof
  released --> [*]
```

## Call chains
### Dispatch to reap
```mermaid
sequenceDiagram
  participant D as Dispatcher
  participant R as claim-registry
  participant G as git
  participant H as GitHub
  participant P as worktree-reaper
  D->>R: claim package-level id
  R-->>D: claim granted, slug frozen
  D->>G: add worktree under D:/wt, install in JS repos
  D->>G: first push with force-with-lease empty expect
  G->>H: push branch, lint passes
  D->>H: draft PR, label agent:claimed
  H-->>D: PR squash merged
  P->>H: PR state, base, head and merge commit
  P->>G: predicate true, remove links, worktree, prune, branch delete
  P->>R: release claim under repo lock
```

## Work breakdown
```mermaid
flowchart TD
  P1["PKG-1 branch-lint"] --> P4["PKG-4 boundary-gate"]
  P2["PKG-2 claim-registry: provides work-claim v1 and claim-store v1"] --> P4
  P3["PKG-3 github-settings"] --> P4
```

| Package | Component | Owns | Provides | Consumes | Depends on | Milestone | ACs | Test seam |
|---|---|---|---|---|---|---|---|---|
| PKG-1 | branch-lint | scripts/branch_lint/**, tests/branch_lint/**, cchk.toml, .pre-commit-config.yaml, templates/branch-lint/** | - | - | - | M1 | AC-1 | none |
| PKG-2 | claim-registry | scripts/claims/**, tests/claims/**, contracts/** | work-claim@1, claim-store@1 | - | - | M1 | AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10 | none |
| PKG-3 | github-settings | scripts/gh_settings/**, tests/gh_settings/**, templates/release-please/**, templates/pr-title/** | - | - | - | M1 | AC-11, AC-12, AC-13, AC-14 | none |
| PKG-4 | boundary-gate | scripts/gates/**, tests/gates/**, .importlinter | - | - | PKG-1, PKG-2, PKG-3 | M2 | AC-15 | none |
| SHARED | - | pyproject.toml | - | - | - | M1 | - | none |

Owns use the Foreman glob dialect and are pairwise disjoint. The two contracts are consumed by the nested worktree-reaper item through `ext:branch-conventions:work-claim@1` and `ext:branch-conventions:claim-store@1`; stubs for them live inside the provider's owns. Hook wiring (`.pre-commit-config.yaml`) is owned by PKG-1.
