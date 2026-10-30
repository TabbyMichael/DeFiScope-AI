# DeFiScope AI — Modernization Roadmap

> A menu of feature additions to modernize DeFiScope, grounded in the current
> implementation. This is **a prioritized menu, not a checklist** — "modern"
> does not require building everything. Use the decision column below to choose
> which items we implement next.

Last updated: 2026-10-29

---

## 1. Where the tool is today (context)

The spine of DeFiScope is **DefiLlama-only** data. From one upstream family
(TVL + fees + DEX volume + coin prices, all public/no key) it derives an
explainable seven-indicator risk model, threshold alerts with multi-channel
delivery, a DB-first dashboard, an LLM-or-template research brief (exportable), a
side-by-side comparison, and a grounded "ask the analyst" RAG chat.


| Layer       | File(s)                                                      | What it does today                                                                                                                                     |
| ----------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Data client | `services/api/app/clients/defillama.py`                      | Calls `/protocols`, `/protocol/{slug}` (TVL history, staking, borrowed, `currentChainTvls`, audit count), `fees.llama.fi/summary/fees` (fees+revenue), `/overview/dexs` (volume), `coins.llama.fi/chart` (peg prices). Retry/backoff honouring `Retry-After`; secondary fetches best-effort (fail → data gap). |
| Metrics     | `services/api/app/analysis/metrics.py`                       | Pure primitives: volatility, drawdown, pct-change, chain HHI, incentive ratio, fees/volume-to-TVL, peg deviation (bps) + duration, freshness, price-normalized TVL (defined, not yet wired). |
| Scoring     | `services/api/app/analysis/scoring.py`                       | 7 weighted indicators → composite 0-100 + band (renormalized over available). Each ships `evidence` + `limitation`; missing data → `data_gaps` (excluded, never "safe"). |
| Alerts      | `services/api/app/services/alerts.py`                        | Rules: TVL drop/surge, daily shock, incentive dependence, stale data, depeg. DB-persisted, idempotent upsert; fan-out to notifiers with cooldown/dedup. `POST /api/alerts/run` + 30-min scheduler. |
| Delivery    | `services/api/app/notifiers/`                                | console / webhook / slack / discord / telegram / email; each activates only when its env secret is set. Secrets never logged/persisted. |
| Briefs      | `services/api/app/services/briefs.py`                        | Evidence-pack → OpenAI-compatible JSON; deterministic template fallback when no key. Same sections offline. |
| Export      | `services/api/app/services/export.py`                        | Brief → Markdown / CSV (formula-injection-safe) / PDF (reportlab) via `GET /api/briefs/{slug}/export`. |
| Chat (RAG)  | `services/api/app/rag/`, `routers/chat.py`                   | BM25 (offline) or cosine+pgvector retrieval over docs + per-protocol evidence; method-aware relevance gate; `llm`/`extractive`/`none` outcomes with numbered citations. `POST /api/chat` + `WS /ws/chat`. |
| Dashboard   | `services/api/app/services/dashboard.py`                     | DB-first reads w/ live hydration fallback; sparklines, aggregate TVL, stats, movers, risk-score history. |
| Contracts   | `services/api/app/schemas.py` → `apps/web/lib/api-types.ts` | OpenAPI-exported + codegen'd via `openapi-typescript`; CI drift-checks.                                                                                 |
| Web         | `apps/web/app/(dashboard)/*`                                 | Next 16 RSC board, protocol detail (+ risk-trend chart), alerts + run-check/auto-refresh, `/ask` chat panel (WS streaming), `/compare` matrix, sort/filter table, TVL chart, dark/light. |

**The differentiator to protect:** intellectual honesty — every score shows
evidence + limitation, gaps stay visible, and it works offline. New features must
not turn this into a black box.

**The biggest limitation:** almost everything is a proxy for **USD TVL**, which
(as the app itself repeats) *conflates price with usage*. The highest-leverage
modernization is to **expand the data surface** so the risk model stops guessing.

---

## 2. Feature menu (all 22)

Effort: S = small, M = medium, L = large. Impact: the same scale.

### Tier 1 — High leverage, low effort (recommended first)


| # | Feature                                                   | Impact   | Effort | Depends on        | Files touched                                                           | Implementation notes                                                                                                                                                                                                                                                                        |
| - | --------------------------------------------------------- | -------- | ------ | ----------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | **Fees + revenue + volume (decompose price vs usage)**    | High     | M      | —                | `defillama.py`, `metrics.py`, `scoring.py`, `schemas.py`, protocol page | New client methods:`GET /summary/fees/{slug}`, `GET /summary/dexs/{slug}`, `GET /overview`. New metrics: volume/TVL, fees/TVL ("capital efficiency"), price-normalized TVL via `coins.llama.fi`. New indicator `real_yield_dependence`. Closes the "cannot establish organic activity" gap. |
| 2 | **Stablecoin depeg watch**                                | High     | M      | —                | `defillama.py`, `metrics.py`, `scoring.py`, `alerts.py`, `schemas.py`   | `GET https://stablecoins.llama.fi/stablecoin/{asset}` (peg-deviation history). Indicator `depeg_exposure`; alert rule `depeg` (> X bps in 30d).                                                                                                                                             |
| 3 | **Alert delivery (email/Slack/Discord/Telegram/webhook)** | High     | M      | alerts            | `services/alerts.py`, `config.py`, new `notifiers/` module              | Fan out after`persist_alerts(...)`; reuse deterministic alert id as the notification dedup/cooldown key.                                                                                                                                                                                    |
| 4 | **Historical risk-score trend**                           | Med-High | S      | snapshots (exist) | `routers/protocols.py`, `services/dashboard.py`, protocol page          | Already writing`risk_score`/`risk_band` into `protocol_snapshots`. Add `GET /api/protocols/{slug}/risk-history` + small line chart.                                                                                                                                                         |
| 5 | **Export PDF/CSV briefs**                                 | Med      | M      | briefs            | `routers/briefs.py`, new export util                                    | `GET /api/briefs/{slug}?format=pdf-or-csv`. Client-ready deliverable.                                                                                                                                                                                                                       |

### Tier 2 — Intelligence upgrades


| #  | Feature                                                      | Impact   | Effort | Depends on | Files touched                           | Implementation notes                                                                                                                                                                                        |
| -- | ------------------------------------------------------------ | -------- | ------ | ---------- | --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 6  | **Anomaly detection (EWMA / z-score / CUSUM changepoints)**  | High     | M      | #1         | `metrics.py`, `alerts.py`, `config.py`  | Replace static`alert_tvl_drop_pct` with adaptive detectors; a 15% drop means different things for Lido vs. a $500K pool.                                                                                    |
| 7  | **De-risk the security model (externalize + incident feed)** | Med      | M      | —         | `scoring.py`, new data file / client    | `KNOWN_SECURITY_NOTES` is a hardcoded dict that won't scale past ~16 protocols. Move to a data file; add DefiLlama audit metadata + a curated incident feed so it works for any discovered protocol.        |
| 8  | **"Ask the analyst" RAG chat + streaming briefs**            | Med-High | L      | briefs     | new`routers/chat.py`, vector store, web | pgvector over`docs/methodology.md` + audit summaries + evidence pack. Grounded Q&A with citations + a "cannot establish" guardrail. Stream over **WebSocket** (Cloudflare quick tunnels don't support SSE). |
| 9  | **Explainability "what-if" (live weight/threshold sliders)** | Med      | M      | scoring    | `routers/protocols.py`, web             | Expose`GET /api/protocols/{slug}/score?weights=...`; re-score client-side. Turns the score into a defensible conversation.                                                                                  |
| 10 | **Cross-protocol correlation / contagion**                   | Med      | M      | #1         | `metrics.py`, dashboard                 | Cluster by shared chains + category to flag correlated "one chain, many protocols" exposure.                                                                                                                |

### Tier 3 — Product & UX (build when real users exist)


| #  | Feature                                       | Impact  | Effort | Depends on     | Files touched                             | Implementation notes                                                 |
| -- | --------------------------------------------- | ------- | ------ | -------------- | ----------------------------------------- | -------------------------------------------------------------------- |
| 11 | **Command-palette search (`cmdk`)**           | Med     | S      | —             | web                                       | Search the whole DefiLlama directory, not just the watchlist.        |
| 12 | **Side-by-side comparison view**              | Med     | M      | —             | web,`routers`                             | Pick 2–3 protocols; the "Aave vs Uniswap" story.                    |
| 13 | **URL-encoded shareable filters (`nuqs`)**    | Low-Med | S      | —             | web                                       | A sorted/filtered board becomes a shareable link.                    |
| 14 | **User watchlists & annotations**             | Med     | L      | auth (Batch 0) | `db.py`, new `routers/watchlists.py`, web | Persist custom watchlists, notes, per-user thresholds (Postgres).    |
| 15 | **Virtualized data grid (TanStack Table v8)** | Med     | M      | —             | web                                       | Render the full ~5000-protocol market, not 50 rows.                  |
| 16 | **Sector / TVL-over-time market index view**  | Med     | M      | —             | web, dashboard                            | L2beat-style category breakdown + a "market health" index over time. |

### Tier 4 — Platform & production-readiness (build when scale demands)


| #  | Feature                                               | Impact          | Effort | Depends on | Files touched                     | Implementation notes                                                                                                                                                     |
| -- | ----------------------------------------------------- | --------------- | ------ | ---------- | --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 17 | **Auth + rate limiting (MUST-FIX)**                   | High (security) | M      | —         | `main.py`, `config.py`, `routers` | `POST /api/alerts/run` is an expensive admin-shaped crawl with **no auth**. Add API-key/OIDC (Auth.js/Clerk) to mutating + admin routes; add `slowapi`/edge rate limits. |
| 18 | **Move off the in-process scheduler**                 | Med-High        | L      | —         | `main.py`, new worker             | APScheduler + in-process LRU can't scale horizontally. Push crawls + brief gen to a Redis-backed queue (arq/Celery); store raw payloads; add retention.                  |
| 19 | **Observability (OTel /metrics / Sentry)**            | Med             | M      | —         | `main.py`, `config.py`            | OpenTelemetry traces, Prometheus`/metrics`, structured JSON logs, request IDs, Sentry. Builds on existing liveness/readiness probes.                                     |
| 20 | **Caching layer (Redis + HTTP ETag)**                 | Med             | M      | #18        | `clients`, web proxy              | `ETag`/`Cache-Control`/`If-None-Match` on the Next→API boundary; cheaper vs. the 6h `STALE_AFTER` re-crawl.                                                             |
| 21 | **LLM brief provenance/versioning**                   | Med             | S-M    | briefs     | `db.py`, `services/briefs.py`     | Persist model name, prompt version, and evidence-pack hash per brief → "can I defend this number?" becomes literally auditable.                                         |
| 22 | **Testing upgrades (hypothesis / golden-file / e2e)** | Med             | M      | —         | `tests/`, `e2e/`                  | Property tests for`metrics.py`, golden-file tests for briefs, expand Playwright (comparison, export, alert toggles).                                                     |

---

## 3. Suggested build order (dependency-driven batches)

- **Batch 0 — safety first:** #17 (auth + rate limit). Do before sharing more.
- **Batch 1 — data expansion (highest leverage; downstream depends on it):** #1 fees/volume, #2 depeg, #4 risk-history.
- **Batch 2 — intelligence + delivery:** #6 anomaly detection, #3 alert delivery, #7 security model.
- **Batch 3 — product polish:** #11, #12, #13, #5, #15, #16.
- **Batch 4 — platform/scale:** #18, #19, #20, #8, #9, #14, #21, #22.

### If you only do three things

1. #1 Fees + volume — kills the most-repeated data gap; makes the risk score real.
2. #3 Alert delivery + #2 depeg watch — turns a passive dashboard into an active monitoring product.
3. #17 Auth + #18 async crawl — safe and scale-able enough to actually share.

---

## 4. Decision log (fill this in)

Mark the items we should add, and any ordering preferences.

- [X]  #1 Fees + revenue + volume
- [X]  #2 Stablecoin depeg watch
- [X]  #3 Alert delivery
- [X]  #4 Historical risk-score trend
- [X]  #5 Export PDF/CSV
- [X]  #6 Anomaly detection
- [X]  #7 Security model rework
- [X]  #8 "Ask the analyst" RAG chat
- [X]  #9 What-if scoring
- [X]  #10 Correlation / contagion
- [X]  #11 Command-palette search
- [X]  #12 Comparison view
- [X]  #13 Shareable filters
- [X]  #14 User watchlists & annotations
- [X]  #15 Virtualized data grid
- [X]  #16 Sector / market index
- [ ]  #17 Auth + rate limiting (recommended regardless)
- [X]  #18 Async job queue
- [X]  #19 Observability
- [X]  #20 Caching layer
- [X]  #21 LLM provenance
- [X]  #22 Testing upgrades

Notes / choices:
----------------

## 4b. Build status (verified against the code, 2026-10-29)

The checkboxes above are **selections**, not shipping state. Grounded in the
actual repo:

- **Shipped:** #1 fees + revenue + DEX volume (and the `real_yield_dependence`
  indicator), #2 stablecoin depeg watch (`depeg_exposure` indicator + `depeg`
  alert), #3 alert delivery (console/webhook/slack/discord/telegram/email),
  #4 risk-score history (`/risk-history` + `RiskTrendChart`), #5 PDF/CSV/Markdown
  export, #8 "Ask the analyst" RAG chat with WebSocket streaming, #12 comparison
  view (`/compare`).
- **Partial:** #7 security model is still a hardcoded `KNOWN_SECURITY_NOTES` dict
  (not yet externalized to a data file / incident feed); #22 has Vitest +
  Playwright + respx wired, but no property-based or golden-file tests yet.
- **Selected but not yet built:** #6 anomaly detection (rules still use static
  thresholds), #9 what-if weight sliders, #10 correlation/contagion, #11 command
  palette, #13 shareable board filters (only `/compare` encodes its selection in
  the URL), #14 user watchlists (depends on auth), #15 virtualized grid, #18 async
  job queue (still in-process APScheduler), #19 observability (only `/api/health`
  + `/api/health/ready` exist today), #20 Redis/ETag caching (in-process TTL only),
  #21 LLM brief provenance/versioning.
- **Not selected (recommended regardless):** #17 auth + rate limiting — required
  before any public deploy, since `POST /api/alerts/run` is an unauthenticated
  crawl.

---

## 5. Open questions before building

1. **Batch scope to start:** confirm Batch 0 + Batch 1 as the first shippable
   increment, or reprioritize.
2. **LLM key:** is `OPENAI_API_KEY` configured (drives whether new indicators
   also flow into the brief prompt vs. template-only fallback)?
3. **New data-source keys:** fees/volume/stablecoins come from DefiLlama (no
   key); on-chain activity (Dune) and richer audit data would need keys/accounts.
4. **Auth provider** for #17/#14: API keys only, or full accounts (Auth.js/Clerk)?
