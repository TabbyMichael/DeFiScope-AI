import type { Metadata } from "next";
import Link from "next/link";
import {
  Activity,
  BellRing,
  CircleAlert,
  CircleCheck,
  CircleX,
  Compass,
  Database,
  Layers,
  ListChecks,
  Lock,
  MessageSquareText,
  Quote,
  Scale,
  SearchCheck,
  Server,
  ShieldCheck,
  Terminal,
  Workflow,
} from "lucide-react";

import {
  Arrow,
  LandingFooter,
  LandingNav,
  LandingReveal,
} from "@/components/landing/landing-chrome";
import { LandingFilm } from "@/components/landing/landing-film";
import { LINKS } from "@/components/landing/links";

/* ===========================================================================
   The public About page.
   ---------------------------------------------------------------------------
   Two rules govern everything below.

   1. Every claim is traceable to the code or to `docs/`. Weights come from
      `services/api/app/analysis/scoring.py`, rules from `services/alerts.py` and
      `config.py`, the cadence from the scheduler in `main.py`, roles from
      `security/rbac.py`, channels from `app/notifiers/`. Nothing is a
      capability invented for a marketing page, and nothing is rounded up: where
      the tool does not do something, the page says so in its own section.

   2. It stays a server component with no cookie, no header and no API read, so
      it prerenders to static HTML exactly like `/welcome`. That is also why the
      figures are written as literals rather than fetched: a page this public
      should not be able to fail because a backend is cold.
   ========================================================================= */

export const metadata: Metadata = {
  title: {
    absolute: "About: how DeFiScope AI scores protocol risk",
  },
  description:
    "DeFiScope AI in detail: the seven weighted indicators and their anchors, the data behind them and what it cannot establish, the monitoring rules, the architecture, the access model, the honest limits and the questions we are asked most.",
  openGraph: {
    title: "About DeFiScope AI: methodology, data and limits",
    description:
      "Seven weighted indicators, six monitoring rules, two data providers and one rule: a missing feed stays a gap, never a reassuring zero.",
    type: "article",
  },
};

/* ------------------------------------------------------------------ the chips
   A table of contents for a long page, built from the section ids below. */
const CHAPTERS = [
  { href: "#mission", label: "Mission" },
  { href: "#methodology", label: "Methodology" },
  { href: "#data", label: "Data sources" },
  { href: "#onchain", label: "On-chain evidence" },
  { href: "#research", label: "Ask the analyst" },
  { href: "#architecture", label: "Architecture" },
  { href: "#security", label: "Access model" },
  { href: "#limits", label: "Honest limits" },
  { href: "#roadmap", label: "Roadmap" },
  { href: "#faq", label: "FAQ" },
] as const;

/* -------------------------------------------------------------- the headline
   Each figure is a property of the shipped code, not a marketing number:
   seven indicator weights that sum to 1.00, six rules, a 30 minute pass, six
   notifier channels, four roles, three clearance levels, two providers, and
   zero keys required to see the board. */
const STATS = [
  {
    value: "7",
    label: "weighted indicators",
    note: "Their weights sum to 1.00. No single number decides a band.",
  },
  {
    value: "6",
    label: "monitoring rules",
    note: "Each alert stores the metric, the observed value and the threshold.",
  },
  {
    value: "30 min",
    label: "monitor pass",
    note: "Scheduled, and idempotent per protocol, rule and day.",
  },
  {
    value: "6",
    label: "delivery channels",
    note: "Console, webhook, Slack, Discord, Telegram, email. Each activates on its own secret.",
  },
  {
    value: "4 + 3",
    label: "roles and clearance levels",
    note: "RBAC grants verbs. Attributes decide which records those verbs reach.",
  },
  {
    value: "2",
    label: "data providers",
    note: "DefiLlama is the core. Dune is an optional additive layer.",
  },
  {
    value: "0",
    label: "keys required to start",
    note: "DefiLlama is a public API with no signup, so the whole model runs without one.",
  },
  {
    value: "1",
    label: "pure function does the scoring",
    note: "assess() in analysis/scoring.py. No network, no model, no opinion.",
  },
] as const;

const PRINCIPLES = [
  {
    icon: CircleX,
    title: "A gap is never a zero",
    text: "When a feed is missing the field renders n/a and that indicator leaves the composite. The score renormalizes over what could be computed, so unknown data can never read as safe.",
  },
  {
    icon: SearchCheck,
    title: "Every score carries its limitation",
    text: "Each indicator ships with the evidence behind it and a sentence about what it cannot establish. That is not a disclaimer: it is what makes the number readable.",
  },
  {
    icon: CircleAlert,
    title: "A denial is explained, not hidden",
    text: "A refusal names the policy and the failing condition, how many items were withheld and what clearance would unlock them. \"Nothing to show\" and \"you may not see this\" are never the same message.",
  },
  {
    icon: Scale,
    title: "The model writes prose, not numbers",
    text: "Briefs and chat answers are constrained to the evidence pack the pipeline produced. An LLM can phrase a finding; it cannot create one, and its absence changes the wording, never the score.",
  },
] as const;

const FOR_WHOM = [
  {
    icon: Compass,
    title: "Analysts doing due diligence",
    text: "One board for TVL, fees, volume, chain spread and risk bands, then a per-protocol brief with the evidence and the open questions.",
  },
  {
    icon: BellRing,
    title: "Risk desks on the watchlist",
    text: "A scheduled pass flags crashes, one day shocks, suspicious surges, depegs and stale upstream data, and delivers them where your team already looks.",
  },
  {
    icon: Workflow,
    title: "Engineers wiring it in",
    text: "A typed OpenAPI contract, idempotent alert identities, a webhook notifier and a manual run endpoint that respects freshness and business hours.",
  },
  {
    icon: Terminal,
    title: "People who want to read the maths",
    text: "The formulas, anchors, weights and thresholds are documented in the repository and implemented as pure functions with tests behind them.",
  },
] as const;

/* ------------------------------------------------------------------ pipeline
   The six stages between an upstream API and a number on the board. Names are
   taken from the modules that implement them, so a reader can follow a stage
   into the code without a translation layer. */
const PIPELINE = [
  {
    title: "Fetch",
    text: "The DefiLlama protocol packs, the fees and DEX volume adapters and the coin price charts are pulled in. Dune adds four contract level activity metrics, but only when both a key and a saved query id are configured.",
  },
  {
    title: "Normalize",
    text: "Point series become a daily, forward filled UTC frame. Duplicate intraday points aggregate with max because DefiLlama issues retroactive corrections, and forward filling never fabricates a value before the first real observation.",
  },
  {
    title: "Measure",
    text: "Primitive metrics: 7 day and 30 day TVL change, 30 day volatility and max drawdown, chain concentration as a Herfindahl index over real chains, incentive ratio, fees to TVL, volume to TVL, and peg deviation in basis points. Each one returns None instead of guessing.",
  },
  {
    title: "Score",
    text: "Each indicator maps its value onto 0 to 100 between a documented safe anchor and a documented risky anchor, clamped at both ends. 100 means the maximum risk contribution, not the maximum value.",
  },
  {
    title: "Compose",
    text: "The composite is a weighted mean over the available indicators, renormalized so missing data does not count as safe. Bands: low under 30, moderate under 50, elevated under 70, high above. Anything not computable is listed under data_gaps.",
  },
  {
    title: "Monitor and deliver",
    text: "The scheduler runs the rules every 30 minutes. Alert ids are deterministic per protocol, rule and day, so a re run cannot duplicate a finding, and each channel only fires if its credential is set.",
  },
] as const;

/* ----------------------------------------------------------- indicator matrix
   Straight out of app/analysis/scoring.py. The right hand column is the point
   of the whole exercise: a reader should leave this table knowing where each
   number stops being evidence. */
const INDICATORS = [
  {
    name: "Stablecoin peg integrity",
    weight: "0.20",
    anchor: "5 bps to 150 bps worst 30 day deviation",
    cannot:
      "Whether a coin outside the curated map is depegged, or whether an excursion that has since recovered is still live. Non issuers are excluded as a gap, never read as on peg.",
  },
  {
    name: "Chain and liquidity concentration",
    weight: "0.16",
    anchor: "HHI 0.15 to 0.95",
    cannot:
      "The security of the dominant chain itself, or bridge risk between chains. Pseudo chains (staking, pool2, borrowed and composite keys) are filtered out before the index is taken.",
  },
  {
    name: "TVL volatility, 30 day",
    weight: "0.16",
    anchor: "0.5% to 10% std-dev of daily returns",
    cannot:
      "Whether a move is price driven or usage driven. USD TVL falls when a token price falls with no change in activity.",
  },
  {
    name: "Security posture",
    weight: "0.14",
    anchor: "3 or more audits to 0 audits plus incident notes",
    cannot:
      "Coverage, recency, or what changed since the last audit. Formal verification and bug bounties are not captured. It is a prompt for manual contract review.",
  },
  {
    name: "Real yield dependence",
    weight: "0.14",
    anchor: "1.0% fees to TVL down to 0.02%",
    cannot:
      "Whether a low ratio is emissions reliance or a capital efficient store of value such as an LST or a stablecoin. A protocol the fee adapter does not track is a gap, not a low score.",
  },
  {
    name: "TVL trend",
    weight: "0.10",
    anchor: "+5% to -40% over 30 days",
    cannot:
      "Organic growth versus incentive driven deposits, or a decline versus an orderly exit. Sustained contraction is treated as the risk signal; growth alone is not treated as safe.",
  },
  {
    name: "Incentive and staking dependence",
    weight: "0.10",
    anchor: "5% to 80% staking share of core TVL",
    cannot:
      "Mercenary capital versus long term stakers. Lido's ratio is high by design, which is exactly why the flag is an instruction to look, not a verdict.",
  },
] as const;

const BANDS = [
  { band: "Low", range: "0 to 29", tone: "ds-band-low" },
  { band: "Moderate", range: "30 to 49", tone: "ds-band-moderate" },
  { band: "Elevated", range: "50 to 69", tone: "ds-band-elevated" },
  { band: "High", range: "70 to 100", tone: "ds-band-high" },
] as const;

/* ------------------------------------------------------------------- sources
   Used for, and the limitation the source carries. This is the same contract as
   the data table in docs/methodology.md, kept short enough to read here. */
const SOURCES = [
  {
    icon: Database,
    name: "DefiLlama protocols",
    usedFor: "TVL, TVL history, per chain distribution, staking TVL, category and audit count.",
    limit:
      "TVL is USD denominated, so it conflates price with usage. Cross protocol double counting is possible, and audit metadata is self reported and coarse.",
  },
  {
    icon: Activity,
    name: "DefiLlama fees and revenue",
    usedFor: "Trailing fees and revenue, which feed the real yield indicator.",
    limit:
      "Only protocols with a fee adapter are covered. A missing series is a gap, never zero, and fee attribution varies by protocol.",
  },
  {
    icon: Layers,
    name: "DefiLlama DEX volume",
    usedFor: "Trading turnover, shown as volume to TVL.",
    limit:
      "Only tracked venues report volume, so a non DEX protocol legitimately has none.",
  },
  {
    icon: Activity,
    name: "DefiLlama coin prices",
    usedFor: "Historical USD prices of the stablecoins a protocol mints, which become peg deviation in basis points.",
    limit:
      "Only coins with a tracked feed resolve. The series is confidence weighted, so a brief intraday excursion can register.",
  },
  {
    icon: ListChecks,
    name: "Curated stablecoin map",
    usedFor: "Which USD pegged coin each protocol mints or backs.",
    limit:
      "Hand curated and deliberately narrow. A protocol minting a coin outside the map is reported as not assessed, never as risk free.",
  },
  {
    icon: ShieldCheck,
    name: "Curated security notes",
    usedFor: "Historical incidents such as Curve's August 2023 Vyper exploit.",
    limit:
      "Intentionally minimal. It is a research prompt, not an incident database, and it will never be complete.",
  },
  {
    icon: Server,
    name: "Dune Analytics",
    usedFor: "Contract level activity: daily active wallets, transactions, transfer volume and returning wallets.",
    limit:
      "Counts contract activity, not people. Optional, key gated, and bounded by a hand curated slug to contract map, so anything outside it is a gap.",
  },
] as const;

/* --------------------------------------------------------------- on-chain view
   Definitions straight out of data/dune/onchain_activity.sql and
   services/onchain.py, including the two limitations that matter most: these
   numbers count contracts rather than people, and they count inflows only. */
const ONCHAIN_FIELDS = [
  {
    term: "active_wallets",
    def: "Distinct transaction senders that touched a tracked contract at least once that day.",
  },
  {
    term: "tx_count",
    def: "Successful transactions sent to the tracked contract set.",
  },
  {
    term: "tx_volume_usd",
    def: "Sum of token transfer value whose recipient is a tracked contract. Inbound legs only, so it is not volume in the DEX sense and must not be compared with the DefiLlama figure beside it.",
  },
  {
    term: "returning_wallets",
    def: "Of that day's active wallets, the ones also active in the 30 days before it.",
  },
  {
    term: "returning_wallet_share",
    def: "returning_wallets divided by active_wallets. Null when there were no active wallets, never a clean looking 0.0.",
  },
] as const;

const MISSING_STATES = [
  {
    state: "unconfigured",
    meaning: "No Dune key or no saved query id. The block says so instead of showing a row of dashes.",
  },
  {
    state: "no_data",
    meaning: "The protocol is outside the curated contract map, or the chain is not covered.",
  },
  {
    state: "partial",
    meaning: "Some chains or some days resolved. The gap is named rather than averaged away.",
  },
  {
    state: "stale",
    meaning: "The newest complete UTC day is too old to describe today. Only complete days count, so a midday reading is never mistaken for a collapse.",
  },
] as const;

/* The bar for promoting activity into a weighted indicator. Written down before
   it is needed, so the decision cannot be made by whoever is annoyed first. */
const PROMOTION_BAR = [
  {
    title: "Six months of continuous history",
    text: "Across the tracked protocols, spanning at least one genuine stress event. A metric watched through a calm season has not been tested.",
  },
  {
    title: "A written hypothesis",
    text: "Naming the mechanism, the direction and the lead time it claims, for example that activity collapses before TVL because debt is repaid before liquidity is withdrawn.",
  },
  {
    title: "A backtest that adds signal",
    text: "It must flag cases the existing seven indicators miss, without double counting volume or TVL and without merely re flagging what they already catch.",
  },
] as const;

/* ------------------------------------------------------------ the chat layer
   The three outcomes of an ask, and what each one means for the person reading
   it. There is no fourth outcome where the system guesses. */
const OUTCOMES = [
  {
    engine: "llm",
    title: "Grounded prose",
    text: "A key is configured and the call succeeded. Each claim is tied to a numbered source, and the answer states what the retrieved context cannot establish.",
    when: "OpenAI compatible key present, and the relevance gate passed.",
  },
    {
    engine: "extractive",
    title: "Verbatim evidence",
    text: "No key, or the model call failed. You get quoted passages from the corpus: no synthesis, nothing invented, same sources.",
    when: "The default offline path. The demo never hard depends on a model.",
  },
  {
    engine: "none",
    title: "A refusal",
    text: "No retrieved chunk cleared the relevance gate, so the answer names what it cannot establish and lists the missing evidence instead of writing a paragraph.",
    when: "Off topic questions, and questions the pipeline has no data for.",
  },
] as const;

const RETRIEVAL = [
  {
    icon: Database,
    title: "Two kinds of chunks",
    text: "Documentation (methodology, architecture, the mechanics primer, the sample research, the curated security notes) split on heading and paragraph boundaries, and one evidence pack per protocol: its overview numbers, each indicator's evidence and limitation, its data gaps and its recent alerts.",
  },
  {
    icon: SearchCheck,
    title: "Ranking that degrades honestly",
    text: "With an embedding key, chunks are ranked by cosine similarity (pgvector on Postgres, in-process cosine on SQLite). With none, the same store is ranked by an Okapi BM25 lexical score, k1 1.5 and b 0.75. Same top k, no external call.",
  },
  {
    icon: Scale,
    title: "A gate that knows which method ranked",
    text: "Cosine and BM25 are not comparable scales, so one fixed threshold cannot gate both. The vector path requires a cosine floor of 0.5; the lexical path requires the passage to share at least two distinct informative query terms after stopword removal, capped by the question's own informative count.",
  },
  {
    icon: Layers,
    title: "Provenance in the primary key",
    text: "Chunk ids hash the document, the section and the body together, so unchanged text keeps a stable id across re-indexes while the same boilerplate under a different heading is a distinct row rather than a collision.",
  },
] as const;

/* ------------------------------------------------------------- the machine
   Four boxes, and the reason each one is that shape. */
const ARCHITECTURE = [
  {
    icon: Layers,
    title: "Web tier",
    text: "Next.js 16 App Router on React 19, Tailwind v4 with shadcn/ui and Recharts. Server components read the API with the visitor's own session cookie, so the first paint is the real board rather than a skeleton waiting on a client fetch. Cache Components and partial prerendering keep the public pages static.",
  },
  {
    icon: Server,
    title: "API tier",
    text: "FastAPI with pandas and NumPy. The scoring core is pure functions, the routers are thin, and every response is scope filtered for the subject that asked. APScheduler runs the monitoring pass in process.",
  },
  {
    icon: Database,
    title: "Data layer",
    text: "SQLite for development and the demo, Postgres 16 with pgvector for production, schema moved by Alembic revisions. Daily snapshots make the board DB-first, so a page never waits on a live crawl and a provider outage does not blank the dashboard.",
  },
  {
    icon: Lock,
    title: "Access layer",
    text: "Local accounts with a memory hard hash, opaque session tokens, RBAC verbs plus attribute predicates, and single use tickets for the streamed chat socket. The published API port and the WebSocket are reachable without the web tier, so both are authorized at the API.",
  },
] as const;

const ARCH_FACTS = [
  "One OpenAPI document generates the TypeScript types the web tier compiles against, so the two halves cannot drift quietly.",
  "Every upstream call is timed, retried and bounded; a slow provider defers work to the next pass instead of holding the current one.",
  "Health and readiness are separate endpoints, so an orchestrator can tell alive from serving.",
  "No dependency on a managed SaaS to run the core: DefiLlama is public, retrieval falls back to local BM25, and briefs fall back to a deterministic template.",
  "The whole stack is three containers (api, web, db) behind one compose file, with Alpine images and a locally built pgvector layer.",
] as const;

/* --------------------------------------------------------------- access model
   Verbs come from security/rbac.py, the demo subjects and clearances from the
   seed set, and the predicates from security/policy.py. */
const ROLES = [
  {
    role: "viewer",
    verbs: "read protocols, alerts, briefs and ask the analyst",
    note: "Cannot export a brief and cannot spend compute: no downloads, no crawl, no manual run. Critical alert content is counted but withheld.",
  },
  {
    role: "analyst",
    verbs: "viewer plus brief export and a monitoring run",
    note: "The desk role. In the demo this subject is also category scoped to two verticals, which is what shows attribute filtering on the board.",
  },
  {
    role: "risk_officer",
    verbs: "analyst plus the audit trail",
    note: "Clearance 2: sees critical alert content and may export low confidence briefs.",
  },
  {
    role: "admin",
    verbs: "every permission",
    note: "Clearance 3, user management and policy management, and the only role that may run the monitor past the freshness and business hours gates.",
  },
] as const;

const PREDICATES = [
  {
    title: "Category scope",
    text: "An analyst assigned to two verticals gets those two verticals on the board, the protocol pages, the summaries and the alert feed. The rest is filtered at the API, not hidden by the UI.",
  },
  {
    title: "Severity clearance",
    text: "Alerts above a subject's clearance are withheld as a counted set: the feed still renders, and the banner states how many were withheld and which clearance unlocks them.",
  },
  {
    title: "Confidence floor for exports",
    text: "A brief generated at low confidence cannot be exported by a role that has not earned the export, because a shaky document should not leave the tool looking settled.",
  },
  {
    title: "Freshness and business-hours gates",
    text: "A manual monitoring run against a stale snapshot, or outside the configured window, is refused with the condition that failed rather than silently producing a comparison nobody asked for.",
  },
  {
    title: "Single use socket tickets",
    text: "The streamed chat cannot attach a cookie to a WebSocket handshake, so the web tier mints a short lived one time ticket that the API consumes on connect.",
  },
  {
    title: "Cache discipline",
    text: "Authenticated responses are marked no-store and excluded from the framework's shared data cache, so one subject's scope filtered board can never be replayed to another.",
  },
] as const;

const SESSION_FACTS = [
  {
    icon: Lock,
    title: "Passwords",
    text: "hashlib.scrypt from the standard library, n 2^14 with 16 MiB of memory per hash, parameters stored alongside the digest so they can be raised later without invalidating anyone. No third party hashing dependency, so nothing new to audit.",
  },
  {
    icon: ShieldCheck,
    title: "Sessions",
    text: "Opaque tokens. The database stores only the SHA 256 digest, with a configurable lifetime (12 hours by default), and the browser holds the token in an httpOnly, same-site lax cookie the pages cannot read.",
  },
  {
    icon: Server,
    title: "Authority",
    text: "The middleware redirect is a convenience, not a control. The API re-authorizes every request, so a visitor who types the port instead of the URL gets a 401 rather than a dashboard.",
  },
  {
    icon: CircleAlert,
    title: "Modes",
    text: "off reproduces the pre-auth open demo, demo seeds four local identities and enables the role switcher, and required seeds nothing. The demo password is published on purpose: these are tour accounts, not credentials to reuse.",
  },
] as const;

/* ------------------------------------------------------------- honest limits
   The list we would rather you read early. Each line is a claim the tool does
   not make, not an aspiration. */
const LIMITS = [
  "It does not detect wash trading or sybil activity. That needs transaction level classification this pipeline does not do.",
  "It does not evaluate token emission schedules. They are not in the free DefiLlama endpoints.",
  "It does not yet price-normalize TVL per protocol. The decomposition is written and tested, but it needs a reliable protocol to token map before it is shown rather than approximated.",
  "Its peg watch covers only the stablecoins in the curated map, measured against a $1.00 target. It does not model collateral or redemption mechanics, and a coin outside the map reads as not assessed.",
  "Its security posture signal is a weak proxy: an audit count is a prompt for manual review, never a guarantee of safety.",
  "It does not replace smart contract audits or incident forensics.",
  "It cannot tell you whether a protocol is a good investment. It tells you what to check next.",
  "Retrieval quality bounds the chat: it can only explain what the pipeline already measured, and it inherits every limitation above.",
] as const;

const ROADMAP = [
  {
    tone: "ds-tri-shipped",
    title: "Shipped",
    icon: CircleCheck,
    items: [
      "Fees, revenue and DEX volume, with real-yield dependence as a scored indicator",
      "Stablecoin peg watch: the indicator plus the depeg alert rule",
      "Alert delivery to console, webhook, Slack, Discord, Telegram and email",
      "Risk-score history with a trend chart",
      "Brief export as Markdown, CSV and print-ready PDF",
      "Ask the analyst with WebSocket streaming and a refusal path",
      "Side by side comparison of two to three protocols",
      "Accounts, sessions, RBAC verbs and ABAC predicates enforced in the API",
    ],
  },
  {
    tone: "ds-tri-partial",
    title: "Partial",
    icon: CircleAlert,
    items: [
      "The security note set is still a curated dict, not an externalized feed",
      "Authorization ships; per-subject rate limits and LLM cost quotas do not, so a logged-in account can still spend the budget",
      "Test coverage spans Vitest, Playwright and respx mocked HTTP, with no property-based or golden-file tests yet",
      "On-chain activity is displayed, cited and monitored, but deliberately not scored",
    ],
  },
  {
    tone: "ds-tri-open",
    title: "Deliberately not built",
    icon: CircleX,
    items: [
      "Anomaly detection to replace static thresholds (it needs the calibration history first)",
      "What-if weight sliders (a score you can tune is a score you cannot defend)",
      "Correlation and contagion views",
      "A command palette, shareable board filters and a virtualized grid",
      "An external job queue (the in-process scheduler is honest about its limits for this scale)",
      "Observability beyond health and readiness, and a Redis or ETag caching layer",
    ],
  },
] as const;

const FAQS = [
  {
    q: "Is any of this investment advice?",
    a: "No, and the footer says so on every page. DeFiScope AI is a research instrument: it scores dimensions that public aggregate data can observe, shows the evidence, states the limitation and leaves the judgment with you. A low band means low risk on the dimensions TVL data can observe, nothing more.",
  },
  {
    q: "Why does a protocol show n/a instead of a number?",
    a: "Because the data does not exist. A fee adapter that does not cover the protocol, fewer than five daily observations, a mapped coin without price history, a protocol outside the contract map: each of those is a gap. Rendering zero would turn an absence of evidence into evidence of absence, so the field stays empty and the indicator renormalizes out of the composite.",
  },
  {
    q: "A protocol's composite says unknown. Is that a score of 100?",
    a: "It is not a score at all. If no indicator is computable the band is unknown and nothing is displayed as a number. That is the same rule applied one level up: unknown is never treated as safe, and it is never treated as dangerous either.",
  },
  {
    q: "Do I need API keys to run it?",
    a: "For the core model, no. DefiLlama's endpoints are public. A key is optional for three add-ons: a large language model for prose briefs and embedded retrieval (without one, briefs use a deterministic template and chat uses BM25 with extractive answers), Dune for contract-level activity, and each notification channel you want to fire.",
  },
  {
    q: "How current is what I am looking at?",
    a: "The monitoring pass runs every 30 minutes, and every payload carries an as_of date marking the latest underlying observation. Staleness is itself a rule: if the last observation is older than two days a stale_data alert fires, because upstream collection failure should be visible before it contaminates a conclusion.",
  },
  {
    q: "Can I change the thresholds?",
    a: "The rule thresholds are environment driven (DEFISCOPE_ALERT_*), and so are the scheduler, the watchlist and the channel secrets. The indicator anchors and weights live in the scoring module instead, on purpose: changing what a score means should be a code review, not a deployment variable.",
  },
  {
    q: "Can I run this privately?",
    a: "Yes. Three containers behind one compose file, SQLite or Postgres, no required outbound dependency except the data providers themselves. The system is designed so a missing model key or a Dune outage degrades the presentation, not the honesty of the numbers.",
  },
  {
    q: "How do I get the data out?",
    a: "The whole surface is a documented REST API with a published OpenAPI schema, and briefs export as Markdown, CSV or print-ready PDF. Research is reproducible only if the numbers can leave the dashboard.",
  },
  {
    q: "Who builds and maintains this?",
    a: "It is an independent open project, not a data vendor: the repository is public, the methodology is a document rather than a black box, and the source link is in the footer. If a claim on this page does not match the code, the code is right and the page is a bug.",
  },
] as const;

/* ===========================================================================
   Markup. Sections in document order; each one is an anchor in the chapter row.
   ========================================================================= */

export default function AboutPage() {
  return (
    <div className="ds-root ds-doc" id="landing-root" data-landing="pending">
      <LandingReveal />

      <a className="ds-skip" href="#about-main">
        Skip to content
      </a>

      <LandingNav
        current="about"
        anchors={{ platform: LINKS.platform, how: LINKS.how }}
      />

      <main id="about-main">
        {/* ------------------------------------------------------------- hero */}
        <section className="ds-page-hero" id="hero">
          <div className="ds-page-bg" aria-hidden="true" />
          {/* The same globe as the landing, graded down to atmosphere. */}
          <LandingFilm className="ds-page-film" />
          <div className="ds-page-tint" aria-hidden="true" />
          <div className="ds-page-hero-inner">
            <p className="ds-eyebrow">About DeFiScope AI</p>

            <h1 className="ds-h1">
              <span className="ds-ln">
                <span className="ds-ln-inner">Built to explain,</span>
              </span>
              <span className="ds-ln">
                <span className="ds-ln-inner">not to reassure.</span>
              </span>
            </h1>

            <p className="ds-sub">
              Seven weighted indicators, six monitoring rules and one grounded
              analyst, running on public data and shipping the evidence behind
              every number: including, always, the numbers it could not compute.
            </p>

            <div className="ds-ctas">
              <Link className="ds-btn ds-btn-lg ds-btn-primary" href={LINKS.board}>
                Open the board
                <Arrow className="ds-arrow" />
              </Link>
              <a className="ds-btn ds-btn-lg ds-btn-ghost" href="#methodology">
                How a score is built
                <Arrow className="ds-arrow" />
              </a>
            </div>

            <nav className="ds-chips" aria-label="On this page">
              {CHAPTERS.map(({ href, label }) => (
                <a key={href} href={href}>
                  {label}
                </a>
              ))}
            </nav>
          </div>
        </section>

        {/* ----------------------------------------------------------- mission */}
        <section className="ds-section" id="mission" aria-labelledby="mission-h">
          <div className="ds-section-inner">
            <p className="ds-eyebrow">Mission</p>
            <h2 className="ds-h2" id="mission-h">
              Most dashboards answer{" "}
              <em>how big is it.</em> That is the easy question and the least
              useful one.
            </h2>
            <p className="ds-lede">
              Total value locked is a dollar figure, so it moves with price, with
              emissions and with one-time deposits. A rising number on that basis
              proves nothing about a protocol. DeFiScope AI was written to answer
              the harder question an analyst actually asks.
            </p>

            <div className="ds-prose">
              <p>
                What would a careful reviewer check before trusting this protocol,
                and what can the data that is actually available establish? That
                framing changes the product. The tool is not a leaderboard with a
                risk label attached; it is a due-diligence pass that has been
                automated as far as evidence allows and then stops, honestly, where
                the evidence does not reach.
              </p>
              <p>
                So every indicator carries three fields rather than one: the value,
                the evidence behind it, and the limitation. The limitation is not
                legal decoration. It is the reason the number can be read at all.
                Chain concentration says nothing about the security of the dominant
                chain. An audit count says nothing about coverage or recency. A TVL
                trend cannot tell organic deposits from bought ones.
              </p>
              <p>
                The system is deliberately unimpressive about its own conclusions.
                It will not call a protocol healthy because TVL rose. A surge makes
                it ask you to verify whether emissions caused it. What it does is
                name the reason to investigate, in the order the evidence supports,
                and hand the judgment back to you.
              </p>
            </div>

            <figure className="ds-pull">
              <Quote className="ds-pull-icon" aria-hidden="true" />
              <blockquote>
                Rising or falling TVL, by itself, proves nothing about sustainable
                growth or protocol risk.
              </blockquote>
              <figcaption>
                The central analytical caveat, written into the methodology before it
                was written into the code, so the alerts would inherit it.
              </figcaption>
            </figure>

            <h3 className="ds-subhead">Four rules the build is held to</h3>
            <ul className="ds-cards">
              {PRINCIPLES.map(({ icon: Icon, title, text }) => (
                <li className="ds-card" key={title}>
                  <span className="ds-card-icon" aria-hidden="true">
                    <Icon size={19} strokeWidth={1.6} />
                  </span>
                  <h4 className="ds-card-title">{title}</h4>
                  <p className="ds-card-text">{text}</p>
                </li>
              ))}
            </ul>

            <h3 className="ds-subhead">Who it is for</h3>
            <ul className="ds-cards">
              {FOR_WHOM.map(({ icon: Icon, title, text }) => (
                <li className="ds-card" key={title}>
                  <span className="ds-card-icon" aria-hidden="true">
                    <Icon size={19} strokeWidth={1.6} />
                  </span>
                  <h4 className="ds-card-title">{title}</h4>
                  <p className="ds-card-text">{text}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* ------------------------------------------------------- the headline
           numbers */}
        <section
          className="ds-section ds-section-raise ds-stats-band"
          aria-labelledby="stats-h"
        >
          <div className="ds-section-inner">
            <h2 className="ds-h2 ds-h2-sm" id="stats-h">
              Eight numbers, every one of them checkable in the repository.
            </h2>
            <dl className="ds-stats">
              {STATS.map(({ value, label, note }) => (
                <div className="ds-stat" key={label}>
                  <dt className="ds-stat-label">{label}</dt>
                  <dd className="ds-stat-num">{value}</dd>
                  <dd className="ds-stat-note">{note}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        {/* ------------------------------------------------------ methodology */}
        <section className="ds-section" id="methodology" aria-labelledby="method-h">
          <div className="ds-section-inner">
            <p className="ds-eyebrow">Methodology</p>
            <h2 className="ds-h2" id="method-h">
              How a number gets made.
            </h2>
            <p className="ds-lede">
              Six stages between an upstream API and a score on the board. Five of
              them are arithmetic. None of them is a model guessing.
            </p>

            <ol className="ds-steps ds-steps-2">
              {PIPELINE.map(({ title, text }) => (
                <li className="ds-step" key={title}>
                  <h3 className="ds-step-title">{title}</h3>
                  <p className="ds-step-text">{text}</p>
                </li>
              ))}
            </ol>

            <h3 className="ds-subhead">The seven indicators</h3>
            <p className="ds-paragraph">
              Each row is the weight it carries in the composite, the two anchor
              points its score is interpolated between, and the claim it does not
              support. A score of 100 on any row means the maximum risk
              contribution on that dimension, not a bad protocol.
            </p>

            <div
              className="ds-table-wrap"
              role="region"
              aria-label="Indicator weights, anchors and limitations"
              tabIndex={0}
            >
              <table className="ds-table">
                <thead>
                  <tr>
                    <th scope="col">Indicator</th>
                    <th scope="col">Weight</th>
                    <th scope="col">Anchor, safe to risky</th>
                    <th scope="col">What it cannot establish</th>
                  </tr>
                </thead>
                <tbody>
                  {INDICATORS.map((row) => (
                    <tr key={row.name}>
                      <th scope="row">{row.name}</th>
                      <td className="ds-td-weight">{row.weight}</td>
                      <td className="ds-td-anchor">{row.anchor}</td>
                      <td className="ds-td-cannot">{row.cannot}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="ds-bands" role="list" aria-label="Risk bands">
              {BANDS.map(({ band, range, tone }) => (
                <span className={`ds-band ${tone}`} key={band} role="listitem">
                  <span className="ds-band-dot" aria-hidden="true" />
                  <span className="ds-band-name">{band}</span>
                  <span className="ds-band-range">{range}</span>
                </span>
              ))}
            </div>

            <p className="ds-note">
              <span className="ds-note-label">Worth saying out loud</span>
              The anchors are documented judgment calls, not market truth. They were
              chosen to be defensible in conversation, and a reader who disagrees
              with an anchor can find it in{" "}
              <code className="ds-inline-code">app/analysis/scoring.py</code> rather
              than having to trust a chart. That is the whole point of publishing
              the weights: disagreement should be possible.
            </p>
          </div>
        </section>

        {/* ------------------------------------------------------- data sources */}
        <section
          className="ds-section ds-section-raise"
          id="data"
          aria-labelledby="data-h"
        >
          <div className="ds-section-inner">
            <p className="ds-eyebrow">Data sources</p>
            <h2 className="ds-h2" id="data-h">
              Two providers, three curated maps, <em>no key to start.</em>
            </h2>
            <p className="ds-lede">
              Every input the model reads, what it is used for and the limitation it
              arrives with. A source without its weakness is a source that will be
              trusted too far.
            </p>

            <ul className="ds-sources">
              {SOURCES.map(({ icon: Icon, name, usedFor, limit }) => (
                <li className="ds-source" key={name}>
                  <span className="ds-source-head">
                    <Icon size={17} strokeWidth={1.6} aria-hidden="true" />
                    <span className="ds-source-name">{name}</span>
                  </span>
                  <p className="ds-source-used">
                    <span className="ds-tag">Used for</span>
                    {usedFor}
                  </p>
                  <p className="ds-source-limit">
                    <span className="ds-tag ds-tag-warn">Limitation</span>
                    {limit}
                  </p>
                </li>
              ))}
            </ul>

            <div className="ds-prose">
              <p>
                Two conventions hold across all of them. Every payload carries an{" "}
                <code className="ds-inline-code">as_of</code> date marking the
                newest underlying observation, so a reader can see how old a
                conclusion is without asking. And a missing series is reported as
                missing: forward filling never invents a value before the first
                observation, and an untracked adapter produces a gap rather than a
                zero that would score as safe.
              </p>
            </div>
          </div>
        </section>

        {/* ------------------------------------------------------- on-chain */}
        <section className="ds-section" id="onchain" aria-labelledby="onchain-h">
          <div className="ds-section-inner">
            <p className="ds-eyebrow">On-chain activity</p>
            <h2 className="ds-h2" id="onchain-h">
              Measured, shown, cited, <em>and not yet scored.</em>
            </h2>
            <p className="ds-lede">
              TVL is a stock, and fee adapters disagree about what they count.
              Neither answers the obvious question: how many addresses actually
              touched this protocol today? That is read straight off chain data and
              placed beside the rest, additively.
            </p>

            <div
              className="ds-table-wrap"
              role="region"
              aria-label="On-chain metric definitions"
              tabIndex={0}
            >
              <table className="ds-table ds-table-2">
                <thead>
                  <tr>
                    <th scope="col">Field</th>
                    <th scope="col">Definition, per tracked contract set, per UTC day</th>
                  </tr>
                </thead>
                <tbody>
                  {ONCHAIN_FIELDS.map(({ term, def }) => (
                    <tr key={term}>
                      <th scope="row">
                        <code className="ds-inline-code">{term}</code>
                      </th>
                      <td>{def}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h3 className="ds-subhead">Four ways to be missing, named separately</h3>
            <ul className="ds-cards">
              {MISSING_STATES.map(({ state, meaning }) => (
                <li className="ds-card ds-card-plain" key={state}>
                  <h4 className="ds-card-title">
                    <code className="ds-inline-code">{state}</code>
                  </h4>
                  <p className="ds-card-text">{meaning}</p>
                </li>
              ))}
            </ul>

            <h3 className="ds-subhead">
              Why the composite does not read these numbers yet
            </h3>
            <div className="ds-prose">
              <p>
                A risk weight needs a calibration story, and there is not one yet. No
                replay over a resolved failure shows that falling activity would have
                flagged it earlier than TVL already did. Adding a weight now would
                contribute noise and a false sense of coverage, so the four metrics
                sit in the brief and the chat and stay out of the score.
              </p>
            </div>
            <ol className="ds-steps">
              {PROMOTION_BAR.map(({ title, text }) => (
                <li className="ds-step" key={title}>
                  <h3 className="ds-step-title">{title}</h3>
                  <p className="ds-step-text">{text}</p>
                </li>
              ))}
            </ol>
            <p className="ds-note">
              <span className="ds-note-label">All three, or nothing</span>
              Until every condition holds, on-chain activity is displayed, cited and
              monitored, and not scored. The bar was written down before the data
              arrived, which is the only way it means anything when the data does.
            </p>
          </div>
        </section>

        {/* --------------------------------------------------------- research */}
        <section
          className="ds-section ds-section-raise"
          id="research"
          aria-labelledby="research-h"
        >
          <div className="ds-section-inner">
            <p className="ds-eyebrow">
              <MessageSquareText size={13} strokeWidth={1.8} aria-hidden="true" />
              Ask the analyst
            </p>
            <h2 className="ds-h2" id="research-h">
              Grounded, cited, and willing to say it does not know.
            </h2>
            <p className="ds-lede">
              The chat adds no new claims. It is a window onto the evidence the
              pipeline already produced: it can re-state it, point at it and admit
              what it cannot establish. It is not an independent analyst, and it
              never overrides a data gap with a confident sentence.
            </p>

            <ul className="ds-cards ds-cards-3">
              {OUTCOMES.map(({ engine, title, text, when }) => (
                <li className="ds-card ds-card-outcome" key={engine}>
                  <span className="ds-engine">{engine}</span>
                  <h4 className="ds-card-title">{title}</h4>
                  <p className="ds-card-text">{text}</p>
                  <p className="ds-when">{when}</p>
                </li>
              ))}
            </ul>

            <h3 className="ds-subhead">How an answer is assembled</h3>
            <ul className="ds-cards">
              {RETRIEVAL.map(({ icon: Icon, title, text }) => (
                <li className="ds-card" key={title}>
                  <span className="ds-card-icon" aria-hidden="true">
                    <Icon size={19} strokeWidth={1.6} />
                  </span>
                  <h4 className="ds-card-title">{title}</h4>
                  <p className="ds-card-text">{text}</p>
                </li>
              ))}
            </ul>

            <p className="ds-note">
              <span className="ds-note-label">Visible on every reply</span>
              Citations, whether the answer is grounded, and which engine produced
              it are fields on the response, not secrets in a log. A model written
              sentence should never be mistaken for a verified fact, least of all by
              the person who asked.
            </p>
          </div>
        </section>

        {/* ----------------------------------------------------- architecture */}
        <section
          className="ds-section"
          id="architecture"
          aria-labelledby="arch-h"
        >
          <div className="ds-section-inner">
            <p className="ds-eyebrow">Architecture</p>
            <h2 className="ds-h2" id="arch-h">
              Two tiers, one database, nothing you have to take on faith.
            </h2>
            <p className="ds-lede">
              A research tool is only as trustworthy as its plumbing is boring. Each
              layer below does one job, and the risky one, the arithmetic, has no
              network access at all.
            </p>

            <ul className="ds-cards">
              {ARCHITECTURE.map(({ icon: Icon, title, text }) => (
                <li className="ds-card" key={title}>
                  <span className="ds-card-icon" aria-hidden="true">
                    <Icon size={19} strokeWidth={1.6} />
                  </span>
                  <h4 className="ds-card-title">{title}</h4>
                  <p className="ds-card-text">{text}</p>
                </li>
              ))}
            </ul>

            <pre
              className="ds-code ds-code-wide"
              aria-label="The scoring entry point, as implemented"
            >
              <code>
                <span className="ds-code-line">
                  <span className="ds-code-verb">def</span> assess(
                </span>
                <span className="ds-code-line">
                  {"    "}
                  <span className="ds-code-key">slug,</span> tvl_df, chain_tvls,
                  tvl_history, staking_history,
                </span>
                <span className="ds-code-line">
                  {"    "}
                  audits=<span className="ds-code-str">None</span>, fees_30d=
                  <span className="ds-code-str">None</span>, minted_symbols=
                  <span className="ds-code-str">None</span>,
                </span>
                <span className="ds-code-line">
                  ) -&gt; <span className="ds-code-str">RiskAssessment</span>:
                </span>
                <span className="ds-code-line"> </span>
                <span className="ds-code-line">
                  <span className="ds-code-key">  # 7 indicators, each a pure map
                  from a value to 0 to 100</span>
                </span>
                <span className="ds-code-line">
                  {"    "}scored = [i{" "}
                  <span className="ds-code-verb">for</span> i{" "}
                  <span className="ds-code-verb">in</span> indicators{" "}
                  <span className="ds-code-verb">if</span> i.score{" "}
                  <span className="ds-code-verb">is not</span>{" "}
                  <span className="ds-code-str">None</span>]
                </span>
                <span className="ds-code-line">
                  {"    "}composite = sum(i.score * i.weight{" "}
                  <span className="ds-code-verb">for</span> i{" "}
                  <span className="ds-code-verb">in</span> scored) / total_w
                </span>
                <span className="ds-code-line">
                  {"    "}
                  <span className="ds-code-key">
                    # missing indicators never count as safe: they are returned
                  </span>
                </span>
                <span className="ds-code-line">
                  {"    "}
                  <span className="ds-code-key">
                    # under data_gaps and excluded from the average
                  </span>
                </span>
              </code>
            </pre>

            <h3 className="ds-subhead">Plumbing decisions worth naming</h3>
            <ul className="ds-ticks">
              {ARCH_FACTS.map((fact) => (
                <li className="ds-tick" key={fact}>
                  <CircleCheck size={16} strokeWidth={1.8} aria-hidden="true" />
                  <span>{fact}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* --------------------------------------------------------- security */}
        <section
          className="ds-section ds-section-raise"
          id="security"
          aria-labelledby="security-h"
        >
          <div className="ds-section-inner">
            <p className="ds-eyebrow">Access model</p>
            <h2 className="ds-h2" id="security-h">
              Roles grant verbs. <em>Attributes decide the records.</em>
            </h2>
            <p className="ds-lede">
              Splitting the two is what lets a new team scope be added without
              inventing a new role, and what lets a denial be explained instead of
              merely delivered.
            </p>

            <div
              className="ds-table-wrap"
              role="region"
              aria-label="Roles and the verbs each grants"
              tabIndex={0}
            >
              <table className="ds-table">
                <thead>
                  <tr>
                    <th scope="col">Role</th>
                    <th scope="col">Verbs</th>
                    <th scope="col">What that means in practice</th>
                  </tr>
                </thead>
                <tbody>
                  {ROLES.map(({ role, verbs, note }) => (
                    <tr key={role}>
                      <th scope="row">
                        <code className="ds-inline-code">{role}</code>
                      </th>
                      <td className="ds-td-anchor">{verbs}</td>
                      <td>{note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h3 className="ds-subhead">The predicates evaluated behind the gate</h3>
            <ul className="ds-cards ds-cards-3">
              {PREDICATES.map(({ title, text }) => (
                <li className="ds-card ds-card-plain" key={title}>
                  <h4 className="ds-card-title">{title}</h4>
                  <p className="ds-card-text">{text}</p>
                </li>
              ))}
            </ul>

            <h3 className="ds-subhead">Credentials and sessions</h3>
            <ul className="ds-cards">
              {SESSION_FACTS.map(({ icon: Icon, title, text }) => (
                <li className="ds-card" key={title}>
                  <span className="ds-card-icon" aria-hidden="true">
                    <Icon size={19} strokeWidth={1.6} />
                  </span>
                  <h4 className="ds-card-title">{title}</h4>
                  <p className="ds-card-text">{text}</p>
                </li>
              ))}
            </ul>

            <p className="ds-note">
              <span className="ds-note-label">Not a security theatre</span>
              The page level redirect in the web tier is a courtesy: it saves a
              visitor from watching three panels fail. It is not the control. The
              API port and the chat socket are reachable without it, and both
              re-authorize every call, so the guard survives deleting the middleware
              entirely.
            </p>
          </div>
        </section>

        {/* ------------------------------------------------------------ limits */}
        <section className="ds-section" id="limits" aria-labelledby="limits-h">
          <div className="ds-section-inner">
            <p className="ds-eyebrow">Honest limits</p>
            <h2 className="ds-h2" id="limits-h">
              What this system deliberately does <em>not</em> claim.
            </h2>
            <p className="ds-lede">
              A tool that hides its boundaries eventually presents a guess as a
              finding. These are the boundaries, written as a list you can hold us
              to, and every one of them is surfaced in the product as{" "}
              <code className="ds-inline-code">data_gaps</code> rather than smoothed
              over.
            </p>

            <ul className="ds-limits">
              {LIMITS.map((line) => (
                <li className="ds-limit" key={line}>
                  <CircleX size={16} strokeWidth={1.8} aria-hidden="true" />
                  <span>{line}</span>
                </li>
              ))}
            </ul>

            <div className="ds-prose">
              <p>
                Two readings matter more than the list. A low band means low risk on
                the dimensions TVL data can observe; it is not a clean bill of
                health, and it has never been sold as one. And{" "}
                <strong className="ds-strong">n/a</strong> means the series does not
                exist, which is a statement about the data, not about the protocol.
                Confusing those two is how a dashboard becomes a liability.
              </p>
            </div>
          </div>
        </section>

        {/* ----------------------------------------------------------- roadmap */}
        <section
          className="ds-section ds-section-raise"
          id="roadmap"
          aria-labelledby="roadmap-h"
        >
          <div className="ds-section-inner">
            <p className="ds-eyebrow">Roadmap</p>
            <h2 className="ds-h2" id="roadmap-h">
              Shipped, partial, and deliberately not built.
            </h2>
            <p className="ds-lede">
              Verified against the repository, not against a plan. The third column
              is the honest one: several obvious features are open because they would
              add a number the evidence cannot defend yet.
            </p>

            <div className="ds-tri">
              {ROADMAP.map(({ tone, title, icon: Icon, items }) => (
                <div className={`ds-tri-col ${tone}`} key={title}>
                  <h3 className="ds-tri-title">
                    <Icon size={16} strokeWidth={1.8} aria-hidden="true" />
                    {title}
                  </h3>
                  <ul className="ds-tri-list">
                    {items.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>

            <p className="ds-note">
              <span className="ds-note-label">How the next thing gets chosen</span>
              An item lands when it removes a manual step or closes an evidence gap,
              not when it adds another number to the board. The three conditions in
              the on-chain section are the template: history, a stated mechanism, and
              a backtest that shows the tool would have seen something it currently
              misses.
            </p>
          </div>
        </section>

        {/* --------------------------------------------------------------- faq */}
        <section className="ds-section" id="faq" aria-labelledby="faq-h">
          <div className="ds-section-inner ds-faq-inner">
            <p className="ds-eyebrow">Questions</p>
            <h2 className="ds-h2" id="faq-h">
              Asked often, answered without hedging.
            </h2>

            <div className="ds-faq">
              {FAQS.map(({ q, a }) => (
                <details className="ds-faq-item" key={q}>
                  <summary className="ds-faq-q">{q}</summary>
                  <p className="ds-faq-a">{a}</p>
                </details>
              ))}
            </div>

            <p className="ds-paragraph">
              The long form of everything on this page lives in the repository:{" "}
              <code className="ds-inline-code">docs/methodology.md</code> for the
              formulas and anchors,{" "}
              <code className="ds-inline-code">docs/architecture.md</code> for the
              plumbing and the decision log, and{" "}
              <code className="ds-inline-code">docs/defi-mechanics-primer.md</code>{" "}
              for the parts of DeFi this model assumes you already know.
            </p>
          </div>
        </section>

        {/* ---------------------------------------------------------- closing */}
        <section className="ds-section ds-contact" aria-labelledby="start-h">
          <div className="ds-contact-inner">
            <h2 className="ds-contact-title" id="start-h">
              Look at the evidence yourself.
            </h2>
            <p className="ds-contact-text">
              The board is live data with its gaps labelled. Sign in with a demo
              account, switch roles and watch what a permission actually changes:
              the withheld alert count, the disabled export, the filtered verticals.
            </p>
            <div className="ds-contact-actions">
              <Link className="ds-btn ds-btn-primary" href={LINKS.board}>
                Open the board
                <Arrow className="ds-arrow" />
              </Link>
              <Link className="ds-btn ds-btn-ghost" href={LINKS.docs}>
                Read the docs
                <Arrow className="ds-arrow" />
              </Link>
              <Link className="ds-btn ds-btn-ghost" href={LINKS.home}>
                Back to the platform
                <Arrow className="ds-arrow" />
              </Link>
            </div>
          </div>
        </section>
      </main>

      <LandingFooter />
    </div>
  );
}
