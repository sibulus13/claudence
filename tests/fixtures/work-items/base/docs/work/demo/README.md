---
id: demo
type: feature
status: building
touches: [core]
layers:
  architecture: added
  component: added
  functional: added
  data: none
evidence: { demo: evidence/demo.webm }
created: "2026-10-31"
owner: harness
lifecycle: false
---
# Demo feature

```mermaid
flowchart TD
  U[User] --> S[Demo]
  S --> X[External system]
```

## References

### Local

| Source (file:line) | Status (working / partial / broken) | What it shows | Decision (extract / wrap / replace / ignore) + reason |
|---|---|---|---|
| docs/work/demo/README.md:1 | working | the parent item | extract: reuse it |

### Web

| Source (URL) | Date checked | What it shows | Decision |
|---|---|---|---|
| https://example.org/demo | 2026-10-31 | a convention | ignore: not relevant |

## Operating envelope

| Assumption | How it is observed (not hoped) | If violated |
|---|---|---|
| one user at a time | AC-1 | refuse: exit 1 with a named reason |

## Purpose
Show a valid work item for the checker fixtures.

## Non-goals
- Anything beyond the fixtures.

## Capabilities
| CAP | Statement |
|---|---|
| CAP-1 | The user can run the demo |
| CAP-2 | The service must answer requests |
| CAP-3 | The service must not lose a request |
| CAP-4 | The service must answer fast |
| CAP-5 | The service must keep its boundary |

## Non-functional requirements
| NFR | Target | Method | Evidence |
|---|---|---|---|
| NFR-1 | p95 latency <= 200 ms | latency-bench: time the answer | AC-3 |
| NFR-2 | no import from core into plugins | fitness: import rule | AC-4 + config:rules/rules.cfg |

## Trade-offs
| Option | Latency | Cost | Maintenance | Extensibility | Refactorability | Verdict |
|---|---|---|---|---|---|---|
| Inline | low | low | medium | low | low | chosen |
| Queue | medium | medium | high | high | high | rejected: too heavy |

## Patterns applied
| Pattern | Where | Why |
|---|---|---|
| adapter | comp-b | isolates the external system |

## Components chosen
| Need | Chosen (off the shelf) | Rejected | Why rejected |
|---|---|---|---|
| parsing | PyYAML | hand-rolled parser | cannot read nested keys |

## Gate plan
| Risk | Kind (deterministic / qualitative) | Check | Blocking / advisory |
|---|---|---|---|
| wrong answer | deterministic | pytest | blocking |
