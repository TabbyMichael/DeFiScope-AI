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
| **Research dashboard** | Compare TVL, 7d/30d changes, volatility, fees & DEX volume, chain concentration and risk bands across the whole market — curated protocols **plus the top 50 by TVL auto-discovered** from the DefiLlama directory (CEX/bridge/chain totals excluded). Rendered DB-first from daily snapshots |
| **Explainable risk scoring** | Seven weighted indicators (chain concentration, TVL volatility & trend, incentive & real-yield dependence, security posture, stablecoin peg integrity); every score ships with its evidence *and* its limitations. Missing data becomes a visible `data gap` and renormalizes out of the composite — never a fake "safe" |
| **AI research briefs + downloads** | Structured executive summary, growth drivers, risks, confidence and next steps — LLM-generated when a key is configured, deterministic template otherwise (same sections, fully offline). Exportable as **Markdown, CSV or print-ready PDF** (`GET /api/briefs/{slug}/export`) |
| **Ask the analyst (RAG chat)** | Grounded Q&A over our own methodology docs + each protocol's evidence (indicators, limitations, data gaps, alerts) — every answer cites numbered sources and states what it *cannot* establish. Works offline (BM25 retrieval + extractive answers) with a method-aware relevance gate that refuses off-topic questions, or streams tokens over WebSocket with OpenAI / a free local Ollama model |
| **Side-by-side comparison** | Pick 2–3 protocols into a shareable `/compare` matrix (URL-encoded selection) to tell the "Aave vs Uniswap vs Lido" story |
| **Automated monitoring + delivery** | Scheduled rules flag TVL crashes, one-day shocks, suspicious surges, incentive-heavy structures, stablecoin depegs and stale upstream data — each alert embeds the metric/threshold that fired it, persists idempotently per protocol/rule/day, and fans out to **console / webhook / Slack / Discord / Telegram / email** (every channel activates only when its env secret is set) |

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

## Ask the analyst — local LLM via Ollama (free, offline)

The `/ask` chat retrieves grounding evidence from our own `docs/` and each
protocol's indicators / data-gaps / alerts, then answers **citing numbered
sources and stating what it cannot establish**. With no model configured it runs
fully offline: retrieval falls back to a pure-Python BM25 index and answers are
composed *extractively* from quoted passages. To get fluent natural-language
answers without a cloud key or cost, point the same OpenAI-compatible endpoint at a
free local [Ollama](https://ollama.com) model.

> Always use Ollama's **`/v1` OpenAI-compatible shim**, not its native `/api/chat`
> — the app parses OpenAI-style SSE (`data:` … `[DONE]`), which only `/v1` emits.

### Option A — Ollama on your host

```bash
# one-time: install Ollama and pull a chat model
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:7b-instruct     # richer prose; llama3.2 / qwen2.5:3b run on less RAM

# then in services/api/.env:
DEFISCOPE_OPENAI_BASE_URL=http://localhost:11434/v1
DEFISCOPE_OPENAI_API_KEY=ollama          # any non-empty value; the LLM path
                                          # enables only when a key is SET -
                                          # Ollama ignores the token itself
DEFISCOPE_OPENAI_MODEL=qwen2.5:7b-instruct
```

Restart the API (`make api-dev`), then open http://localhost:3000/ask.

### Option B — Ollama in Docker (opt-in profile)

The [`ollama`](docker-compose.yml) service (plus an optional `open-webui`
developer console) lives behind an opt-in profile, so the default stack stays
lean and never hard-depends on a multi-GB model:

```bash
docker compose --profile llm up -d
docker compose exec ollama ollama pull qwen2.5:7b-instruct

# and in services/api/.env, use the internal service hostname:
DEFISCOPE_OPENAI_BASE_URL=http://ollama:11434/v1
DEFISCOPE_OPENAI_API_KEY=ollama
DEFISCOPE_OPENAI_MODEL=qwen2.5:7b-instruct
```

### Tuning long, engaging answers (and a gotcha we verified)

Retrieval stays lexical (BM25) — **no embeddings or DB setup required** for a
local LLM. Local CPU models are slow, so if answers get truncated you may need to
lift the generation budget and give the request enough time:

```bash
DEFISCOPE_RAG_MAX_TOKENS=1600           # longer answers (default)
DEFISCOPE_RAG_LLM_TIMEOUT_SECONDS=150   # slow CPU models exceed short timeouts
DEFISCOPE_RAG_TEMPERATURE=0.5           # a little more fluent, still grounded
```

When we tested this on CPU, a 7B model at the previous fixed 90s timeout timed
out and the chat **auto-degraded to the offline extractive answer** — the safety
net working as designed, and the reason the timeout is now configurable. If
Ollama is ever down, the app keeps answering from cited evidence instead of
erroring.

The honesty contract is enforced by the system prompt, not by restraining the
model: it must answer only from the numbered context, attribute every claim to
`[n]`, never invent numbers, and say what the evidence cannot establish.

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

Shipped since the MVP: fee/revenue/DEX-volume join (decomposes price vs usage),
stablecoin depeg watch, PDF/CSV/Markdown export, risk-score history, alert
delivery, side-by-side comparison, and the grounded RAG chat.

Still open (see [docs/modernization-roadmap.md](docs/modernization-roadmap.md)):

1. Auth + rate limiting on the mutating/admin routes (a must-fix before any
   public deploy — `POST /api/alerts/run` is an unauthenticated crawl today).
2. Dune-powered on-chain activity (daily users, real volume, liquidations) for a
   flagship protocol; move beyond the TVL proxy.
3. Cross-protocol correlation / stablecoin-contagion mapping.
4. Adaptive anomaly detection (replacing static thresholds) and price-normalized
   TVL once a reliable protocol→token map exists.

*Built as a portfolio piece for DeFi research & strategy work — every design
choice optimizes for "can I defend this number in an interview?"*
