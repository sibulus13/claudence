# demo-child: L2 components

```mermaid
flowchart TD
  subgraph Before
    B1[old]
  end
  subgraph After
    A1[plug] --> A2[plug]
  end
```

## plug

### Interface
f(x)

### Functional requirements
| FR | Requirement |
|---|---|
| FR-1 | does 1 |

### Data
none

### Failure modes
| Failure | Detection | Handling |
|---|---|---|
| bad input | validation | reject |

### Budget
| Dimension | Budget |
|---|---|
| Latency | 10 ms p95 |
