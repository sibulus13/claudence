---
paths:
  - "**/next.config.*"
  - "**/vercel.json"
  - "**/vercel.ts"
  - "**/app/**/*.tsx"
  - "**/middleware.ts"
  - "**/proxy.ts"
---
# Next.js and Vercel ground rules
- Before handing over a URL: load the exact serving mode in a browser and require HTTP 200, the app shell present and zero console/page errors. Hand over the localhost URL. Never build into a live dev server's `.next`.
- Run the production build locally before pushing to a Vercel-connected branch.
- Provision services through the Vercel Marketplace (`vercel integration add`; Neon for Postgres). Least privilege: scoped DB roles, no secrets in `NEXT_PUBLIC_*`, provider quota caps, per-environment variables.
- Never pipe a value into `vercel env add` from PowerShell (it corrupts it); use a file or `--value`. (Enforced: hooks/guard.py.)
- Each app declares `deploymentTier:` in its CLAUDE.md; pre-traffic ships after build+test, live needs the governance gate (`/dark-factory`).
