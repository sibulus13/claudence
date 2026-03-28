# Claude Code Parallelization — Design Reference

## TLDR

Use **native Claude Code subagents** for all parallelism. No external frameworks needed for a single TypeScript developer. Dispatch independent tasks concurrently by default; only sequence tasks when output from one feeds the next or both touch the same file.

---

## The Three Parallel Primitives

### 1. Parallel tool calls (same message, main conversation)
The fastest form of parallelism — zero overhead.

```
# In a single Claude response: Glob + Grep + Read in parallel
# No subagent overhead, results available immediately
```

**Use for:** independent file reads, searches, and writes in the current task. Anything that doesn't need isolation.

---

### 2. Background subagents (`run_in_background: true`)
A fresh Claude instance, own context window, non-blocking. Parent continues working; result surfaces when done.

```
# Agent tool with run_in_background: true
# Claude Code asks for all permissions upfront, then runs concurrently
# /tasks shows active agents; results arrive via AgentOutputTool
```

**Use for:** test runs, builds, documentation research, codebase exploration, long read tasks.
**Limit:** 10 concurrent subagents max (excess queue).
**Constraint:** subagents cannot spawn sub-subagents.
**Cost:** each subagent pays full context init cost again (~same total tokens as sequential, but faster wall time).

---

### 3. `--worktree` isolation (parallel repo branches)
Each session or subagent gets its own git branch and working directory. Zero file conflicts.

```bash
claude --worktree feature-auth   # branch: worktree-feature-auth
claude --worktree bugfix-123     # branch: worktree-bugfix-123
```

Or per-subagent via `isolation: worktree` in agent frontmatter.
Add `.worktreeinclude` to project root to auto-copy `.env` into new worktrees.

**Use for:** parallel feature branches, parallel PR reviews, any subagent that writes files.
**Windows caveat:** add `.claude/worktrees/` to `.gitignore`. Re-run `pnpm install` in each worktree.

---

## Decision Table

| Scenario | Pattern |
|---|---|
| Multiple independent file reads/searches | Parallel tool calls, single message |
| Run tests + write docs simultaneously | Background subagents |
| Two features touching different packages | Subagents with `isolation: worktree` |
| Feature A's output needed by Feature B | Sequential (chain from main conversation) |
| Same file touched by two tasks | Sequential, or split file ownership first |
| `pnpm turbo build` while writing code | Background subagent |
| Research + implementation in parallel | Background research agent + main writes |
| < 5 minute task | Keep in main conversation (subagent overhead not worth it) |

---

## Alternatives Compared

| Approach | Parallel primitive | Windows | Setup | Best for |
|---|---|---|---|---|
| **Native subagents** | Agent tool + background | Good | Zero | Code tasks, builds, research |
| **Agent Teams** | Peer-to-peer messaging | No split-pane | Experimental flag | Complex multi-agent debate (defer) |
| **ruflo / claude-flow** | Queen/worker swarms | Untested | npm install | Distributed swarm intelligence (overkill) |
| **everything-claude-code** | Prebuilt agent files | Bash-first | git clone | Template library, not runtime |
| **LangGraph** | DAG-based conditional edges | Python runtime | Significant | Multi-model DAG workflows |
| **CrewAI** | Role-based crews | Python runtime | Significant | Business process automation |
| **AutoGen** | GroupChat / graph | Python runtime | Medium | Research / conversational multi-agent |

**Verdict:** LangGraph/CrewAI/AutoGen are the right tools when you need model-agnostic orchestration, checkpointing with time travel, or complex DAG workflows across non-Claude models. For a single developer doing TypeScript/pnpm work in Claude Code, they add Python runtime overhead and abstraction you don't need. Native subagents cover the 95% case with zero dependencies.

---

## Rate Limit Reality

**Per-session concurrency ceiling:**
- Max 5x plan: 3–5 background Sonnet subagents safely before per-minute TPM limits bite
- Pro plan: 1–2 concurrent subagents
- Opus: severely constrained per-minute throughput — use Sonnet/Haiku for workers

**Cost model:** parallel ≈ sequential in total tokens (each agent pays context init cost). You're buying wall-time speed, not token savings. If parallel coordination requires debugging, it can cost more than sequential.

---

## Setup for Tarive Monorepo

1. **Create `.claude/agents/` in `D:\repo\web\Tarive`** with per-package agent files:
   - `mobile-agent.md` — owns `apps/app/`
   - `api-agent.md` — owns `packages/api/`
   - `core-agent.md` — owns `packages/core/`
   - `ui-agent.md` — owns `packages/ui/`

2. **Agent file template:**
   ```markdown
   ---
   name: mobile-agent
   description: Use when working on the Expo mobile app in apps/app/. Run in background for builds and tests.
   model: sonnet
   isolation: worktree
   ---
   You own apps/app/ only. Never touch packages/ directly.
   ```

3. **Add to `D:\repo\web\Tarive\CLAUDE.md`** (routing rules):
   - Cross-package refactors touching shared types → sequential in main conversation
   - Independent package work → parallel subagents with worktree isolation
   - `pnpm turbo build` / `pnpm turbo test` → always background

4. **`.worktreeinclude`** at repo root:
   ```
   .env
   .env.local
   apps/app/.env
   ```

5. **Defer Agent Teams** until Windows split-pane support ships and the feature leaves experimental.
