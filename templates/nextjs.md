# Next.js — Project Instructions

## App Router Conventions

- Route handlers live in `src/app/api/**/route.ts` — export named functions `GET`, `POST`, `PATCH`, `DELETE`
- Middleware (`src/middleware.ts`) runs on the Edge runtime — no Node.js built-ins; use `crypto.subtle` for HMAC
- `NextResponse.json()` for JSON responses; `NextResponse.next()` to pass through
- Dynamic params: `{ params }: { params: { id: string } }` — always typed, never `any`

## Environment Variables

- `NEXT_PUBLIC_*` variables are embedded in the client bundle — never put secrets there
- Server-only vars (no prefix) are safe for API routes and server components
- Validate required env vars at startup — crash fast rather than silently returning empty strings

## Deployment (Vercel)

- Edge middleware has a 1MB bundle limit — avoid heavy dependencies
- `export const runtime = 'edge'` on route handlers that need Edge; default is Node.js runtime
- Webhook routes (Plaid, Stripe) must be excluded from HMAC middleware — they POST from external services
- `export const dynamic = 'force-dynamic'` on routes that must not be cached

## Cashcow-Specific

- This is the reference implementation that Tarive was extracted from
- 17 API routes mirrored in `packages/api` (Hono) — keep in sync when adding features
- The `/api/user/settings` route was added to cashcow specifically for Tarive mobile compatibility
- Middleware at `src/middleware.ts` enforces the same HMAC app signature as the Hono API
