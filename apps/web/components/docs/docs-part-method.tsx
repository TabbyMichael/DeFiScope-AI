import {
  BANDS,
  INDICATORS,
  METRICS,
  SOURCES,
} from "../docs/docs-data";
import {
  Code,
  DocTable,
  DocsSection,
  DocsSub,
  Lead,
  Note,
  P,
} from "../docs/docs-section";

/* ===========================================================================
   Sections 4 to 8: the machinery. This is the part a reader comes to check a
   number against, so it stays literal: the modules are named by their path, the
   weights and bands are quoted from scoring.py, and the limitation column is the
   whole point of the indicator table.
   ========================================================================= */

const SERVICES = [
  "web, a Next.js App Router front end that renders the public pages statically and the board server-side",
  "api, a FastAPI service that owns the pipeline, the scheduler, the store reads and the authorization layer",
  "db, Postgres under compose or SQLite for dev and tests, holding daily snapshots, alerts, on-chain rows and chat chunks",
] as const;

const READ_STEPS = [
  "A board or history read is served from the latest snapshot per protocol in the database, so opening the app does not wait on DefiLlama.",
  "If the newest capture is older than the staleness window, the request hydrates live and the next scheduled pass persists what it saw.",
  "A cold start runs a warm-up pass in the background rather than blocking the port, so the service becomes reachable while the first crawl is still running.",
] as const;

const PIPELINE = [
  "Fetch the DefiLlama protocol packs, the fees and DEX volume adapters and the coin price charts; add Dune activity only when both a key and a saved query id exist.",
  "Normalize point series into a daily, forward-filled UTC frame, aggregating duplicate intraday points by max and never fabricating a value before the first real observation.",
  "Measure the pure primitives listed in section 6.",
  "Score each indicator by mapping its value onto 0 to 100 between a documented safe and risky anchor, clamped at both ends.",
  "Compose a weighted mean over the indicators that were computable, renormalizing so a missing one is never counted as safe.",
  "Monitor on the scheduler, persist alerts and snapshots idempotently, and fan new alerts out to whichever channels are configured.",
] as const;

function Architecture() {
  return (
    <DocsSection n={4} id="architecture" eyebrow="How a score is built" title="System architecture">
      <Lead>
        {"Three services and one rule: the numbers on the board are the same numbers the pipeline wrote to the store, and every one of them traces to a function with a test behind it."}
      </Lead>

      <DocsSub id="arch-services">{"Three services"}</DocsSub>
      <ul className="ds-ticks">
        {SERVICES.map((s) => (
          <li className="ds-tick" key={s}>
            <Code>{s.split(",")[0]}</Code>
            <span>{s.slice(s.indexOf(",") + 1).trim()}</span>
          </li>
        ))}
      </ul>

      <DocsSub id="arch-pipeline">{"The pipeline"}</DocsSub>
      <P>
        {"Between an upstream API and a number on the board there are six stages, each owned by a named module in "}
        <Code>{"services/api/app/"}</Code>
        {". The cadence is set by the scheduler in "}
        <Code>{"main.py"}</Code>
        {", which runs a pass every "}
        <Code>{"monitor_interval_minutes"}</Code>
        {" (30 by default)."}
      </P>
      <ol className="ds-steps">
        {PIPELINE.map((step, i) => (
          <li className="ds-step" key={i}>
            <p className="ds-step-text">{step}</p>
          </li>
        ))}
      </ol>

      <DocsSub id="arch-reads">{"How a read is served"}</DocsSub>
      <P>
        {"The dashboard and protocol pages are database-first, which is what keeps them cheap to open and immune to an upstream outage."}
      </P>
      <ul className="ds-ticks">
        {READ_STEPS.map((s, i) => (
          <li className="ds-tick" key={i}>
            <span>{s}</span>
          </li>
        ))}
      </ul>
    </DocsSection>
  );
}

const NORMALIZE = [
  "Series are indexed by UTC calendar day and forward-filled, so a weekend gap becomes the last known value rather than a hole.",
  "Duplicate intraday points, which DefiLlama emits as retroactive corrections, are aggregated by max.",
  "Forward filling never runs backwards past the first real observation: leading blanks stay blank.",
] as const;

function DataSources() {
  return (
    <DocsSection n={5} id="data-sources" eyebrow="How a score is built" title="Data sources">
      <Lead>
        {"Nothing is listed here without the weakness it carries. A source that cannot answer a question is named as unable, not quietly dropped."}
      </Lead>

      <DocsSub id="sources-table">{"Source by source"}</DocsSub>
      <div className="ds-sources">
        {SOURCES.map((s) => (
          <div className="ds-source" key={s.name}>
            <p className="ds-source-name">{s.name}</p>
            <p className="ds-source-used">
              <span className="ds-tag">Used for</span>
              {s.usedFor}
            </p>
            <p className="ds-source-limit">
              <span className="ds-tag ds-tag-warn">Limitation</span>
              {s.limit}
            </p>
          </div>
        ))}
      </div>

      <DocsSub id="sources-normalise">{"Normalization"}</DocsSub>
      <ul className="ds-ticks">
        {NORMALIZE.map((s, i) => (
          <li className="ds-tick" key={i}>
            <span>{s}</span>
          </li>
        ))}
      </ul>

      <DocsSub id="sources-gaps">{"Gaps, never zeros"}</DocsSub>
      <P>
        {"An indicator whose input is missing leaves the composite and is listed under "}
        <Code>{"data_gaps"}</Code>
        {". A fee adapter that does not track a protocol is a gap, not a zero; a stablecoin outside the curated map is not assessed, not safe. This is the single contract that runs through the whole scoring engine."}
      </P>
    </DocsSection>
  );
}

function Metrics() {
  return (
    <DocsSection n={6} id="metrics" eyebrow="How a score is built" title="Metric primitives">
      <Lead>
        {"The formulas in "}
        <Code>{"analysis/metrics.py"}</Code>
        {" that the scorer and the alert rules are built on. Each is pure and unit-tested, which is what lets a displayed number be traced to a documented calculation."}
      </Lead>

      <DocsSub id="metrics-list">{"The primitives"}</DocsSub>
      <DocTable caption="Metric primitives and their definitions" head={["Function", "What it computes"]} wide>
        {METRICS.map((m) => (
          <tr key={m.fn}>
            <th scope="row">
              <Code>{m.fn}</Code>
            </th>
            <td>{m.formula}</td>
          </tr>
        ))}
      </DocTable>

      <DocsSub id="metrics-purity">{"Pure and tested"}</DocsSub>
      <P>
        {"Every primitive returns "}
        <Code>{"None"}</Code>
        {" rather than guessing when its input is too short or its baseline is zero. The scorer treats "}
        <Code>{"None"}</Code>
        {" as a gap and renormalizes around it, so no metric silently upgrades a missing reading into a reassuring value."}
      </P>
    </DocsSection>
  );
}

function Scoring() {
  return (
    <DocsSection n={7} id="scoring" eyebrow="How a score is built" title="The seven indicators">
      <Lead>
        {"Seven weighted signals make the composite. Their weights sum to 1.00, and no single one can decide a band on its own."}
      </Lead>

      <DocsSub id="scoring-weights">{"Weights"}</DocsSub>
      <P>
        {"The weights are set so the most direct loss events carry the most influence: a minted stablecoin drifting off its peg outweighs a chain-concentration proxy. Peg integrity is "}
        <Code>{"0.20"}</Code>
        {", concentration and volatility "}
        <Code>{"0.16"}</Code>
        {" each, security posture and real yield "}
        <Code>{"0.14"}</Code>
        {", trend and incentive dependence "}
        <Code>{"0.10"}</Code>
        {"."}
      </P>

      <DocsSub id="scoring-anchors">{"Anchors and limitations"}</DocsSub>
      <P>
        {"Each indicator maps its raw value onto 0 to 100 between a documented safe anchor and a documented risky anchor. The right-hand column is the reason the table exists: it is what the number does not mean."}
      </P>
      <DocTable
        caption="Indicators, their weights, anchors and limitations"
        head={["Indicator", "Weight", "Anchors", "What it cannot establish"]}
        wide
      >
        {INDICATORS.map((ind) => (
          <tr key={ind.key}>
            <th scope="row">{ind.name}</th>
            <td className="ds-td-weight">{ind.weight}</td>
            <td className="ds-td-anchor">{ind.anchor}</td>
            <td className="ds-td-cannot">{ind.cannot}</td>
          </tr>
        ))}
      </DocTable>
      <Note label={"Reading a score"}>
        <P>
          {"A score of 100 is the maximum risk contribution for that indicator, not the largest raw value. Trend is scored so that sustained contraction is the risk signal; growth alone is never treated as safe."}
        </P>
      </Note>
    </DocsSection>
  );
}

function Bands() {
  return (
    <DocsSection n={8} id="bands" eyebrow="How a score is built" title="Bands and the composite">
      <Lead>
        {"The composite is the weighted mean over the indicators that could be computed, rounded to one decimal, then cut into four bands. A fifth state, unknown, means nothing was computable at all."}
      </Lead>

      <DocsSub id="bands-table">{"The four bands"}</DocsSub>
      <div className="ds-bands">
        {BANDS.map((b) => (
          <span className={`ds-band ${b.tone}`} key={b.band}>
            <span className="ds-band-dot" aria-hidden="true" />
            <span className="ds-band-name">{b.band}</span>
            <span className="ds-band-range">{b.range}</span>
          </span>
        ))}
        <span className="ds-band" key="unknown">
          <span className="ds-band-dot" aria-hidden="true" />
          <span className="ds-band-name">Unknown</span>
          <span className="ds-band-range">no score</span>
        </span>
      </div>
      <DocTable caption="Band thresholds and what each means" head={["Band", "Composite", "Meaning"]} wide>
        {BANDS.map((b) => (
          <tr key={b.band}>
            <th scope="row">{b.band}</th>
            <td className="ds-td-weight">{b.range}</td>
            <td>{b.meaning}</td>
          </tr>
        ))}
      </DocTable>
      <P>
        {"The thresholds live in "}
        <Code>{"scoring.py"}</Code>
        {": low under 30, moderate under 50, elevated under 70, high at or above. When every indicator is a gap the composite is "}
        <Code>{"None"}</Code>
        {" and the band reads "}
        <Code>{"unknown"}</Code>
        {", which the interface shows as a gap rather than as a zero or a reassurance."}
      </P>
    </DocsSection>
  );
}

export function MethodSections() {
  return (
    <>
      <Architecture />
      <DataSources />
      <Metrics />
      <Scoring />
      <Bands />
    </>
  );
}
