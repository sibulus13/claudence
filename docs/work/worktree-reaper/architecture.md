# worktree-reaper: L1 architecture

```mermaid
flowchart TD
  subgraph Before
    B1["Manual worktree and branch cleanup"]
  end
  subgraph After
    A1["Weekly schedule"] --> A2["Reaper"]
    A2 --> A3["Merged-proof predicate"]
    A3 --> A4["Ordered removal under repo lock"]
    A4 --> A5["Claim release"]
  end
```

Before: cleanup is manual and the Foreman path deletes with its own checks. After: one predicate decides, one ordered removal executes it under the per-repo lock, and the claim is released through the ClaimStore port.

## Components
| Component | Role (one line) | Spec |
|---|---|---|
| worktree-reaper | merged-proof predicate, ordered removal, claim release, weekly schedule | components.md `## worktree-reaper` |

## Call chains
### Reap one worktree
```mermaid
sequenceDiagram
  participant R as worktree-reaper
  participant S as ClaimStore
  participant G as git
  participant H as GitHub
  participant W as worktree files
  R->>S: live_claims for repo
  R->>H: defaultBranchRef and PRs for the branch
  R->>G: fetch default branch, status, rev-list, merge-base
  R->>S: repo_lock
  R->>W: delete links and junctions, then worktree remove
  R->>G: prune and branch delete
  R->>S: release claim
```
