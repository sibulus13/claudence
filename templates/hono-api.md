# Hono API — Project Instructions

## Runtime Compatibility

- Hono runs on Node.js (via `@hono/node-server`), Cloudflare Workers, Bun, and Deno
- **Do not** use Node.js built-ins (`perf_hooks`, `node:crypto`, `node:fs`) in route handlers that need to be Cloudflare Workers compatible — use Web Standard APIs (`globalThis.performance`, `globalThis.crypto`, `Response`, `Request`)
- Entry point split: `src/index.ts` for Node (`serve(app)`), `src/index.workers.ts` for Workers (`export default app`)

## Middleware Order

- App-level middleware applies to all routes: `app.use('*', middleware)`
- Exempt paths from middleware explicitly: check `c.req.path` or register before the middleware with `app.get('/health', handler)`
- Standard order: `secureHeaders()` → `cors()` → `appSignatureMiddleware` → `authMiddleware` → routes

## Auth Pattern

- Layer 1: HMAC app signature (`X-App-Sig` + `X-App-Time`) — verified via `timingSafeEqual`, 5-minute replay window
- Layer 2: Supabase JWT — verified locally with `jose.jwtVerify()` first, then 5-minute user cache before calling `supabase.auth.getUser()` (avoids network call per request)
- Skip app signature in dev: check `SKIP_APP_SIG=true` or `NODE_ENV=development` without the secret set
- JWT secret: `SUPABASE_JWT_SECRET` env var, loaded once and cached as `KeyLike`

## Webhooks (Plaid, Stripe)

- Exempt from app signature middleware — they have their own verification
- Stripe: `stripe.webhooks.constructEvent(rawBody, sig, STRIPE_WEBHOOK_SECRET)` — requires raw body, not parsed JSON
- Plaid: verify the `Plaid-Verification` header

## Deployment Notes

- Fly.io: `auto_stop_machines = false` and `min_machines_running = 1` — Plaid webhooks require always-on
- Cloudflare Workers: in-memory rate limiter doesn't persist across instances — use KV for rate limiting
- Stripe API version: update `apiVersion` string in `new Stripe(...)` whenever the `stripe` npm package is upgraded — it's a narrow literal type
