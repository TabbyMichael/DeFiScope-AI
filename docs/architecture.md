# Architecture

DeFiScope AI is a monorepo pairing a **Next.js 16 research dashboard** with a
**FastAPI analytics service**. The split is deliberate: deterministic research
math lives in Python (testable, pandas-native), while presentation, navigation
and the grounded chat live in React over a typed API contract.

Everything degrades gracefully. With no API key and no network the service still
scores protocols, fires threshold alerts, renders the board from its own
snapshots, and answers chat questions *extractively* from quoted evidence — the
LLM is an enhancement, never a dependency.

## Repository layout

```
DeFiScope-AI/
├── apps/web/                       # Next.js 16 + React 19 + TS + Tailwind v4 + Recharts
│   ├── app/
│   │   ├── (dashboard)/            # RSC pages: board, protocols/[slug], alerts, ask, compare, about
│   │   └── api/                    # same-origin route handlers: chat, run-check, brief-export/[slug]
│   ├── components/
│   │   ├── dashboard/             # stat-cards, protocol-table, sparkline, alert-feed/item,
│   │   │                          #   risk-watchlist, compare-matrix, compare-picker
│   │   ├── chat/                  # chat-panel (WS streaming + HTTP fallback)
│   │   ├── TvlChart, RiskTrendChart, IndicatorCard, RiskBadge, app-sidebar, mode-toggle …
│   │   └── ui/                    # shadcn primitives
│   ├── lib/                       # api.ts client, api-types.ts (OpenAPI codegen), compare.ts, types.ts
│   └── e2e/                       # Playwright specs
├── services/api/                    # FastAPI + pandas analytics service
│   ├── app/
│   │   ├── clients/defillama.py    # one async client, five endpoints, retry/backoff, best-effort enrichment
│   │   ├── analysis/metrics.py     # pure metric primitives (all unit-tested)
│   │   ├── analysis/scoring.py     # seven explainable risk indicators → renormalized composite
│   │   ├── services/protocols.py   # orchestration + bounded TTL cache + market discovery
│   │   ├── services/dashboard.py   # DB-first board reads, sparklines, aggregate stats, risk history
│   │   ├── services/briefs.py      # LLM brief + deterministic template fallback (same sections)
│   │   ├── services/alerts.py      # pure rule evaluation, idempotent persistence, notify fan-out
│   │   ├── services/export.py      # brief → Markdown / CSV / PDF (reportlab)
│   │   ├── notifiers/              # console, webhook, slack, discord, telegram, email
│   │   ├── rag/                    # chunking · embeddings · lexical(BM25) · ingest · service
│   │   ├── routers/               # protocols · briefs · alerts · dashboard · chat
│   │   ├── db.py                  # SQLAlchemy models; SQLite default, Postgres + pgvector
│   │   ├── reference_data.py      # curated protocol→stablecoin map (data/*.json)
│   │   ├── config.py              # pydantic-settings (DEFISCOPE_ env prefix)
│   │   └── main.py                # lifespan, CORS, scheduler (30-min pass), health/readiness
│   ├── alembic/                    # migrations (schema source of truth)
│   ├── data/protocol_stablecoins.json
│   └── tests/                      # 152 pytest: metrics, scoring, clients, alerts, dashboard,
│                                   #   watchlist, export, notifiers, RAG (ingest + service), API (respx)
├── services/db/                    # Postgres 16 + pgvector, built on Alpine (not the Debian
│   └── Dockerfile                  #   pgvector image): compiles pgvector from source; lower CVE profile
├── docs/                           # methodology · architecture · primer · sample research · roadmap
├── scripts/tunnel.sh               # Cloudflare quick-tunnel publisher
├── Makefile                        # task runner wrapping the flows below
└── docker-compose.yml              # builds db + api + web (all Alpine), plus opt-in `llm` profile
```

## Data flow

```
                         ┌──────────── DefiLlama (public, no key) ────────────┐
                         │ /protocols  /protocol/{slug}  fees/…  /overview/dexs│
                         │                        coins.llama.fi /chart         │
                         └───────────────┬──────────────────────────────────────┘
                                         ▼
                     clients/defillama.py  ──normalize──▶  ResearchPack
                                         │            (detail + summary + fees
                                         │             + volume + peg histories)
                                         ▼
                     analysis/metrics.py (pure primitives)
                                         ▼
                     analysis/scoring.assess ──▶ RiskAssessment
                    (7 indicators → renormalized composite + data_gaps)
                                         │
        ┌──────────────┬────────────────┼─────────────────┬───────────────┐
        ▼              ▼                ▼                 ▼               ▼
  services/        services/        services/        services/       rag/ingest
  protocols        dashboard        briefs           alerts          (docs + evidence
  (TTL cache,      (DB-first        (LLM |            (rules →        chunks → BM25/
   discovery)      reads +          template)          persist +       cosine index)
        │           hydrate)                            notify)            │
        ▼              ▼                ▼                 ▼               ▼
     routers/protocols · dashboard · briefs · alerts · chat  ── OpenAPI ──▶ apps/web
                                        │                                   (RSC + codegen types)
                                        ▼
                          notifiers/  (console/webhook/slack/discord/telegram/email)
```

The scheduler (`main.py`) drives a **30-minute monitoring pass**: discover the
watchlist (curated slugs + top-N by TVL), fetch packs concurrently, evaluate
rules, persist daily snapshots + alerts, and fan new alerts out to configured
channels. The same pass runs once at startup as a **background task** (never
awaited in the lifespan, so a slow crawl can't delay the port bind or fail
readiness). The RAG index is hydrated synchronously from any persisted chunks
(offline-capable from the first request) and refreshed in the background after
warm-up, because the evidence chunks are derived from the snapshots/alerts.

## Persistence

SQLAlchemy models in [`db.py`](../services/api/app/db.py) back three tables:

| Table | Purpose |
|---|---|
| `protocol_snapshots` | One row per protocol per day (unique `(slug, date)`): the full normalized overview + composite score/band. Enables a **DB-first** dashboard, sparklines and the risk-score trend, independent of upstream retention. First sight of a slug backfills the whole DefiLlama history. |
| `alert_records` | Durable alert log keyed by deterministic `alert-{sha256(slug:rule:day)}` id, so re-runs **upsert** rather than duplicate. `notified_at` is the delivery cooldown/dedup marker. |
| `chat_chunks` | One indexed passage per RAG chunk. `chunk_id` is a provenance-scoped content hash (`doc_id ␟ section ␟ body`) so identical boilerplate across sources gets distinct ids while unchanged text keeps a stable id; `doc_id` lets a whole source be replaced on refresh. `embedding` is **pgvector `Vector(1536)` on Postgres**, plain JSON on SQLite (ranked in-process). |

Default DB is **SQLite** (zero setup); the same models run against the
docker-compose **Postgres** via `DEFISCOPE_DATABASE_URL`. Schema changes go
through **Alembic** (`services/api/alembic`); `init_db()` also adds any missing
column idempotently as a safety net for a volume that predates a deploy, and
best-effort `CREATE EXTENSION vector` so a non-pgvector install degrades to
lexical chat instead of crashing.

## Key decisions

1. **Deterministic core, generative edge.** Every number comes from a tested pure
   function in `analysis/`. The LLM never computes — it only composes prose from a
   structured evidence pack (`services/briefs.py`), and a deterministic template
   produces the same sections offline. `generated_by` is always surfaced.
2. **Missing data is visible data.** Indicators that can't be computed return
   `None`, are excluded from the composite (weights renormalized), appear under
   `data_gaps`, and render in the UI. Unknown is never rendered as "safe" — and
   an absent fees/price feed stays a gap, never a zero.
3. **Resilient against a public upstream.** One client wraps retry/backoff
   (honouring `Retry-After`, no retry on 404), bounds the per-protocol TTL cache
   (LRU, 5-min) and the crawl concurrency, and treats the fees/volume/peg
   enrichment as strictly best-effort: a dead secondary host degrades to a data
   gap, not a failed pack. One bad protocol never sinks the board.
4. **DB-first reads with a serialized live fallback.** The dashboard renders from
   snapshots; it runs a live monitoring pass only when the newest capture is
   stale (> 6h), guarded by an `asyncio.Lock` so a cold-start burst triggers a
   single crawl, not N.
5. **Method-aware chat grounding.** Cosine (`[0,1]`) and BM25 (unbounded) scores
   aren't comparable, so relevance is gated by the method that produced them: a
   fixed cosine floor for the vector path, a shared-informative-term bar for the
   lexical path. The chat then refuses (`generated_by="none"`) rather than quote
   irrelevant passages. See [methodology](methodology.md).
6. **Honesty is structural, not a prompt.** Alerts embed their triggering metric /
   observed value / threshold; notifier failures are logged by exception *type*
   only (never `str(exc)`, which would leak a secret-laden webhook URL); exports
   neutralize spreadsheet formula injection. Provider secrets are read only to
   open an outbound connection and are never persisted or logged.
7. **SQLite first, Postgres when shared.** Zero-setup dev; the compose stack
   swaps in Postgres + pgvector with no code change.

## API surface (self-documented at `/docs` via FastAPI)

| Endpoint | Purpose |
|---|---|
| `GET /api/protocols` | Normalized comparison board with risk bands (live, cached) |
| `GET /api/protocols/{slug}` | TVL series, chain breakdown, full evidence payload |
| `GET /api/dashboard` | DB-first board: latest snapshot per protocol + stats + alerts + aggregate history |
| `GET /api/protocols/{slug}/history?days=` | Trailing daily TVL points (sparkline/trend) |
| `GET /api/protocols/{slug}/risk-history?days=` | Daily composite risk-score trend (scored days only) |
| `GET /api/briefs/{slug}` | Structured research brief (LLM or template) + markdown + sources |
| `GET /api/briefs/{slug}/export?format=md\|csv\|pdf` | Brief rendered for download (`Content-Disposition` attachment) |
| `GET /api/alerts` | Today's persisted alerts (fast DB read, no crawl) |
| `GET /api/alerts/history?limit=` | Durable alert log |
| `POST /api/alerts/run` | Manual/full monitoring pass: crawl → evaluate → persist → notify (no auth — see note) |
| `POST /api/chat` | Grounded Q&A, single request/response (WS fallback) |
| `WS /ws/chat` | Streaming chat (`token` / `citations` / `done` frames; chosen over SSE because Cloudflare quick tunnels pass WS but not SSE) |
| `GET /api/health` | Liveness (always 200; surfaces DB state + curated protocol list) |
| `GET /api/health/ready` | Readiness (503 until the DB answers, for compose/k8s probes) |

The browser never sees the compose-internal API host: server components and the
same-origin Next route handlers (`/api/chat`, `/api/run-check`,
`/api/brief-export/[slug]`) proxy to the backend, so `NEXT_PUBLIC_API_URL` stays
server-only and only `NEXT_PUBLIC_API_PUBLIC_URL` / `…_WS_URL` (build-time) are
opened by the client. Types are generated from the exported OpenAPI
(`make gen-types`; CI drift-checks with `check:types`).

## Operational notes

- **APScheduler runs in-process.** A multi-worker deployment must move
  `run_monitor` to a single dedicated worker/cron so passes don't multiply.
- **No authentication yet.** `POST /api/alerts/run` is an expensive admin-shaped
  crawl with no auth — fine for the local showcase, a must-fix before any public
  deploy (roadmap #17).
- One failing protocol is logged and skipped (`get_packs`); one dead notifier
  channel is logged and swallowed without aborting the pass.
- The web tier degrades to an explicit "API unavailable" state with the exact
  restart command rather than an empty dashboard.
