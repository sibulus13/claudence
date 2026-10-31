# branch-conventions: L1 architecture

```mermaid
flowchart TD
  subgraph Before
    B1[Foreman withLock in memory] --> B2[.git/foreman-worktrees]
    B3[Ad hoc branch names] --> B4[Manual cleanup]
  end
  subgraph After
    A1[Dispatcher] --> A2[claim-registry in Weaver Postgres]
    A2 --> A3[D:/wt worktrees]
    A3 --> A4[branch-lint hook and PR check]
    A4 --> A5[GitHub squash merge]
    A5 --> A6[worktree-reaper weekly]
    A7[github-settings and release-please] --> A5
  end
```

Before: Foreman holds an in-memory lock and keeps worktrees under each repo's `.git/foreman-worktrees`; branch names are free-form and cleanup is manual. After: a Postgres-backed claim registry gates every worktree under `D:/wt/<repo>/<id>`, a lint gates names at push and PR, and a reaper applies one delete predicate.

## Components
| Component | Role (one line) | Spec |
|---|---|---|
| branch-lint | validates `<type>/<id>-<slug>` at pre-push and on PRs | components.md `## branch-lint` |
| claim-registry | leased claims, worktree writer, advisory-lock critical section, push guard, visibility mirrors | components.md `## claim-registry` |
| worktree-reaper | safe-delete predicate and weekly reaper | components.md `## worktree-reaper` |
| github-settings | rulesets, squash-only, release-please, auto-delete audit | components.md `## github-settings` |

## Lifecycle
Lifecycle of a work claim.

```mermaid
stateDiagram-v2
  [*] --> claimed: claim acquired
  claimed --> working: worktree created, first heartbeat
  working --> working: heartbeat renews lease
  working --> pr_open: first push, draft PR opened
  pr_open --> working: more commits pushed
  pr_open --> merged: PR squash-merged
  merged --> reaped: predicate holds, worktree and branch deleted
  merged --> merged: predicate fails, keep with reason
  working --> expired: process dead or heartbeat missed
  pr_open --> expired: process dead or heartbeat missed
  expired --> reclaimed: another holder takes the lease
  reclaimed --> working: new holder resumes in the same worktree
  reaped --> [*]
```

## Call chains
### Dispatch to reap
```mermaid
sequenceDiagram
  participant D as Dispatcher
  participant R as claim-registry
  participant G as git and worktree
  participant H as GitHub
  participant P as worktree-reaper
  D->>R: claim (repo, item, package)
  R-->>D: lease granted, slug frozen
  D->>G: add worktree D:/wt/repo/id, pnpm install
  D->>G: push with force-with-lease empty expect
  G->>H: push branch, branch-lint pre-push passes
  D->>H: open draft PR, label agent:claimed
  H-->>D: squash merge, PR MERGED
  P->>H: gh pr view state, headRefOid
  P->>G: predicate true, remove links, worktree remove, prune, branch -D
  P->>R: release claim
```

## Work breakdown
```mermaid
flowchart TD
  P1[PKG-1 branch-lint] --> P3[PKG-3 worktree-reaper]
  P2[PKG-2 claim-registry<br/>provides work-claim@1] -->|work-claim@1| P3
  P4[PKG-4 github-settings]
```

| Package | Component | Owns | Provides | Consumes | Depends on | Milestone | ACs | Test seam |
|---|---|---|---|---|---|---|---|---|
| PKG-1 | branch-lint | scripts/branch_lint/**, tests/branch_lint/**, cchk.toml | - | - | - | M1 | AC-1, AC-2 | none |
| PKG-2 | claim-registry | scripts/claims/**, tests/claims/**, contracts/work-claim.v1.json, contracts/fixtures/work-claim.v1/** | work-claim@1 | - | - | M1 | AC-3, AC-4, AC-5, AC-6, AC-7 | none |
| PKG-3 | worktree-reaper | scripts/worktree_reaper/**, tests/worktree_reaper/**, tests/architecture/** | - | work-claim@1 | PKG-2 | M2 | AC-8, AC-9, AC-10, AC-11, AC-15 | fixtures:work-claim@1 + stub:contracts/fixtures/work-claim.v1/stub.py |
| PKG-4 | github-settings | scripts/gh_settings/**, tests/gh_settings/**, templates/release-please/** | - | - | - | M1 | AC-12, AC-13, AC-14 | none |
| SHARED | - | pyproject.toml, .importlinter, .pre-commit-config.yaml | - | - | - | M1 | - | none |

Owns use the Foreman glob dialect and are pairwise disjoint. PKG-1 and PKG-4 do not depend on PKG-2 and may run in parallel with it.
