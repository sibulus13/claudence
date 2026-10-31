# <id>: L1 architecture

```mermaid
flowchart TD
  subgraph Before
    B1[<container>] --> B2[<container>]
  end
  subgraph After
    A1[<container>] --> A2[<container>]
    A2 --> A3[<new container or external system>]
  end
```

Before: <"n/a: new" when added.> After: <one sentence on the new edges.>

## Components
| Component | Role (one line) | Spec |
|---|---|---|
| <component-a> | <role> | components.md `## <component-a>` |
| <component-b> | <role> | nested: docs/work/<child-id>/ |

## Lifecycle
<!-- Keep this section only when README has `lifecycle: true`. When `lifecycle: false`, delete the whole section (heading and diagram): the checker requires it iff true. -->

```mermaid
stateDiagram-v2
  [*] --> <State1>
  <State1> --> <State2>: <event>
  <State2> --> [*]
```

## Call chains
### <Main call chain>
```mermaid
sequenceDiagram
  participant C as Caller
  participant A as <component-a>
  participant B as <component-b>
  C->>A: <call>
  A->>B: <call>
  B-->>A: <result>
  A-->>C: <result>
```
