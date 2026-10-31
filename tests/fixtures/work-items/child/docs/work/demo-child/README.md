---
id: demo-child
type: feature
status: building
touches: [core]
layers:
  architecture: none
  component: added
  functional: added
  data: none
created: "2026-10-31"
owner: harness
parent: demo
nestTrigger: [contract]
nestWhy: other code calls its plug-in contract
---
# Demo child

```mermaid
flowchart TD
  P[demo] --> C[child]
```

## Purpose
A nested part.

## Non-goals
- The parent's work.

## Capabilities
| CAP | Statement |
|---|---|
| CAP-1 | The service must expose the plug-in contract |

## Non-functional requirements
None.

## Gate plan
| Risk | Kind (deterministic / qualitative) | Check | Blocking / advisory |
|---|---|---|---|
| contract drift | deterministic | pytest | blocking |
