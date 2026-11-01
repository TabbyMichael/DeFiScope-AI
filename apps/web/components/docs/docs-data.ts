/* ===========================================================================
   Docs reference data.
   ---------------------------------------------------------------------------
   One plain-data module, importable by both the server sections and the client
   rails, so the left navigation, the right "on this page" rail and the body
   cannot drift out of agreement about what exists or which id each part carries.

   Two rules, inherited from the About page this manual is built beside:

   1. Every figure is traceable to code or `docs/`. Weights come from
      `analysis/scoring.py`, thresholds from `config.py` + `services/alerts.py`,
      the verb set from `security/rbac.py`, the policies from
      `security/policy.py`, the pipeline from `main.py`. Nothing here is a
      capability invented for a page.
   2. A missing value is `n/a`, never a zero and never an em dash.
   ========================================================================= */

/** One section in the rail: a stable id, its number, and the label shown. */
export type DocsLink = { readonly n: number; readonly id: string; readonly label: string };

/** A rail group, headed by a short uppercase title. */
export type DocsGroup = { readonly title: string; readonly links: readonly DocsLink[] };

/** Subheads inside one section, listed in the right-hand "on this page" rail. */
export type DocsSub = { readonly href: string; readonly label: string };

/* ------------------------------------------------------------------ the rail
   The order here IS the reading order of the page; the body renders its sections
   in the same sequence and carries the same ids. The numbers are load-bearing:
   the prose refers to "section 8" the way a printed manual does. */
export const DOCS_GROUPS: readonly DocsGroup[] = [
  {
    title: "Start here",
    links: [
      { n: 1, id: "overview", label: "What DeFiScope measures" },
      { n: 2, id: "getting-started", label: "Run the stack" },
      { n: 3, id: "tour", label: "The five-minute tour" },
    ],
  },
  {
    title: "How a score is built",
    links: [
      { n: 4, id: "architecture", label: "System architecture" },
      { n: 5, id: "data-sources", label: "Data sources" },
      { n: 6, id: "metrics", label: "Metric primitives" },
      { n: 7, id: "scoring", label: "The seven indicators" },
      { n: 8, id: "bands", label: "Bands and the composite" },
    ],
  },
  {
    title: "Monitoring and research",
    links: [
      { n: 9, id: "rules", label: "Alert rules" },
      { n: 10, id: "delivery", label: "Delivery channels" },
      { n: 11, id: "onchain", label: "On-chain evidence" },
      { n: 12, id: "ask", label: "Ask the analyst" },
      { n: 13, id: "briefs", label: "Research briefs" },
    ],
  },
  {
    title: "Reference",
    links: [
      { n: 14, id: "api", label: "API reference" },
      { n: 15, id: "auth", label: "Access model" },
      { n: 16, id: "config", label: "Configuration" },
      { n: 17, id: "limits", label: "Limitations" },
      { n: 18, id: "glossary", label: "Glossary" },
    ],
  },
] as const;

/** Flat list, in reading order, for the scroll observer and prev/next logic. */
export const DOCS_SECTIONS: readonly DocsLink[] = DOCS_GROUPS.flatMap((g) => g.links);

/** Subheads per section id, for the right rail. Only the active section's list shows. */
export const DOCS_SUBHEADS: Readonly<Record<string, readonly DocsSub[]>> = {
  overview: [
    { href: "overview-in-one-line", label: "In one line" },
    { href: "overview-what-it-is-not", label: "What it is not" },
  ],
  "getting-started": [
    { href: "start-requirements", label: "What you need" },
    { href: "start-compose", label: "Start with Docker" },
    { href: "start-local", label: "Run it from source" },
    { href: "start-env", label: "Optional keys" },
  ],
  tour: [
    { href: "tour-board", label: "The board" },
    { href: "tour-protocol", label: "A protocol" },
    { href: "tour-alerts", label: "Alerts" },
    { href: "tour-ask", label: "Ask" },
  ],
  architecture: [
    { href: "arch-services", label: "Three services" },
    { href: "arch-pipeline", label: "The pipeline" },
    { href: "arch-reads", label: "How a read is served" },
  ],
  "data-sources": [
    { href: "sources-table", label: "Source by source" },
    { href: "sources-normalise", label: "Normalization" },
    { href: "sources-gaps", label: "Gaps, never zeros" },
  ],
  metrics: [
    { href: "metrics-list", label: "The primitives" },
    { href: "metrics-purity", label: "Pure and tested" },
  ],
  scoring: [
    { href: "scoring-weights", label: "Weights" },
    { href: "scoring-anchors", label: "Anchors and limitations" },
  ],
  bands: [{ href: "bands-table", label: "The four bands" }],
  rules: [
    { href: "rules-table", label: "The six rules" },
    { href: "rules-idempotency", label: "Idempotent per day" },
  ],
  delivery: [{ href: "delivery-channels", label: "Channels and their gates" }],
  onchain: [
    { href: "onchain-fields", label: "The four metrics" },
    { href: "onchain-status", label: "Five states of a number" },
    { href: "onchain-calibration", label: "Why it is not scored" },
  ],
  ask: [
    { href: "ask-retrieval", label: "How retrieval works" },
    { href: "ask-refusal", label: "The three outcomes" },
  ],
  briefs: [{ href: "brief-confidence", label: "Confidence and the export gate" }],
  api: [
    { href: "api-conventions", label: "Conventions" },
    { href: "api-endpoints", label: "Endpoints" },
    { href: "api-errors", label: "Errors and denials" },
  ],
  auth: [
    { href: "auth-roles", label: "Roles" },
    { href: "auth-abac", label: "Attribute policies" },
    { href: "auth-modes", label: "Auth modes" },
  ],
  config: [{ href: "config-env", label: "Environment variables" }],
  limits: [{ href: "limits-list", label: "What DeFiScope will not claim" }],
  glossary: [],
};

/* ----------------------------------------------------------- indicator matrix
   Straight from `app/analysis/scoring.py`. `weight` sums to 1.00 across all
   seven; `anchor` is the safe-to-risky span the raw value is mapped onto;
   `cannot` is the limitation the indicator ships with, quoted in spirit from the
   code's own `limitation` string. This is the column the whole exercise exists
   to make readable. */
export type Indicator = {
  readonly name: string;
  readonly key: string;
  readonly weight: string;
  readonly anchor: string;
  readonly cannot: string;
};

export const INDICATORS: readonly Indicator[] = [
  {
    name: "Stablecoin peg integrity",
    key: "depeg_exposure",
    weight: "0.20",
    anchor: "5 bps safe to 150 bps risky, worst 30d deviation of a minted coin",
    cannot: "A coin outside the curated map, or whether a recovered excursion is still live. Non-issuers are excluded as a gap, never read as on-peg.",
  },
  {
    name: "Chain and liquidity concentration",
    key: "liquidity_concentration",
    weight: "0.16",
    anchor: "HHI 0.15 safe to 0.95 risky",
    cannot: "The security of the dominant chain itself, or bridge risk. Pseudo chains (staking, pool2, borrowed, composite keys) are filtered before the index.",
  },
  {
    name: "TVL volatility (30d)",
    key: "tvl_volatility",
    weight: "0.16",
    anchor: "0.5% to 10% std-dev of daily returns",
    cannot: "Whether a move is price-driven or usage-driven. USD TVL falls when a token price falls with no change in activity.",
  },
  {
    name: "Security posture",
    key: "security_posture",
    weight: "0.14",
    anchor: "3 or more audits down to 0 audits plus incident notes",
    cannot: "Coverage, recency, or what changed since the last audit. Formal verification and bug bounties are not captured. A prompt for manual review.",
  },
  {
    name: "Real-yield dependence",
    key: "real_yield_dependence",
    weight: "0.14",
    anchor: "1.0% fees/TVL down to 0.02%",
    cannot: "Whether a low ratio is emissions reliance or a capital-efficient store of value. A protocol the fee adapter does not track is a gap, not a low score.",
  },
  {
    name: "TVL trend (7d / 30d)",
    key: "tvl_trend",
    weight: "0.10",
    anchor: "+5% to -40% over 30 days",
    cannot: "Organic growth versus incentive-driven deposits, or decline versus orderly exit. Growth alone is not treated as safe.",
  },
  {
    name: "Incentive and staking dependence",
    key: "incentive_dependence",
    weight: "0.10",
    anchor: "5% to 80% staking share of core TVL",
    cannot: "Mercenary capital versus long-term stakers. A high ratio is an instruction to look, not a verdict.",
  },
] as const;

/* ----------------------------------------------------------------- bands ----
   Composite thresholds from `assess()`: low < 30, moderate < 50, elevated < 70,
   else high. `unknown` is the composite being None because nothing was
   computable. */
export type Band = {
  readonly band: string;
  readonly range: string;
  readonly tone: string;
  readonly meaning: string;
};

export const BANDS: readonly Band[] = [
  { band: "Low", range: "0 to 29", tone: "ds-band-low", meaning: "Nothing measured pushed the composite high." },
  { band: "Moderate", range: "30 to 49", tone: "ds-band-moderate", meaning: "Some indicators lean risky; worth a look." },
  { band: "Elevated", range: "50 to 69", tone: "ds-band-elevated", meaning: "Several signals point the same way." },
  { band: "High", range: "70 to 100", tone: "ds-band-high", meaning: "Strong risk contribution across the board." },
] as const;

/* --------------------------------------------------------------- rules ------
   Thresholds from `config.py`, semantics from `services/alerts.py`. Each alert
   stores the metric, the observed value and the threshold that fired. */
export type Rule = {
  readonly rule: string;
  readonly severity: string;
  readonly trigger: string;
  readonly value: string;
};

export const RULES: readonly Rule[] = [
  { rule: "tvl_drop", severity: "warning, critical at 2x", trigger: "7d TVL change at or below the drop threshold", value: "-15%" },
  { rule: "daily_shock", severity: "critical", trigger: "24h TVL change at or below (possible exploit, depeg or mass exit)", value: "-10%" },
  { rule: "tvl_surge", severity: "info", trigger: "7d TVL change at or above the surge threshold", value: "+30%" },
  { rule: "incentive_dependence", severity: "warning", trigger: "staking divided by core TVL at or above", value: "0.60" },
  { rule: "stale_data", severity: "warning", trigger: "latest DefiLlama observation older than", value: "2 days" },
  { rule: "depeg", severity: "warning, critical at 2x", trigger: "a minted stablecoin off its $1 peg over the 30d window", value: "50 bps" },
] as const;

/* --------------------------------------------------------------- sources ----
   Used for, and the limitation the source carries. Mirrors the data table in
   `docs/methodology.md`, kept to what a reader needs in one pass. */
export type Source = {
  readonly name: string;
  readonly usedFor: string;
  readonly limit: string;
};

export const SOURCES: readonly Source[] = [
  {
    name: "DefiLlama protocols",
    usedFor: "TVL, TVL history, per-chain distribution, staking TVL, category and audit count.",
    limit: "TVL is USD-denominated, so it conflates price with usage. Cross-protocol double counting is possible; audit metadata is self-reported and coarse.",
  },
  {
    name: "DefiLlama fees and revenue",
    usedFor: "Trailing fees and revenue, which feed the real-yield indicator.",
    limit: "Only protocols with a fee adapter are covered. A missing series is a gap, never zero, and fee attribution varies by protocol.",
  },
  {
    name: "DefiLlama DEX volume",
    usedFor: "Trading turnover, shown as volume to TVL.",
    limit: "Only tracked venues report volume, so a non-DEX protocol legitimately has none.",
  },
  {
    name: "DefiLlama coin prices",
    usedFor: "Historical USD prices of the stablecoins a protocol mints, which become peg deviation in basis points.",
    limit: "Only coins with a tracked feed resolve. The series is confidence-weighted, so a brief intraday excursion can register.",
  },
  {
    name: "Curated stablecoin map",
    usedFor: "Which USD-pegged coin each protocol mints or backs.",
    limit: "Hand-curated and deliberately narrow. A protocol minting a coin outside the map is reported as not assessed, never as risk-free.",
  },
  {
    name: "Curated security notes",
    usedFor: "Historical incidents such as Curve's August 2023 Vyper exploit.",
    limit: "Intentionally minimal. A research prompt, not an incident database, and it will never be complete.",
  },
  {
    name: "Dune Analytics",
    usedFor: "Contract-level activity: daily active wallets, transactions, transfer volume and returning wallets.",
    limit: "Counts contract activity, not people. Optional, key-gated, and bounded by a hand-curated slug-to-contract map, so anything outside it is a gap.",
  },
] as const;

/* ---------------------------------------------------------------- metrics ---
   The pure functions in `analysis/metrics.py` the scorer and rules build on. */
export type Metric = { readonly fn: string; readonly formula: string };

export const METRICS: readonly Metric[] = [
  { fn: "pct_change(df, days)", formula: "Percentage change of the latest value over the trailing window; None when the series is too short or the baseline is zero." },
  { fn: "volatility(df, 30d)", formula: "Standard deviation of daily TVL returns over the trailing window, not annualized; None under 5 observations." },
  { fn: "max_drawdown(df, 30d)", formula: "Worst peak-to-trough decline within the window as a negative fraction." },
  { fn: "chain_concentration(shares)", formula: "Herfindahl-Hirschman index over TVL by chain (real chains only); 1 is a single chain, near 0 is diversified." },
  { fn: "incentive_ratio(tvl, staking)", formula: "Latest staking and LP-rewards TVL divided by core TVL; None when no staking series exists." },
  { fn: "fees_tvl_ratio(fees, tvl)", formula: "Trailing-30d fees as a fraction of current TVL (capital efficiency); None when either side is missing." },
  { fn: "price_normalized_tvl(tvl, price)", formula: "TVL change after dividing out the token price, separating usage from price; None when either series is too short." },
  { fn: "max_peg_deviation_bps(prices)", formula: "Worst absolute deviation from a $1 peg over the window, in basis points; None when no valid price exists." },
  { fn: "depeg_duration(prices, tol)", formula: "Count of observations beyond the tolerance; None when there is no valid data, 0 when the peg held throughout." },
  { fn: "data_freshness_days(df)", formula: "Days between the latest observation and now (UTC)." },
] as const;

/* ------------------------------------------------------------- on-chain -----
   Fields from `data/dune/onchain_activity.sql` and `services/onchain.py`, plus
   the five statuses that make a missing number mean something specific. */
export type OnchainField = { readonly term: string; readonly def: string };

export const ONCHAIN_FIELDS: readonly OnchainField[] = [
  { term: "active_wallets", def: "Distinct transaction senders that touched a tracked contract at least once that day." },
  { term: "tx_count", def: "Successful transactions sent to the tracked contract set." },
  { term: "tx_volume_usd", def: "Sum of token transfer value whose recipient is a tracked contract. Inbound legs only, so it is not DEX volume and must not be compared with it." },
  { term: "returning_wallets", def: "Active wallets seen on an earlier day within the lookback window; the share is returning divided by active." },
] as const;

export type OnchainStatus = { readonly status: string; readonly meaning: string };

export const ONCHAIN_STATUSES: readonly OnchainStatus[] = [
  { status: "ok", meaning: "Every mapped chain reported for the newest day." },
  { status: "partial", meaning: "The newest day is missing one of the mapped chains." },
  { status: "stale", meaning: "Rows exist but the newest one is older than the alert window." },
  { status: "no_data", meaning: "Configured, but no curated mapping or no rows captured yet." },
  { status: "unconfigured", meaning: "No key or no query id, so nothing can be measured." },
] as const;

/* ---------------------------------------------------------------- channels --
   Notifiers in `app/notifiers/`. Each activates only when its secret is set. */
export type Channel = { readonly name: string; readonly activates: string };

export const CHANNELS: readonly Channel[] = [
  { name: "console", activates: "Always on; the reference sink for a run with no secrets." },
  { name: "webhook", activates: "A URL is configured; format is generic, slack or discord." },
  { name: "slack", activates: "SLACK_WEBHOOK_URL is set." },
  { name: "discord", activates: "DISCORD_WEBHOOK_URL is set." },
  { name: "telegram", activates: "A bot token and a chat id are both set." },
  { name: "email", activates: "SMTP host, credentials and from and to addresses are set." },
] as const;

/* --------------------------------------------------------------- endpoints --
   The HTTP surface from `app/routers/` and `main.py`. `auth` is the verb from
   `security/rbac.py`, or "public" for the two health probes and `/api/status`. */
export type Endpoint = {
  readonly method: string;
  readonly path: string;
  readonly auth: string;
  readonly what: string;
};

export const ENDPOINTS: readonly Endpoint[] = [
  { method: "GET", path: "/api/health", auth: "public", what: "Liveness probe plus the database state; always 200." },
  { method: "GET", path: "/api/health/ready", auth: "public", what: "Readiness probe; 503 until the database answers." },
  { method: "GET", path: "/api/status", auth: "public", what: "Aggregate coverage: protocols, days, bands, alerts, index counts." },
  { method: "POST", path: "/api/auth/login", auth: "credentials", what: "Exchange an email and password for the session cookie." },
  { method: "POST", path: "/api/auth/logout", auth: "session", what: "Clear the session cookie." },
  { method: "GET", path: "/api/auth/me", auth: "session", what: "The current subject: role, clearance and scope." },
  { method: "POST", path: "/api/auth/switch", auth: "session, demo only", what: "Become another seeded account without a password, to see a policy fire." },
  { method: "POST", path: "/api/auth/ticket", auth: "chat:ask", what: "Mint a single-use WebSocket ticket for the streamed answer." },
  { method: "GET", path: "/api/protocols", auth: "protocols:read", what: "The watchlist as overviews, narrowed to the subject's scope." },
  { method: "GET", path: "/api/protocols/{slug}", auth: "protocols:read", what: "Full research pack for one protocol, with evidence and gaps." },
  { method: "GET", path: "/api/dashboard", auth: "protocols:read", what: "The board: latest snapshot per protocol plus stats and movers, DB-first." },
  { method: "GET", path: "/api/protocols/{slug}/history", auth: "protocols:read", what: "Daily TVL series for one protocol." },
  { method: "GET", path: "/api/protocols/{slug}/risk-history", auth: "protocols:read", what: "Daily composite risk-score trend for one protocol." },
  { method: "GET", path: "/api/alerts", auth: "alerts:read", what: "Today's alerts; withheld critical rows are counted, not hidden." },
  { method: "GET", path: "/api/alerts/history", auth: "alerts:read", what: "The persisted alert log, newest first." },
  { method: "POST", path: "/api/alerts/run", auth: "monitor:run", what: "Trigger a monitoring pass, gated on freshness and business hours." },
  { method: "GET", path: "/api/briefs/{slug}", auth: "briefs:read", what: "A grounded research brief for one protocol." },
  { method: "GET", path: "/api/briefs/{slug}/export", auth: "briefs:export", what: "Render a brief as markdown, CSV or PDF; low confidence refuses to leave unsigned." },
  { method: "POST", path: "/api/chat", auth: "chat:ask", what: "Grounded Q&A over the docs and the protocol's own evidence." },
  { method: "WS", path: "/ws/chat", auth: "chat:ask ticket", what: "Streamed token, citation and done frames for the same answer." },
] as const;

/* ------------------------------------------------------------------ roles ---
   `security/rbac.py`: a role grants verbs; the ABAC layer decides which records
   those verbs reach. */
export type Role = { readonly role: string; readonly verbs: string };

export const ROLES: readonly Role[] = [
  { role: "viewer", verbs: "protocols:read, alerts:read, briefs:read, chat:ask. Looks; cannot export or spend compute." },
  { role: "analyst", verbs: "viewer plus briefs:export and monitor:run." },
  { role: "risk_officer", verbs: "analyst plus audit:read. May sign off a low-confidence export." },
  { role: "admin", verbs: "every verb, including users:manage and policy:manage, and the escape hatch on the monitor gates." },
] as const;

/* ------------------------------------------------------------- ABAC policies
   `security/policy.py`. Each has a stable id that doubles as the `policy` field
   on a denial, so a doc line and a log line name the same rule. */
export type Policy = { readonly id: string; readonly fires: string; readonly shape: string };

export const POLICIES: readonly Policy[] = [
  { id: "scope.category_chain", fires: "A resource is outside the subject's category or chain scope.", shape: "Filtered list, or a 403 on a detail read naming the failing axis." },
  { id: "alerts.severity_clearance", fires: "A critical alert and the subject's clearance is below 2.", shape: "Content withheld, count kept, so the feed never reads as empty when it is not." },
  { id: "briefs.export.confidence_gate", fires: "A low-confidence brief is exported by a role that is not risk_officer or admin.", shape: "403 naming the gap count; the read itself stays allowed." },
  { id: "monitor.run.freshness", fires: "A manual pass when the newest snapshot is still fresh.", shape: "403 with the age in hours; admins may always force one." },
  { id: "monitor.run.business_hours", fires: "A manual pass outside weekday 07:00 to 22:00 server time.", shape: "403 with the window; admins are exempt." },
] as const;

/* ------------------------------------------------------------------- env ----
   Selected from `config.py`. Names carry the DEFISCOPE_ prefix; the default is
   what the code falls back to when the variable is absent. `secret` marks the
   values that must never be published to the browser. */
export type EnvVar = { readonly name: string; readonly def: string; readonly note: string; readonly secret?: boolean };

export const ENV_VARS: readonly EnvVar[] = [
  { name: "DEFISCOPE_DATABASE_URL", def: "sqlite:///./defiscope.db", note: "Postgres in compose; SQLite for dev and tests." },
  { name: "DEFISCOPE_AUTH_MODE", def: "demo", note: "off (no auth, showcase only), demo (seeded logins), required (login, no seeds)." },
  { name: "DEFISCOPE_AUTH_SESSION_HOURS", def: "12", note: "Lifetime of the session cookie." },
  { name: "DEFISCOPE_MONITOR_INTERVAL_MINUTES", def: "30", note: "How often the scheduler re-scores the watchlist; published at /api/status." },
  { name: "DEFISCOPE_DEFAULT_PROTOCOLS", def: "16 curated slugs", note: "Always tracked on top of auto-discovery." },
  { name: "DEFISCOPE_MARKET_TOP_N", def: "50", note: "Auto-discover the top N by TVL from the directory; 0 disables." },
  { name: "DEFISCOPE_ALERT_TVL_DROP_PCT", def: "-15.0", note: "tvl_drop threshold." },
  { name: "DEFISCOPE_ALERT_TVL_SURGE_PCT", def: "30.0", note: "tvl_surge threshold." },
  { name: "DEFISCOPE_ALERT_STAKING_RATIO", def: "0.60", note: "incentive_dependence threshold." },
  { name: "DEFISCOPE_ALERT_STALE_DATA_DAYS", def: "2", note: "stale_data threshold." },
  { name: "DEFISCOPE_ALERT_DEPEG_BPS", def: "50.0", note: "depeg threshold." },
  { name: "DEFISCOPE_OPENAI_API_KEY", def: "(unset)", note: "Optional. Without it, briefs and chat use the template and lexical fallback.", secret: true },
  { name: "DEFISCOPE_DUNE_API_KEY", def: "(unset)", note: "Optional second provider. On-chain stays a gap until both this and the query id exist.", secret: true },
  { name: "DEFISCOPE_DUNE_ACTIVITY_QUERY_ID", def: "(unset)", note: "Id of the saved query returning all four activity metrics.", secret: true },
  { name: "DEFISCOPE_ALERT_NOTIFY_CHANNELS", def: "console,webhook", note: "Delivery sinks; each activates on its own secret." },
];

/* ---------------------------------------------------------------- glossary --
   Terms the product uses that a reader meets for the first time on this page.
   Definitions stay in the product's own words. */
export type Term = { readonly term: string; readonly def: string };

export const GLOSSARY: readonly Term[] = [
  { term: "Composite score", def: "A single 0 to 100 figure, the weighted mean of the indicators that could be computed. Higher means more risk contribution." },
  { term: "Band", def: "The label on a composite: low, moderate, elevated or high, at the 30, 50 and 70 cut-offs. unknown when nothing was computable." },
  { term: "Indicator", def: "One weighted signal (peg, concentration, volatility, and so on) that carries its own value, score, evidence and limitation." },
  { term: "Data gap", def: "An indicator that could not be computed. It leaves the composite and is listed under data_gaps, never counted as safe." },
  { term: "HHI", def: "Herfindahl-Hirschman index: the sum of squared chain shares. 1 is one chain, near 0 is evenly spread." },
  { term: "Basis point (bps)", def: "One hundredth of a percent. 50 bps of a $1 peg is $0.995 or $1.005." },
  { term: "TVL", def: "Total value locked, as USD. It moves with price as well as with usage, which is the core caveat on every TVL-derived indicator." },
  { term: "Real yield", def: "Fee revenue rather than token emissions. Proxied here by fees relative to TVL." },
  { term: "Watchlist", def: "The set the monitor evaluates: the curated slugs plus the auto-discovered top of the market, minus excluded categories and slugs." },
  { term: "Snapshot", def: "One protocol's normalized observation for one day, stored so the board reads from the database rather than a live crawl." },
  { term: "Clearance", def: "An integer attribute on a subject. Critical alert content needs level 2." },
  { term: "Scope", def: "The category and chain axes a subject may see. A restricted axis denies an unknown attribute." },
  { term: "Withheld count", def: "How many alert rows a clearance gate removed. Shown so a filtered feed is never mistaken for an empty one." },
  { term: "Confidence gate", def: "The policy that lets a low-confidence brief be read but not exported without sign-off." },
  { term: "n/a", def: "The placeholder for a value that could not be measured. Distinct from 0, which means measured and none." },
] as const;

/** Format a possibly-null aggregate count as a display string. null is n/a. */
export function fmtCount(value: number | null | undefined): string {
  return value == null ? "n/a" : value.toLocaleString("en-US");
}
