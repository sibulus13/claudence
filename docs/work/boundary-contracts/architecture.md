# boundary-contracts: L1 architecture

```mermaid
flowchart TD
  subgraph Before
    B1["Foreman enums"] -.hand copy.-> B2["Cortex enums"]
    B2 -.hand copy.-> B3["TeleFi envelope enum"]
    B4["Weaver status table: prose"]
  end
  subgraph After
    A1["enums.v1 schema"] --> A2["contract toolkit"]
    A2 --> A3["generated pydantic, TS, Ajv, SQL"]
    A2 --> A4["mermaid in spec L1"]
    A2 --> A5["CI gates"]
  end
```

Before: n/a for tooling; each repo holds its own copies of the enums. After: one enums file and per-boundary folders feed a toolkit that generates every binding and every diagram, and CI regenerates and fails on any diff.

## Components
| Component | Role (one line) | Spec |
|---|---|---|
| enums-schema | the single shared enums file, seeded with the fleet's enums | components.md `## enums-schema` |
| contract-toolkit | meta-schema, machine checks, codegen, lint, compat gate, mermaid, sequence checkers | components.md `## contract-toolkit` |
| stage-result adopter | Weaver StageResult contract and run-status machine | nested: docs/work/boundary-contracts-weaver/ |

Per-boundary folder shape (`contracts/<boundary>/`): `<msg>.v<N>.schema.json`, a reference to the common enums, `<boundary>.machine.v<N>.json`, `fixtures/{valid,invalid}/`, `sequences/{valid,invalid}/*.jsonl`, and a one-line COMPAT note: additive within vN; a breaking change is a new vN+1 file plus a dual-read window.

## Call chains
### Author adds a boundary, CI proves sync
```mermaid
sequenceDiagram
  participant A as Author
  participant T as contract-toolkit
  participant E as enums-schema
  participant G as Generated code
  participant CI as CI
  A->>T: add machine and schema files
  T->>E: resolve states and events
  E-->>T: enum values
  T->>G: regenerate pydantic, TS, SQL, mermaid
  CI->>T: regen check, lint, compat, sequences
  T-->>CI: exit 0 or a rule id
```

### Receiver validates a message at runtime
```mermaid
sequenceDiagram
  participant P as Producer
  participant R as Receiver
  participant V as Generated validator
  participant D as Database
  P->>R: message
  R->>V: validate schema and state
  V-->>R: ok or named error
  R->>D: write next state through the transition check
```

## Work breakdown
```mermaid
flowchart TD
  P1["PKG-1 enums-schema provides enums v1"] -->|enums v1| P2["PKG-2 contract-toolkit provides machine-meta v1"]
```

| Package | Component | Owns | Provides | Consumes | Depends on | Milestone | ACs | Test seam |
|---|---|---|---|---|---|---|---|---|
| PKG-1 | enums-schema | contracts/common/** | enums@1 | - | - | M1 | AC-1, AC-2 | none |
| PKG-2 | contract-toolkit | contracts/machine-meta/**, contracts/generated/**, scripts/contracts/**, tests/contracts/**, .spectral/** | machine-meta@1 | enums@1 | PKG-1 | M2 | AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13, AC-14, AC-15 | fixtures:enums@1 |
| SHARED | - | package.json, pnpm-lock.yaml, pyproject.toml, .github/workflows/contracts.yml | - | - | - | M1 | - | none |

Package numbering follows the owner's list (toolkit first in prose); PKG-1 is the enums file because the toolkit consumes it, so it takes the earlier milestone. The Weaver adopter is a nested item, not a package.

Owns use the Foreman glob dialect and are pairwise disjoint. Milestone exit: listed ACs green, contract tests for every contract provided or consumed, and the isolation run passing per package.
