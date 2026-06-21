---
name: orchestrate
description: Agent orchestration for autonomous background execution with parallelization and verification
version: 1.0.0
---

# orchestrate

Use this skill when the user wants autonomous background execution with parallelization, verification, and testing.

## When to Use

- User requests automatic parallel task execution
- Background subagent launch with verification
- Multi-step implementation with automatic validation
- Code changes that need automated testing/linting

## Workflow

### 1. Analyze & Partition

Identify which steps are:

- **Independent**: Can run in parallel (no shared dependencies)
- **Sequential**: Must run in order (output of N → input of N+1)
- **Shared resource**: Multiple steps write to same file(s)

### 2. Execute

For independent tasks:

```
Launch with `Task` tool, subagent_type="general", run_in_background=true
```

For sequential tasks:

```
Run sequentially, passing output as input to next step
```

### 3. Verify

After execution completes:

- Run tests: `pnpm test`
- Run typecheck: `pnpm type-check`
- Run build: `pnpm build`
- Verify actual output matches expected output

### 4. Report

Return structured summary:

- What was done
- What passed/failed
- Next steps needed

## Example Invocation

```
/orchestrate implement feature: user authentication with OAuth
```

This would:

1. Analyze the codebase for OAuth patterns
2. Find existing auth hooks (if any)
3. Implement the feature in background
4. Run tests automatically
5. Report results

## Configuration

Set these in your AGENTS.md or prompt:

| Config          | Description                  | Default |
| --------------- | ---------------------------- | ------- |
| maxAgents       | Max parallel subagents       | 3-5     |
| verifyTests     | Auto-run tests after changes | true    |
| verifyTypecheck | Auto-run type-check          | true    |
| failFast        | Stop on first failure        | false   |

## Best Practices

1. **Partition first** — Don't just run tasks; identify dependencies
2. **Verify always** — Tests should pass before reporting success
3. **Report failures clearly** — Include error output, not just "failed"
4. **No worktree isolation** in this repo — All agents write to live working dir
