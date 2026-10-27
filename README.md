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

## Tests

```bash
cd services/api && uv run pytest
```

41 tests covering metric primitives, risk scoring behavior, alert rules, and
API contracts against mocked DefiLlama responses (respx) — no live network.

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
