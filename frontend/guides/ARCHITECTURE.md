# Sterish Dashboard — Architecture Guide

> Read this before writing code in `frontend/`.
> Read it alongside [`docs/api-spec.md`](../../docs/api-spec.md) (frozen since STE-10) and
> [`app/globals.css`](../app/globals.css) (Nabil's design tokens).

The structure here follows the same pattern as `fe/` in the Sterun project, so that anyone
moving between the two repositories does not have to learn two layouts.

---

## 1. Separation of responsibilities

| Layer | What lives there |
| --- | --- |
| `app/` | routing only: no logic, no UI |
| `src/modules/` | one folder per page: logic plus UI |
| `src/components/` | primitives and layouts used across modules |
| `src/hooks/` | every client hook and provider |
| `src/lib/` | API and chain concerns: client, types, wallet kit, fixtures |
| `src/utils/` | pure helpers with no side effects |

---

## 2. Folder structure

```
frontend/
├── app/                                  <- ROUTING ONLY
│   ├── layout.tsx                        shell: fonts, Providers, Header, Footer
│   ├── providers.tsx                     where client providers are composed
│   ├── page.tsx                          /                    → <Registry />
│   ├── error.tsx                         error boundary
│   ├── globals.css                       tailwind + tokens (NABIL'S)
│   ├── skills/[skillId]/
│   │   ├── page.tsx                      /skills/:id          → <SkillDetail />
│   │   └── not-found.tsx                 skill is not registered
│   ├── tokens/page.tsx                   token preview, a design working tool
│   └── api/mock/[...path]/route.ts       delegates to src/lib/mockApi.ts
│
├── public/brand/logo/                    STE-7 assets from Nabil
├── guides/ARCHITECTURE.md                this file
│
└── src/
    ├── components/
    │   ├── elements/
    │   │   ├── VerdictBadge.tsx          4 verdicts: colour + icon + text
    │   │   └── ErrorNotice.tsx           takes an ApiError, not a raw string
    │   ├── layouts/
    │   │   ├── Header.tsx
    │   │   ├── Footer.tsx
    │   │   └── WalletButton.tsx
    │   └── ui/                           shadcn, managed by components.json
    │
    ├── modules/
    │   ├── registry/
    │   │   ├── Registry.tsx              rendered by app/page.tsx
    │   │   └── component/
    │   │       ├── RegistryTable.tsx
    │   │       ├── RegistryPagination.tsx
    │   │       └── RegistrySkeleton.tsx
    │   └── skill-detail/
    │       ├── SkillDetail.tsx           rendered by app/skills/[skillId]/page.tsx
    │       └── component/
    │           ├── VersionCard.tsx
    │           ├── VerdictBanner.tsx
    │           ├── EvidenceLinks.tsx
    │           └── CopyHash.tsx
    │
    ├── hooks/
    │   └── useWallet.tsx                 WalletProvider + useWallet
    │
    ├── lib/
    │   ├── api.ts                        the only door to the API
    │   ├── types.ts                      mirrors api-spec v1.0.0
    │   ├── wallet.ts                     Stellar Wallets Kit, lazily loaded
    │   ├── fixtures.ts                   4 verdict cases
    │   ├── mockApi.ts                    mock logic, outside app/
    │   └── utils.ts                      shadcn's `cn()`
    │
    └── utils/
        └── format.ts                     shortAddress, formatLedgerTime, shortHash
```

---

## 3. Rules per layer

### 3.1 `app/` — routing only

`page.tsx` does one thing: `await params` / `await searchParams`, then render the module's
component. If `useState`, `fetch`, or JSX beyond a single element appears, that is the sign the
code belongs in `modules/`.

The same goes for route handlers: `app/api/mock/[...path]/route.ts` only resolves params and
calls `handleMockRequest`. The logic lives in `src/lib/mockApi.ts`, which also lets the tests
call it directly without faking a route context.

### 3.2 `src/components/elements/` — primitives

Props-driven only. No fetching, no data-reading hooks. `ErrorNotice` takes an `ApiError` so it
can tell "the API said no" from "the API was unreachable"; those are two different facts and only
one of them deserves a retry button.

### 3.3 `src/modules/` — one folder per page

**Promotion rule:** used by one module, it stays in `component/`. Used by two or more, it moves
up to `components/elements/`. Never import from another module's `component/`; if you need to,
promote it first. `VerdictBadge` has been promoted because registry and skill-detail both use it.
`CopyHash` deliberately has not, because only one module uses it so far.

### 3.4 `src/lib/` — API and chain

Everything that knows about the API or about Stellar. Components must not know the details, and
there is **no `fetch` to the API outside `lib/api.ts`**. That is what makes swapping mock for live
a matter of one environment variable.

---

## 4. Rules specific to this product

### 4.1 A verdict belongs to one version, not to a skill

There is never a verdict badge at skill level. The registry table keeps `Latest` and `Audited`
in separate columns and marks the row when they differ. A skill whose newest release has not been
audited must not read as approved. Verdict inheritance across versions was a scaffold bug STE-5
removed from the contract, and it is just as wrong if it reappears in the UI.

### 4.2 A failed read is never a verdict

A failed read renders `ErrorNotice`, never a default value. An unreachable registry is not
evidence that a skill is safe. Fetches are also uncached, even though the spec permits 60
seconds, because a stale verdict is the worst thing this product could serve.

### 4.3 HTTP status codes must be honest

An unregistered skill must answer **404**, not a 200 carrying the text "not registered". That is
why `SkillDetail` awaits its fetch **without** Suspense: a shell that flushes first locks the
status at 200.

### 4.4 UI text in English, no em dashes

Every string that reaches the screen is in English. Em dashes are forbidden; use a comma, a full
stop, a colon or brackets. Since STE-41 this extends to every markdown document in the repository
as well, because the work is reviewed from outside the country.

### 4.5 Never write a raw colour value

Always go through the tokens in `app/globals.css`. Verdicts must never be distinguished by
colour alone: there is always an icon and a word, so they stay legible in greyscale and to
red-green colour-blind eyes.

---

## 5. What to know about the API

- **`GET /skills` used to be slow**, about 0.44 seconds per row, which is why this page asks for
  20 rows rather than the 50 the spec allows, sets a 30-second client timeout, and wraps the
  table in `<Suspense>`. STE-33 fixed the cause: `limit=20` is now around 2.8 seconds live. Both
  numbers are worth revisiting — 15 seconds is a saner timeout, and `limit=50` is viable at about
  4.6 seconds.
- **`report_uri` is populated** for the 19 seeded skills since STE-32, and `GET /reports` is
  live. The evidence panel can link to the report and show `findings[]`, `capabilities[]` and
  `recommendation` rather than saying "not published yet". The 47 older versions still return
  null, correctly: they predate report publishing.
- **The API still has no filter or sort.** Do not build client-side filter or sort controls over
  a single page; a label like "highest trust first" that only orders a third of the data
  misleads. Tracked as STE-34.

---

## 6. Path aliases and naming

`@/` points at `src/`. Never use `../../` across folders; inside a single module, relative is fine.

| Item | Convention | Example |
| --- | --- | --- |
| Component file | PascalCase | `VersionCard.tsx` |
| Hook file | camelCase, `use` prefix | `useWallet.tsx` |
| Lib / utility file | camelCase | `mockApi.ts`, `format.ts` |
| Local component folder | lowercase | `component/` |
| Module folder | kebab-case | `skill-detail/` |
| TypeScript type | PascalCase | `type Verdict = …` |
| Constant | SCREAMING_SNAKE_CASE | `PAGE_SIZE`, `API_BASE_URL` |

---

## 7. Commands

```bash
pnpm dev          # http://localhost:3000
pnpm typecheck    # next typegen && tsc --noEmit
pnpm lint
pnpm test         # vitest: data layer + mock API
pnpm build
```

`next typegen` must run before `tsc`: `PageProps` and `RouteContext` are generated into
`.next/types` and do not ship inside the `next` package. Without it, typecheck is green on a
machine that happens to have run `next dev` and red in CI.

**For any claim that decides CI, verify in a clean clone**, not in this worktree.
