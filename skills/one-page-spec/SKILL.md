---
name: one-page-spec
description: The spec for a feature, and how to build from it. One page, three diagrams, then a walking skeleton through every arrow before building out. Pilot of the lean flow; use when the brief names it. Config, wording and docs need no spec; a bug needs a symptom, a way to reproduce it, and a test.
---

# One-page spec

Size it by the cost of being wrong. 400 words plus diagrams.

## The page

1. **Why**: the owner's words, two lines.
2. **Have and reuse**: what already exists, from the research page.
3. **User path**: a flowchart of the normal journey.
4. **States**: a state diagram of what a user can reach, including bad days: outage, restart, retry, bad input from a real source.
5. **Architecture**: boxes and arrows. Label every arrow with what crosses it.
6. **Done means**: up to 5 behaviours, each with the command or steps that show it.
7. **Assumptions**: only what could be wrong and would change the build.

Leave out background, milestones, measurement and rejected options unless a decision depends on them. Draw before writing: if a diagram cannot show it, ask whether it matters.

## Build it

1. **Walking skeleton first.** Build the thinnest version that carries one real case through every arrow, using the real entry point and the real next system. Run it and keep what happened.
2. **Build out**, test first, one state at a time. Each test goes through the path production uses.
3. **Change the producer last.** When an arrow's contract changes, update and restart the consumer first.
4. Hand off with the run record, not a claim.

## When a diagram was wrong

Fix the diagram in the same commit. A state found during the build is a missing state: add it, then the test.
