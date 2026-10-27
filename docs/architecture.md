# Architecture

DeFiScope AI is a two-tier monorepo: a Next.js research dashboard over a
FastAPI analytics service. The split is deliberate — deterministic research
math lives in Python (testable, pandas-native), while presentation and
navigation live in React.

```
defiscope-ai/
├── apps/web/                  # Next.js 16 + TypeScript + Tailwind + Recharts
│   ├── app/                   # App Router: dashboard, protocol detail, alerts, about
│   ├── components/            # TvlChart (client), IndicatorCard, RiskBadge
│   └── lib/                   # api client + types mirroring backend schemas
├── services/api/              # FastAPI + pandas analytics service
│   ├── app/
│   │   ├── clients/defillama.py    # HTTP client + response normalization (+ edge cases)
│   │   ├── analysis/metrics.py     # pure metric primitives (tested)
│   │   ├── analysis/scoring.py     # explainable risk indicators & composite
│   │   ├── services/protocols.py   # orchestration + TTL cache
│   │   ├── services/briefs.py      # LLM briefs + deterministic template fallback
│   │   ├── services/alerts.py      # monitoring rules + persistence
│   │   ├── routers/                # /api/protocols /api/briefs /api/alerts
│   │   ├── db.py                   # SQLAlchemy (SQLite default, Postgres ready)
│   │   └── main.py                 # lifespan, CORS, scheduler (30-min monitoring)
│   └── tests/                      # 41 tests: metrics, scoring, alerts, API (respx)
├── docs/                      # methodology, sample research, DeFi primer
└── docker-compose.yml         # api + web + postgres for shared deploys
```

## Data flow

```
DefiLlama API ──fetch──▶ DefiLlamaClient ──normalize──▶ metrics.series_to_frame
     (public, no key)         │                            │
                               │                            ▼
                        /protocols index ──────▶ scoring.assess ──▶ RiskAssessment
                                                              │
                 ┌────────────────────────────────────────────┤
                 ▼                       ▼                    ▼
        routers/protocols         services/briefs      services/alerts
        (JSON for UI)             (LLM | template)     (rules + DB persist)
                 │                       │                    │
                 └─────────── Next.js server components ──────┘
```

## Key decisions

1. **Deterministic core, generative edge.** All numbers come from tested pure
   functions (`analysis/`). The LLM never computes — it only composes prose from
   a structured evidence pack, and a deterministic template produces the same
   sections when no API key is configured. This keeps outputs reproducible and
   interview-defensible.
2. **Cache in front of a public API.** In-process TTL cache (5 min) per protocol
   prevents dashboard polling from hammering DefiLlama; DefiLlama itself updates
   hourly.
3. **Missing data is visible data.** Indicators that cannot be computed return
   `None`, are excluded from the composite (weights renormalized), appear under
   `data_gaps` in the payload, and are rendered in the UI. Unknown is never
   rendered as safe.
4. **Idempotent monitoring.** Alert IDs derive from (protocol, rule, date), so
   repeated scheduler passes do not duplicate history. Snapshots are one row per
   protocol per day, building a local time series independent of upstream
   retention.
5. **SQLite first, Postgres when shared.** Zero-setup default; the same
   SQLAlchemy models run against the docker-compose Postgres via
   `DEFISCOPE_DATABASE_URL`.

## API surface (self-documented at /docs via FastAPI)

| Endpoint | Purpose |
|---|---|
| `GET /api/protocols` | Normalized comparison board with risk bands |
| `GET /api/protocols/{slug}` | TVL series, chain breakdown, full evidence payload |
| `GET /api/briefs/{slug}` | Structured research brief (+ markdown, sources, as-of) |
| `GET /api/alerts` | Live rule evaluation with triggering evidence |
| `GET /api/alerts/history` | Persisted alert log |
| `GET /api/health` | Liveness + monitored protocol list |

## Operational notes

- The scheduler (APScheduler) runs inside the API process; a multi-worker
  deployment should move `run_monitor` to a single dedicated worker/cron.
- One failing protocol slug never sinks the dashboard: per-protocol errors are
  logged and skipped (`get_packs`).
- The web tier degrades to an explicit "API unavailable" state with the exact
  restart command rather than an empty dashboard.
