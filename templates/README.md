# Claude Code Template Library

Reusable instruction snippets. When creating a new project's CLAUDE.md, copy relevant sections from these files rather than using `@` imports (avoid due to Windows bug #8868 and global CLAUDE.md import bug #1041).

## Available Templates

| File | Use for |
|---|---|
| `typescript.md` | Any TypeScript project — strict mode rules, type discipline |
| `pnpm-monorepo.md` | pnpm workspace + Turborepo projects |
| `expo-react-native.md` | Expo / React Native apps — SDK compat, Expo Go caveats, Metro |
| `hono-api.md` | Hono backend APIs — middleware, auth, webhook patterns |
| `nextjs.md` | Next.js App Router projects |

## How to Bootstrap a New Project

1. Create `[project]/CLAUDE.md`
2. Copy relevant template sections into it
3. Add project-specific structure, stack, and conventions below
4. Create `[project]/.claude/settings.json` with scoped permissions
5. Add `.claude/settings.local.json` to `.gitignore`

## Settings Cascade (reminder)

```
~/.claude/settings.json          ← global (hooks, broad permissions)
  └── [project]/.claude/settings.json    ← project (narrow permissions, project hooks) — committed
        └── [project]/.claude/settings.local.json  ← local overrides — gitignored
```

Arrays (allow, deny, hooks) **concatenate** across levels — they do not override each other.
Scalars (model, defaultMode) override from highest-precedence level.

## Adding a New Template

Create `~/.claude/templates/[technology].md` following the pattern:
- H1 title
- One-line description of scope
- Sections covering: conventions, common pitfalls, project-specific notes
