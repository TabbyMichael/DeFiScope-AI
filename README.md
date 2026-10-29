# DeFiScope AI

**DeFi protocol research, explainable risk scoring, and automated monitoring —
turning raw on-chain aggregates into evidence-backed research briefs.**

DeFiScope answers three questions for any protocol:

1. Is its growth sustainable, or driven by temporary incentives and price effects?
2. What are its major liquidity, concentration, and security risk exposures?
3. What should an analyst investigate, monitor, or avoid next?

Built on live [DefiLlama](https://defillama.com) data (public API, no key
required). Try it on [Aave](http://localhost:3000/protocols/aave-v3) vs
[Uniswap](http://localhost:3000/protocols/uniswap-v3).

## Features

| | |
|---|---|
| **Research dashboard** | Compare TVL, 7d/30d changes, volatility, chain concentration and risk bands across protocols — real data, live |
| **Explainable risk scoring** | Five weighted indicators; every score ships with its evidence *and* its limitations. Missing data becomes a visible `data gap`, never a fake "safe" |
| **AI research briefs** | Structured executive summary, growth drivers, risks, confidence, and next steps — LLM-generated when a key is configured, deterministic template otherwise (same sections, fully offline) |
| **Automated monitoring** | Scheduled rules flag TVL crashes, suspicious surges, incentive-heavy structures, and stale upstream data — each alert embeds the metric/threshold that fired it |

## Quick start

Prerequisites: [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
# 1. Backend (FastAPI + pandas) — port 8000
cd services/api
uv sync
uv run uvicorn app.main:app --port 8000 --reload

# 2. Frontend (Next.js + Tailwind + Recharts) — port 3000
cd ../../apps/web
npm install
npm run dev

# 3. Optional: enable LLM briefs (falls back to template engine without it)
cp ../../.env.example services/api/.env   # from apps/web; then set DEFISCOPE_OPENAI_API_KEY
```

Open http://localhost:3000. API docs at http://localhost:8000/docs.

Docker alternative (api + web + Postgres): `docker compose up --build`.

### Task runner

The repo-root [`Makefile`](Makefile) wraps the common flows (needs `make`, `uv`,
Node 20+). Run `make help` for the full list.

```bash
make install      # uv sync + npm install
make api-dev      # FastAPI on :8000 with autoreload
make web-dev      # Next.js on :3000
make check        # lint (ruff + eslint) + typecheck + tests
make gen-types    # regenerate openapi.json + frontend API types
make compose      # full stack via docker compose
make e2e          # Playwright e2e (needs `make compose` running first)
make tunnel       # publish the running app on a public Cloudflare URL
```

## Sharing the app (public link)

Want to send a working link to someone outside your machine? The repo ships a
[`scripts/tunnel.sh`](scripts/tunnel.sh) helper that opens a free
[Cloudflare Quick Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/)
and prints a public `https://<random-words>.trycloudflare.com` URL — no account,
no port forwarding, no firewall rules.

Run it **after** the app is already up (either mode works):

```bash
# 1. Start the stack (pick one) …
make compose                 # docker (web :4000, api :3646)
#   …or: make api-dev  +  make web-dev   # local dev (web :3000, api :8000)

# 2. …then publish it
make tunnel
#   or directly:
bash scripts/tunnel.sh
```

The helper auto-detects which ports are live (docker first, then dev), reuses an
installed `cloudflared` or downloads one into `.cloudflared-bin/` otherwise, and
tunnels both the web app and the API. Press `Ctrl+C` to stop sharing.

Useful flags / env:

```bash
bash scripts/tunnel.sh --web 4000     # force the web port (must match where the app listens)
bash scripts/tunnel.sh --api 8000     # force the API port
bash scripts/tunnel.sh --no-api       # tunnel only the web app
WEB_PORT=4000 API_PORT=3646 bash scripts/tunnel.sh
bash scripts/tunnel.sh --help
```

### Sharing on a non-default port

If you'd rather not use Next's default `:3000`, start the dev server on any free
port and tunnel that **same** port:

```bash
# terminal 1 - web app on :4000 (not :3000)
cd apps/web
npm run dev -- -p 4000

# terminal 2 - expose the same port
bash scripts/tunnel.sh --web 4000
```

A running tunnel can't switch ports — press `Ctrl+C` and relaunch with the new
`--web <port>` (a fresh URL is issued every run). If you use Docker instead, web
is already on `:4000` and the API on `:3646`, so plain `make tunnel` targets
those without any flags.

Notes:
- **Ephemeral URL.** Quick-tunnel addresses change on every run and only live as
  long as the script runs. For a stable custom domain, use a named
  `cloudflared tunnel` with your own Cloudflare account instead.
- **Dashboard data flows through the web tunnel** (the Next server calls the API
  server-side), so external users get the full app from the single web URL.
- The in-app **"API" docs link** is baked at build time to a `localhost` address,
  so share the separate API tunnel URL printed by the script for anyone who needs
  the raw OpenAPI docs.

## Tests

```bash
make test         # or: cd services/api && uv run pytest
```

Backend (pytest) + frontend (Vitest) suites cover metric primitives, risk
scoring, alert rules, DB-first dashboard reads, API contracts against mocked
DefiLlama responses (respx) and generated-type drift — no live network.

End-to-end (Playwright) specs live in [`apps/web/e2e`](apps/web/e2e) and run
against a full stack — bring it up with `make compose`, then `make e2e`
(the smoke suite tolerates an empty dataset while the startup warm-up runs).

## Design principles

- **Deterministic core, generative edge.** All numbers come from tested pure
  functions; the LLM only writes prose constrained to a structured evidence
  pack. Outputs are reproducible and auditable.
- **Honest uncertainty.** TVL conflates price and usage; audit counts don't
  prove safety. Every indicator states what it cannot establish, and every
  brief has a "what this analysis cannot establish" section.
- **Resilient research.** One dead protocol doesn't sink the board; stale data
  is flagged, not hidden; alerts are idempotent per protocol/rule/day.

Deep-dive docs: [methodology](docs/methodology.md) ·
[architecture](docs/architecture.md) ·
[sample research brief: Aave vs Uniswap](docs/sample-research.md) ·
[DeFi mechanics primer](docs/defi-mechanics-primer.md)

## Scope & limitations (stated, not hidden)

- TVL-based signals only: no wash-trading detection, no emissions schedules,
  no oracle/liquidation internals. Those need transaction-level data (Dune) and
  tokenomics sources.
- The security indicator is a weak proxy by design — a prompt for manual
  contract review, not a safety verdict.
- Score anchors and weights are documented judgment calls; challenge and tune
  them (see methodology table).

## Roadmap

1. Fee/revenue series join (DefiLlama `/summary/fees`) to decompose price-vs-usage.
2. Stablecoin depeg watch: per-peg deviation alerts with contagion mapping.
3. Dune-powered on-chain activity (daily users, real volume) for one flagship protocol.
4. Client-ready PDF/CSV export with sources, assumptions, and as-of timestamps.

*Built as a portfolio piece for DeFi research & strategy work — every design
choice optimizes for "can I defend this number in an interview?"*
