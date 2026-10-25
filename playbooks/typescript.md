# TypeScript (Next.js / React) ground rules

Everything in javascript.md applies. Additionally:

- `"strict": true`; no implicit `any`; explicit return types on exported functions.
- Imports at the top, type-only imports as `import type`; path aliases from `tsconfig`, not deep
  relative chains.
- Runtime data is validated with zod at every boundary (API route in/out, external response);
  derive types with `z.infer` so the schema and type cannot drift. `as SomeType` on external data
  is a defect.
- Server vs client components are explicit (`"use client"` only where state or effects need it);
  secrets never reach client bundles.
- Reuse the repo's existing components and tokens before adding one; state the reuse search.
- Gate: `tsc --noEmit` plus the repo's runtime validation (e.g. `validate_dashboard.py`).
