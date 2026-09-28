# Sterish landing (`sterish.xyz`)

A separate deployment from the dashboard, on purpose.

| | Deployment | Root directory |
|---|---|---|
| **Landing** | `sterish.xyz` | `landing/` |
| Dashboard | `app.sterish.xyz` | `frontend/` |

Two audiences that want different things on arrival. Someone who reaches
`sterish.xyz` has usually never heard of Sterish and needs the argument;
someone who opens `app.sterish.xyz` already knows and wants the registry. Same
brand, same tokens, different first frame — which is why this app has no
product nav and no wallet button.

## Running it

```bash
pnpm install
pnpm dev          # http://localhost:3000
pnpm test         # data layer + the token drift guard
pnpm typecheck
pnpm build
```

No env is required: `NEXT_PUBLIC_API_URL` defaults to `https://api.sterish.xyz`.
Point it at `http://localhost:8000` to develop against a local API.

## The numbers are read, never typed

`src/modules/landing/liveStats.ts` derives every figure on the page from
`GET /skills` at render time, and the rug pull from two `/check` reads. A
number typed into copy is accurate exactly once, and this page states facts to
people who cannot check them.

When the API does not answer, the page still renders and **labels itself
stale** rather than showing a stale number as if it were live.

Both reads sit behind Suspense boundaries. `GET /skills` costs roughly 2.8s
against the live API; awaiting it before rendering gave a 3.5s blank page,
measured in a production build. Streaming brings first paint to about 11ms.

## Design tokens are a copy, and the copy is guarded

`app/globals.css` is `frontend/app/globals.css` minus two imports whose
packages this app does not install. Everything else is byte-for-byte identical.

A copy is the arrangement that drifts quietly, so it is not left to anyone
remembering: `src/modules/landing/tokens.drift.test.ts` reads both files and
fails the build when they disagree. **Change tokens in
`frontend/app/globals.css` first**, then re-run the test and bring the change
across.

## Claims

Every factual claim on the page was verified before it was written, and the
record is in `docs/evidence/ste-23-landing-claims-2026-09-20.json`: both CVEs
against their published advisories, the x402 and USDC SAC wording against
Stellar's own docs, and the rug pull against the live registry.
