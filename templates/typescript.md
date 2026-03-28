# TypeScript — Project Instructions

## Compiler Settings

- `strict: true` always. No exceptions
- `noUncheckedIndexedAccess: true` for any project reading from arrays or records by index
- `exactOptionalPropertyTypes: true` where the project already uses it
- `skipLibCheck: true` is acceptable; `noEmit` for type-check-only passes
- Target `ES2020` minimum; use `ESNext` for projects that run in modern runtimes only

## Type Discipline

- No `any` — use `unknown` and narrow, or model the type properly
- No `as SomeType` casts unless bridging untyped third-party APIs; document why
- No non-null assertions (`!`) on values that could genuinely be null at runtime
- Prefer `interface` for object shapes exposed in public APIs; `type` for unions, intersections, and aliases
- `StyleProp<ViewStyle>` not `ViewStyle` for React Native style props that accept arrays
- Never use `@ts-ignore` — fix the underlying type issue

## Imports

- No `@/` path aliases unless the tsconfig explicitly defines them
- Barrel exports (`index.ts`) are fine for packages; avoid them inside `src/` directories (causes circular dep risk)
- `import type` for type-only imports to avoid accidental runtime dependencies

## Process / Environment

- `typeof process !== 'undefined'` guard before accessing `process.env` in code that runs in both Node and browser/React Native
- Add `@types/node` to devDependencies in any package that references `process`, `Buffer`, `path`, etc.
- React Native ≥ 0.71 bundles its own types — never add `@types/react-native`
