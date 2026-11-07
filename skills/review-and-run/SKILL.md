---
name: review-and-run
description: The two-step review. Read the code against the states a user can reach, then run the real thing end to end. Pilot of the lean flow; use when the brief names it. Every finding says how someone gets there, and only reachable faults block.
---

# Review and run

## Step 1: read for reachable states

Take the spec's state diagram and arrows. For each state and arrow, find the code that handles it. Add any state the diagram misses that a user can reach.

Reachable means one of:

- **A**: ordinary use or a normal scheduled run hits it.
- **B**: a plausible bad day hits it: outage, restart, retry, bad input from a real source, or someone who can really reach that input, such as a person editing a public issue.

Not reachable:

- **C**: theoretical: needs a sequence nobody would plausibly do, or a very narrow window.
- **D**: paperwork: wording, format or citations with no change in behaviour.

## Step 2: run it

Run the real thing, not its tests. Pilot a UI end to end, or start the script or service in a test environment. Use the real entry point, send one real case through every arrow, and compare what happens with **Done means**. Keep the output.

If it cannot be run, say why and what that leaves unproven.

## Findings

Each finding states its class, the path to reach it, and what you saw.

- A and B block. C and D never block: list them once at the end for the backlog.
- A second round checks only the fixes. Stop after that unless an A fault remains.
- Don't hunt for every edge case, and don't re-review what passed.

End with `VERDICT: pass` or `VERDICT: fix-first`.
