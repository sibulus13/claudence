---
name: brief
description: Generate a role-specific context package for a downstream agent. Takes role + project + milestone. Strips irrelevant context and produces a minimum viable briefing that can be pasted directly into an agent prompt.
version: 1.0.0
---

# /brief

Generate a minimum viable context package for a specific role and task. The output is a self-contained briefing — paste it directly into an Agent prompt.

## Usage

```
/brief role=implementer project=Envoy milestone=M5
/brief role=reviewer project=Helm milestone=M8
/brief role=marketing project=Envoy deliverable=landing-page-copy
```

## Role → context package mapping

### implementer
Assemble:
1. Project name + tech stack (from context.md Overview)
2. Target milestone from context.md — the `## Next milestone — acceptance criteria` section verbatim
3. Files to create/modify (derive from AC if not explicit)
4. ≤3 existing code patterns to follow (find similar files/functions in the repo and quote the relevant signature or pattern)
5. What NOT to change (list files that are adjacent but out of scope)
6. tsc/test invocation command for validation

Strip: full conversation history, other projects, architectural debates, prior milestone details.

### reviewer
Assemble:
1. Git diff of changed files since milestone start (`git diff HEAD~N -- [files]`)
2. AC from context.md (to verify implementation satisfies it)
3. Known constraints or edge cases from context.md open decisions
4. Expected output format: "numbered findings with file:line and severity (critical/warn/info)"

Strip: implementation rationale, prior session context, unrelated projects.

### qa
Assemble:
1. AC list verbatim from context.md
2. Test invocation command
3. List of files changed (from git diff --name-only)
4. Any known regression surface from context.md

Strip: implementation details beyond test invocation.

### designer
Assemble:
1. User goal (1 sentence from context.md spec)
2. Constraints: tech stack + time estimate + existing patterns (quote 1-2 existing schema or UI patterns)
3. Definition of done: "output a schema/mockup that unambiguously specifies what an Implementer will build"

Strip: all implementation specifics.

### marketing
Assemble:
1. ICP description (from project context.md or memory)
2. Core value prop (1 sentence)
3. Competitors or alternatives users currently use
4. Deliverable type (tagline / landing page copy / email / tweet thread)

Strip: code, architecture, implementation.

### business
Assemble:
1. The specific question (pricing? market size? CAC/LTV?)
2. Known data points (from project context.md or memory)
3. The decision this analysis informs
4. Output format: "unit economics table + recommendation + key assumptions stated"

Strip: code, architecture.

## Output format

The brief produces a ready-to-paste agent prompt:

```
## Context

[Project name] — [one-line description from context.md]
Stack: [tech stack]

## Your task

[Role]-specific task description

## Acceptance criteria

[AC list]

## Constraints

[what not to change / hard limits]

## Validation

[how to verify your work is complete]

## Output contract

[what format your output must take]
```
