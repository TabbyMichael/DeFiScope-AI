# Research Methodology

This document defines exactly how DeFiScope AI computes every number it displays,
what each metric can and cannot establish, and where human judgment is required.
It is the contract between the dashboard and the analyst.

## Data sources

| Source | Used for | Known limitations |
|---|---|---|
| [DefiLlama](https://api.llama.fi) (`/protocols`, `/protocol/{slug}`) | TVL, TVL history, chain distribution, staking TVL, category, audit count | TVL is USD-denominated, so it conflates price movement with usage. Cross-protocol double counting (e.g. wrapped assets) is possible. Audit metadata is self-reported and coarse. |
| [DefiLlama fees](https://fees.llama.fi) (`/summary/fees/{slug}`) | Trailing fees & revenue (`dailyFees` / `dailyRevenue`) | Only protocols with a fees adapter are covered; a missing series is a data gap, never zero. Fee attribution (who captures it) varies per protocol. |
| [DefiLlama DEX volume](https://api.llama.fi) (`/overview/dexs/{slug}`) | Trading volume (turnover) | Only tracked venues report volume; non-DEX protocols legitimately have none (a gap, not inactivity). |
| [DefiLlama coin prices](https://coins.llama.fi) (`/chart/{coins}`) | Historical USD prices of a protocol's minted stablecoins → peg deviation | Only coins with a tracked price feed resolve; a mapped coin without history is a data gap. Confidence-weighted, so brief intraday excursions can register. |
| Curated stablecoin map (`data/protocol_stablecoins.json`) | Which USD-pegged coin(s) each protocol mints/backs | Hand-curated and deliberately narrow; a protocol minting a coin outside the map is reported as "not assessed", never risk-free. |
| Curated security notes (`app/analysis/scoring.py::KNOWN_SECURITY_NOTES`) | Historical incidents (e.g. Curve's Aug 2023 Vyper exploit) | Intentionally minimal; a research prompt, not an incident database. |

All outputs carry an `as_of` date (timestamp of the latest underlying observation)
and source links. The API refuses to silently present stale data: freshness is a
first-class field and a monitoring rule.

## Metric primitives (`app/analysis/metrics.py`)

Raw DefiLlama point series are normalized to a **daily, forward-filled UTC frame**.
Duplicate intraday points are aggregated with `max` (DefiLlama issues retro
corrections). Forward-filling never fabricates values before the first observation.

- **TVL change (7d / 30d)**: `(latest - value_n_days_ago) / value_n_days_ago`.
  Returns `None` (never a guess) when history is insufficient or the baseline is zero.
- **Volatility (30d)**: standard deviation of daily TVL returns over the trailing
  30 days, requiring ≥5 observations.
- **Max drawdown (30d)**: worst peak-to-trough decline within the window.
- **Chain concentration**: Herfindahl-Hirschman Index (HHI) over per-chain TVL
  shares. DefiLlama's pseudo-chains (`staking`, `pool2`, `borrowed`, and composite
  keys like `Ethereum-staking`) are excluded — this is a common silent error in
  TVL dashboards and we filter it explicitly (and test it).
- **Incentive ratio**: latest staking/LP-rewards TVL ÷ core TVL.
- **Fees / TVL and Volume / TVL**: trailing fee and volume totals ÷ current TVL
  (capital-efficiency ratios). `None` when either side is missing or TVL ≤ 0, so an
  untracked feed stays a gap rather than reading as 0.
- **Price-normalized TVL**: trailing TVL change after dividing out the token's own
  price (`(T₁/P₁) ÷ (T₀/P₀) − 1`), separating usage from price. Pure/tested and
  ready, but not yet wired to a per-protocol token mapping — until that mapping is
  reliable it is intentionally not shown rather than approximated.
- **Peg deviation (bps)**: for a USD-pegged coin, `(price − 1) / 1 × 10 000`.
  `max_peg_deviation_bps` is the worst absolute deviation over the window and
  `depeg_duration` counts observations beyond a ±tolerance band. Both return `None`
  (a gap) when there is no valid price — never read as "on peg".
- **Data freshness**: days between the last observation and now.

Every primitive is covered by unit tests (`tests/test_metrics.py`).

## Risk indicators (`app/analysis/scoring.py`)

Each indicator produces `{value, score 0–100, weight, evidence, limitation}`
where **100 = maximum risk contribution**. Scores are linear maps between a
"safe" and "risky" anchor value, clamped to [0, 100]. Anchors are documented
judgment calls, not market truth:

| Indicator | Weight | Anchor: safe → risky | What it CANNOT establish |
|---|---|---|---|
| Chain / liquidity concentration (HHI) | 0.16 | 0.15 → 0.95 | Security of the dominant chain itself; bridge risk between chains |
| TVL volatility (30d std-dev of daily returns) | 0.16 | 0.5% → 10% | Whether moves are price-driven vs usage-driven |
| TVL trend (30d change) | 0.10 | +5% → −40% | Organic vs incentive-driven flows (see below) |
| Incentive dependence (staking/core TVL) | 0.10 | 5% → 80% | Mercenary vs long-term stakers (Lido's ratio is high by design) |
| Security posture (audit count + curated notes) | 0.14 | 3+ audits → 0 audits + incident history | Coverage, recency, or post-audit upgrades. Never a safety guarantee |
| Real-yield dependence (30d fees / TVL) | 0.14 | 1.0% → 0.02% (higher fee/TVL = safer) | Whether low yield is emissions-reliance vs a capital-efficient store of value (LSTs, stablecoins) or untracked fee revenue. Missing fees = data gap, never scored safe |
| Stablecoin peg integrity (worst 30d deviation of minted coins) | 0.20 | 5 bps → 150 bps (higher deviation = riskier) | Whether a coin outside the curated map is depegged; a since-recovered excursion still registers. Non-issuers and issuers without price history are excluded as a gap, never read as on-peg |

Weights sum to 1.0 across the seven indicators. `depeg_exposure` carries the
highest single weight because a peg loss is the most direct solvency event for a
stablecoin issuer, but it renormalizes out for the many protocols that mint no
tracked coin, so it does not distort their composites.

**Composite score** = weighted mean over *available* indicators, renormalized so
missing data does not count as "safe". If any indicator is not computable it is
reported under `data_gaps`. Bands: `low` <30 ≤ `moderate` <50 ≤ `elevated` <70 ≤ `high`.

### The central analytical caveat

> Rising or falling TVL, by itself, proves nothing about sustainable growth or
> protocol risk. Token prices, market conditions, incentive emissions, and
> one-time whale movements all move USD TVL. DeFiScope therefore never labels a
> protocol "healthy" because TVL rose; it flags the *reason to investigate*
> (e.g. a TVL surge triggers an "verify incentive-driven" alert). The real-yield
> indicator now brings fees, revenue and DEX volume to bear on that question, but
> those adapters cover only tracked protocols — where they are absent the missing
> evidence is still surfaced in the data-gaps section of every brief rather than
> guessed.

## Research briefs (`app/services/briefs.py`)

Briefs are generated from the structured evidence pack only — the LLM path is
constrained to provided numbers ("never invent numbers" system instruction, JSON
schema output) and the deterministic template fallback produces the same sections
from the same evidence when no LLM is configured. `generated_by` is always
surfaced so a reader knows which engine wrote the prose. Confidence is downgraded
automatically when data gaps exist.

## Monitoring rules (`app/services/alerts.py`)

| Rule | Default threshold | Severity | Rationale |
|---|---|---|---|
| `tvl_drop` | ≤ −15% over 7d (critical at ≤ −30%) | warning/critical | Sustained outflow is the clearest exit signal in TVL data |
| `daily_shock` | ≤ −10% in 24h | critical | Overnight crashes correlate with exploits/depegs/mass exits |
| `tvl_surge` | ≥ +30% over 7d | info | Growth this fast is usually emissions-backed; verify before believing it |
| `incentive_dependence` | staking/core ≥ 0.60 | warning | Flags emission-driven value for investigation |
| `stale_data` | last observation > 2d old | warning | Upstream collection failure; protects downstream conclusions |
| `depeg` | a minted stablecoin ≥ 50 bps off peg in 30d (critical at ≥ 100 bps) | warning/critical | A peg loss is the clearest solvency signal for a stablecoin issuer; only runs for protocols in the curated map |

Alert IDs are deterministic per protocol/rule/day, so re-runs are idempotent.
Every alert embeds its triggering evidence: metric, observed value, threshold.

## Chat / RAG (`app/rag/`)

"Ask the analyst" answers questions about a protocol or the scoring itself by
retrieving evidence from DeFiScope's own corpus and grounding the answer in it.
It adds no new claims — it only re-states what the dashboard already computed,
with citations.

**Retrieval sources.** Two kinds of chunks are indexed:

- *Documentation*: `methodology.md`, `architecture.md`, `defi-mechanics-primer.md`,
  `sample-research.md`, and the curated security notes — split on heading/paragraph
  boundaries into chunks with provenance (`source_name`, `section`).
- *Evidence packs*: for each tracked protocol, its overview numbers, each risk
  indicator's `evidence` **and** `limitation`, its `data_gaps`, and recent alerts —
  so a "why is Lido flagged?" question retrieves the exact limitation wording, not
  just the headline.

**Ranking.** When an `OPENAI_API_KEY` is configured, chunks are embedded
(`text-embedding-3-small`) and ranked by cosine similarity (pgvector on Postgres,
in-process cosine on SQLite/dev). With **no key** the system falls back to a pure
Python Okapi-BM25 lexical score (k1=1.5, b=0.75) — same store, same top-k, no
external calls. Chunks are content-hashed *with their provenance folded into the
hash* (`doc_id ␟ section ␟ body`), so unchanged text keeps a stable id across
re-indexes while the *same* boilerplate appearing under different sources gets a
distinct id rather than colliding on the primary key.

**Relevance gate (method-aware).** The two retrievers produce scores on
incomparable scales — cosine is bounded `[0, 1]`, BM25 is unbounded (typically
1–20+) — so a single fixed threshold cannot gate both. The gate keys off whichever
path actually ranked the results:

- **Vector path:** a chunk must reach the cosine floor `rag_min_score` (default 0.5).
- **Lexical path:** a raw BM25 floor would be meaningless (one stray common word
  like "like" clears it), so a passage must instead share at least
  `rag_min_query_term_overlap` **distinct informative query terms** (default 2,
  after stopword removal). The requirement is capped by the query's own
  informative-term count, so a terse single-word question still answers on one
  match, while an off-topic question sharing only filler is refused.

Only chunks that clear the bar become *supporting* evidence; if none do, the chat
refuses instead of quoting irrelevant passages.

**Grounding rule (the honesty contract).** The model is instructed to *answer only
from the numbered context, attribute every claim to `[n]`, state what the context
cannot establish, and never invent numbers*. Every response exposes `citations`,
`grounded`, and `generated_by`, so a model answer is never mistaken for verified
fact. Three outcomes exist:

| `generated_by` | When | Meaning for the reader |
|---|---|---|
| `llm` | key present and the call succeeds | Natural-language prose, each claim tied to a `[n]` citation |
| `extractive` | no key, or the LLM call fails | Verbatim quoted passages from the evidence — no synthesis, nothing invented |
| `none` (`grounded=false`) | no retrieved chunk clears the method-aware relevance gate (cosine floor, or the lexical informative-term bar) | A refusal: it names what it cannot establish and lists the missing evidence rather than guessing |

**Limits.** Retrieval quality is bounded by the corpus: the chat can only explain
what the pipeline already measured. It inherits every data source limitation above
(TVL conflates price, missing adapters are gaps, the depeg map is narrow), does not
access live markets or new protocols beyond what is indexed, and never overrides a
`data_gap` with a confident-sounding sentence. It is a window onto the evidence, not
an independent analyst.

## What this system deliberately does NOT claim

- It does not detect wash trading or sybil activity (needs transaction-level data).
- It does not evaluate token emission schedules (not in free DefiLlama endpoints).
- It does not yet price-normalize TVL per protocol: fees/volume are shown, but the
  TVL-vs-price decomposition needs a reliable protocol→token mapping first.
- Its depeg watch covers only the stablecoins in the curated protocol→coin map and
  measures deviation against a $1.00 target; it does not model a coin's collateral
  or redemption mechanics, and a protocol minting an unmapped coin is reported as
  "not assessed", not as peg-safe.
- It does not replace smart-contract audits or incident forensics.
- Its security-posture signal is a weak proxy that prompts manual review.

These boundaries are surfaced in the UI as `data_gaps` rather than hidden.
