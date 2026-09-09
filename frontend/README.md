# Sterish dashboard

Next.js 16 App Router, React 19, Tailwind 4, shadcn/ui. Reads the verification
API described in [`docs/api-spec.md`](../docs/api-spec.md) and connects a
Stellar wallet through Stellar Wallets Kit.

## Run it

```bash
pnpm install
cp .env.example .env.local     # then edit if you want something other than live
pnpm dev                       # http://localhost:3000
```

`pnpm` is required, not npm: the lockfile is `pnpm-lock.yaml` and CI installs
with `--frozen-lockfile`.

## Checks

```bash
pnpm typecheck    # next typegen && tsc --noEmit
pnpm lint         # eslint
pnpm test         # vitest, the data layer and the mock API
pnpm build        # next build
```

CI runs exactly these four, in that order.

## Where the data comes from

Every read goes through `src/lib/api.ts`. Nothing else in the app calls `fetch`
against the API, so switching data sources is an environment change and never a
code change. The layout of the rest is described in
[`guides/ARCHITECTURE.md`](./guides/ARCHITECTURE.md), which follows the same
shape as Sterun's `fe/`.

| `NEXT_PUBLIC_API_URL` | What you get |
|---|---|
| `https://api-sterish.jameshub.fun` | The live testnet API |
| `http://localhost:8000` | An API you are running yourself |
| `http://localhost:3000/api/mock` | Fixtures, no network needed |

`NEXT_PUBLIC_*` values are inlined at build time, so after changing one, restart
`pnpm dev` (or rebuild) rather than only reloading the page.

### The mock

`app/api/mock/[...path]/route.ts` answers the read endpoints of the spec
(sections 3.1 to 3.5) from `src/lib/fixtures.ts`, including the section
4 error bodies. It exists for two reasons:

1. The live testnet registry currently holds only `SAFE` and `DANGEROUS` rows.
   `WARNING` and `UNAUDITED` have no live example, and both need to look right.
2. It makes the UI developable with no network at all.

It also covers cases that are awkward to produce on chain: a skill whose newest
version was never audited, and a skill that was never audited at all.

## Two things worth knowing

**The API is slow, and the dashboard is shaped around it.** Measured against the
live API on 2026-09-09, `GET /skills` costs roughly 0.44s per row: 3 skills in
2.5s, 20 in 9.9s, 50 in 22s. It appears to read each row separately rather than
batching. The registry page therefore asks for 20 rows, not the 50 the spec
allows, and the client timeout is 30s so that a slow-but-working API renders
instead of being reported as unreachable. The table is inside `<Suspense>`, so
the page shell paints immediately and the rows stream in. If the fan-out is
fixed, both numbers should come back down.

**A verdict belongs to one version, never to a skill.** The registry table shows
`Latest` and `Audited` as separate columns for exactly this reason, and marks
the row when they differ. A skill whose newest version was never audited must
never read as endorsed.

## Wallet

`src/lib/wallet.ts` and `src/hooks/useWallet.tsx` wrap Stellar Wallets Kit 2.x. Two things about it that cost
time to work out:

- It is a **static** class with `init()`. Examples showing
  `new StellarWalletsKit({...})` and `kit.openModal()` are version 1 and do not
  compile against what is installed.
- It persists the session (`activeAddress`, `selectedModuleId`) to
  `localStorage` itself, so a refresh keeps the connection with no persistence
  code here. Because the server cannot see that, the header renders a
  placeholder until after mount rather than guessing.

The kit is imported dynamically, so its wallet tree stays out of the first load
and only downloads when somebody clicks Connect.
