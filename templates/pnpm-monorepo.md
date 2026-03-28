# pnpm Monorepo — Project Instructions

## Workspace Rules

- All dependency installs: `pnpm install` from the **monorepo root** — never `npm install` or `yarn`
- Adding a dep to a specific package: `pnpm add <pkg> --filter=<package-name>`
- Running scripts: `pnpm <script> --filter=<package>` from root, or `pnpm <script>` from within the package directory
- Never run `npx` for tools that are workspace devDependencies — use `pnpm exec` instead
- `workspace:*` protocol for internal packages — never a version number

## Turborepo

- Config key is `tasks` (not `pipeline`) since Turbo 2.0
- `turbo run dev --filter=@scope/package` for single-package dev mode
- Do NOT use `pnpm app:dev` / `pnpm api:dev` Turbo scripts when you need interactive output (QR codes, REPL) — run the underlying command directly
- Turbo caches `build` outputs in `.turbo/` — run `pnpm build --force` to bust cache

## package.json

- Peer dependency versions must match what the SDK/framework ships — always check the SDK's compatibility matrix before pinning
- `@types/react-native` must never be added for RN ≥ 0.71
- `pnpm.overrides` in root `package.json` can force transitive peer resolution but does not silence peer warnings from dependents

## Common Pitfalls

- `ERR_PNPM_NO_MATCHING_VERSION`: usually means a `@types/*` package was abandoned — check if the types are now bundled in the main package
- After `pnpm install` failures, the lockfile may be stale — re-run install after fixing `package.json`
- `workspace:*` references fail if you accidentally run `npm install` — clean `node_modules` and re-run `pnpm install`
