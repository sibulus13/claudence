# spec-gate: L1 architecture

```mermaid
flowchart TD
  subgraph Before
    B1[PreToolUse guard parses the command] --> B2[spec_check on docs/specs]
  end
  subgraph After
    A1[git commit] --> A2[commit-msg hook spec_gate.py]
    A2 --> A3[spec_check on docs/work]
    A4[fleet installer] --> A1
  end
```

Before: the agent's PreToolUse hook predicted a commit from its command text. After: the commit-msg hook observes the commit itself and reads the work item the trailer names.

## Components
| Component | Role (one line) | Spec |
|---|---|---|
| spec_check | validates a work item by tier and rule id | nested: docs/work/spec-gate-checker/ |
| spec-gate hook | rejects a source commit on the default branch without a building or shipped item | components.md |
| fleet installer | puts the pre-commit config into each fleet repo | components.md |

## Call chains
### Source commit on the default branch
```mermaid
sequenceDiagram
  participant D as Committer
  participant G as git
  participant H as spec_gate
  participant K as spec_check
  D->>G: git commit
  G->>H: commit-msg file
  H->>K: README with source-commit flag
  K-->>H: findings
  H-->>G: exit 0 or 1
```
