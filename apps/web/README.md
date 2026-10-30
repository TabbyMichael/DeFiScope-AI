# DeFiScope AI — Web (Next.js)

The research dashboard for DeFiScope AI: a Next.js 16 App Router app (React 19,
TypeScript, Tailwind v4, Recharts, shadcn/ui) that renders a server-driven
DeFi risk board, per-protocol detail, alerts, a comparison matrix, and the
grounded "ask the analyst" chat. It is a **thin, typed client over the FastAPI
analytics service** (`services/api`) — no research math happens here.

See the repo-root [README](../../README.md) for the product overview and the
[architecture doc](../../docs/architecture.md) for the full system design.

## Running it

```bash
npm install
npm run dev            # http://localhost:3000  (expects the API on :8000)
```

Point it at the backend with `NEXT_PUBLIC_API_URL` (default
`http://localhost:8000`). In the Docker stack this app is served on **:4000** and
the API on **:3646**.

### Environment variables (build-time)

| Var | Purpose |
|---|---|
| `NEXT_PUBLIC_API_URL` | Base URL the **Next server** uses for its own fetches (may be a compose-internal host like `http://api:8000`). |
| `NEXT_PUBLIC_API_PUBLIC_URL` | A **browser-reachable** API URL for the docs link / any client-side call. Falls back to the server URL, then `http://localhost:8000`. |
| `NEXT_PUBLIC_API_WS_URL` | Browser-reachable WebSocket base for streamed chat tokens (e.g. `ws://localhost:3646`). Derives `ws:`/`wss:` from the public URL when unset. |

> The compose-internal host is resolvable only inside the Docker network, so the
> browser never calls it directly: server components and the same-origin route
> handlers below proxy to the backend, and only the public/WS URLs reach the client.

## Pages & route handlers

| Route | What it is |
|---|---|
| `/` | Server-component board: stat cards, sortable/filterable protocol table with sparklines, aggregate TVL history, risk watchlist. |
| `/protocols/[slug]` | Protocol detail: TVL chart, chain breakdown, explainable indicator cards (each with its limitation), risk-score trend (`RiskTrendChart`), brief, export buttons. |
| `/alerts` | Live rule evaluation + persisted history, with a manual "run check" (auto-refresh). |
| `/ask` | Grounded RAG chat panel — streams tokens over WebSocket, falls back to `POST /api/chat`; shows numbered citations and `generated_by`. |
| `/compare` | Side-by-side matrix for 2–3 protocols, selection encoded in the URL. |
| `/about` | Methodology / honesty statement. |
| `api/chat`, `api/run-check`, `api/brief-export/[slug]` | Same-origin Next route handlers that forward to the backend so `NEXT_PUBLIC_API_URL` stays server-only. |

`lib/api.ts` is the single API client (GET/POST/POST-JSON helpers with per-route
timeouts and `next: { revalidate }` caching). `lib/types.ts` derives ergonomic,
non-optional view types **from** the generated `lib/api-types.ts` contract (never
hand-mirrored), `lib/compare.ts` holds comparison logic, and `lib/utils.ts` is the
`cn` helper.

## Types are generated, not hand-written

`lib/api-types.ts` is code-generated from the backend's OpenAPI schema:

```bash
npm run gen:types      # openapi-typescript ../../services/api/openapi.json -o lib/api-types.ts
npm run check:types    # regenerate + `git diff --exit-code` — CI drift gate
```

Regenerate after any backend schema change (or run `make gen-types` at the repo
root, which also refreshes `openapi.json`).

## Testing

```bash
npm run test           # Vitest unit/component tests (jsdom + React Testing Library)
npm run test:e2e       # Playwright against a running full stack (`make compose` first)
npm run test:e2e:install   # playwright install --with-deps chromium
```

Unit specs live under `components/__tests__/` and `lib/__tests__/`; Playwright
specs live in `e2e/` and are **excluded from Vitest** (they need a browser + live
stack, not jsdom). `npm run lint` (ESLint) and `npm run typecheck` (`tsc
--noEmit`) complete the checks.

## Scripts

`dev` · `build` · `start` · `lint` · `typecheck` · `test` · `test:watch` ·
`test:e2e` · `test:e2e:install` · `gen:types` · `check:types`.

## Notes

- **Server Components by default.** Data is fetched on the server; only
  interactive leaves (charts, chat panel, dropdowns, the run-check trigger, theme
  toggle) are client components.
- Next.js 16 enables **Cache Components**; runtime-data views are wrapped in
  `Suspense` and reads opt into revalidation windows rather than prerendering.
- Dark/light theming is via `next-themes` (`components/theme-provider.tsx`).
- The `AGENTS.md` block in this directory is managed automatically by `next dev`
  — do not hand-edit it.
This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
