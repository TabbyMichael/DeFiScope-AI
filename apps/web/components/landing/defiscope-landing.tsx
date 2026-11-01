import { Suspense } from "react";
import Link from "next/link";
import {
  ArrowRight,
  BellRing,
  Database,
  LayoutGrid,
  MessageSquareText,
  ShieldCheck,
} from "lucide-react";

import {
  Arrow,
  LandingFooter,
  LandingNav,
  LandingReveal,
} from "./landing-chrome";
import { LandingFilm } from "./landing-film";
import { LINKS } from "./links";
import {
  BANDS,
  INDICATORS,
  RULES,
  SOURCES,
  fmtCount,
} from "@/components/docs/docs-data";
import { fetchCoverage } from "@/lib/api";

/* ---------------------------------------------------------------------------
   The landing. The hero, the rotating-globe film and the theme switch are the
   approved ones and are untouched; everything below them is rebuilt to have
   depth, and the depth is real: the first body section reads the live aggregate
   at `/api/status` (passed in by the server page) rather than asserting numbers.

   Two rules carry over from the product itself:
   1. Every figure is either a property of the shipped code or the live coverage
      read. Nothing here is a capability invented for a page.
   2. A value that could not be measured renders `n/a`, never a zero. When the
      whole backend is unreachable (`coverage === null`) the band says so once and
      every cell reads `n/a`; it never collapses that into "0 protocols".
   ------------------------------------------------------------------------- */

const CAPABILITIES = [
  {
    icon: ShieldCheck,
    title: "Explainable scoring",
    text: "Seven weighted indicators: concentration, volatility, trend, incentives, audit posture, real yield and peg integrity. Every score ships with its evidence and its limitation.",
  },
  {
    icon: LayoutGrid,
    title: "Research board",
    text: "TVL, 7d/30d moves, fees, DEX volume and chain concentration across the watchlist, rendered DB-first from daily snapshots so a page never waits on a live crawl.",
  },
  {
    icon: BellRing,
    title: "Monitoring & alerts",
    text: "Six rules flag crashes, daily shocks, incentive-heavy structures, depegs and stale upstream data. Idempotent per protocol, rule and day, fanned out to Slack, Discord, Telegram, email or a webhook.",
  },
  {
    icon: MessageSquareText,
    title: "Ask the analyst",
    text: "Grounded Q&A over the methodology and each protocol's own evidence. Every answer cites numbered sources, or refuses when nothing relevant was retrieved.",
  },
] as const;

const PIPELINE = [
  {
    title: "Ingest",
    text: "DefiLlama packs normalize to a daily, forward-filled UTC frame; Dune adds four contract-level activity metrics per chain, per day, only when both a key and a query id exist.",
  },
  {
    title: "Score",
    text: "Each indicator maps its anchors onto 0 to 100 and carries a weight. Anything that cannot be computed leaves the composite and is listed under data_gaps instead.",
  },
  {
    title: "Monitor",
    text: "A scheduled pass re-scores the watchlist, fires the rules with the metric, value and threshold that triggered them, and notifies whichever channels you configured.",
  },
] as const;

const NON_CLAIMS = [
  "It never calls a protocol healthy because TVL rose. A surge asks you to verify whether emissions caused it.",
  "It gives no investment advice and makes no buy, sell or avoid call. It names what to check next.",
  "It does not read a smart contract, detect wash trading, or treat an audit count as proof of safety.",
  "It will not invent a figure when a feed is missing. A gap is drawn as a gap, never as a reassuring zero.",
] as const;

/** Live coverage figures. A null means the read could not be made, which is
 *  shown as a single honest reason plus `n/a` cells, not a wall of zeros.
 *  This runs on the server inside a Suspense boundary: it is the one dynamic
 *  region on an otherwise static page, so a cold backend streams `n/a` instead
 *  of blocking the hero or failing the build. */
async function CoverageBand() {
  const coverage = await fetchCoverage();
  const tracked = coverage ? fmtCount(coverage.protocols_tracked) : "n/a";
  const scored = coverage ? fmtCount(coverage.scored_observations) : "n/a";
  const days = coverage ? fmtCount(coverage.observation_days) : "n/a";
  const cats = coverage ? fmtCount(coverage.categories) : "n/a";
  const chains = coverage ? fmtCount(coverage.chains) : "n/a";
  const alerts7d = coverage ? fmtCount(coverage.alerts_7d) : "n/a";
  const chunks = coverage ? fmtCount(coverage.index_chunks) : "n/a";
  const cadence = coverage ? `${coverage.monitor_interval_minutes} min` : "n/a";

  const stats = [
    { value: tracked, label: "protocols tracked", note: "Every protocol with a snapshot in the store right now." },
    { value: scored, label: "scored observations", note: "Protocol-days the risk model has actually ranked." },
    { value: days, label: "days of history", note: "Distinct observation dates behind the trend charts." },
    { value: cats, label: "categories", note: "Distinct DeFi verticals currently on the watchlist." },
    { value: chains, label: "chains", note: "Real chains represented across tracked protocols." },
    { value: alerts7d, label: "alerts in 7 days", note: "Rules that fired this week, across the whole watchlist." },
    { value: chunks, label: "retrieval chunks", note: "The corpus the grounded analyst answers from." },
    { value: cadence, label: "monitor pass", note: "How often the scheduler re-scores the watchlist." },
  ] as const;

  const asOf = coverage?.as_of ?? coverage?.captured_at ?? null;

  return (
    <section className="ds-section ds-section-raise ds-stats-band" aria-labelledby="coverage-h">
      <div className="ds-section-inner">
        <p className="ds-eyebrow">
          <Database size={13} strokeWidth={1.8} aria-hidden="true" />
          Live coverage
        </p>
        <h2 className="ds-h2 ds-h2-sm" id="coverage-h">
          These are the numbers the service is holding <em>right now</em>.
        </h2>
        <p className="ds-lede">
          Read straight from the running database through the public
          <code className="ds-inline-code"> /api/status </code>
          aggregate. Nothing here is a stock figure pasted into a template.
        </p>

        {coverage === null ? (
          <p className="ds-note" role="status">
            <span className="ds-note-label">Not connected</span>
            The board is not reachable from this page right now, so every figure
            below reads <code className="ds-inline-code">n/a</code>. It is shown as
            a gap, not as zero, exactly as the product treats a missing feed.
          </p>
        ) : coverage.status === "empty" ? (
          <p className="ds-note" role="status">
            <span className="ds-note-label">Fresh store</span>
            The database answered, but no snapshots have been captured yet. The
            counts below are real zeros, and the first monitor pass will fill them.
          </p>
        ) : null}

        <dl className="ds-stats">
          {stats.map(({ value, label, note }) => (
            <div className="ds-stat" key={label}>
              <dt className="ds-stat-label">{label}</dt>
              <dd className="ds-stat-num">{value}</dd>
              <dd className="ds-stat-note">{note}</dd>
            </div>
          ))}
        </dl>

        <p className="ds-coverage-meta">
          {coverage ? (
            <>
              {"Snapshot as of "}
              <code className="ds-inline-code">
                {asOf ? new Date(asOf).toISOString().slice(0, 16).replace("T", " ") : "n/a"}
              </code>
              {" UTC. "}
              <Link className="ds-inline-link" href={LINKS.docs}>
                How coverage is measured
                <ArrowRight size={13} strokeWidth={2} aria-hidden="true" />
              </Link>
            </>
          ) : (
            <>
              <Link className="ds-inline-link" href={LINKS.docs}>
                Read the methodology
                <ArrowRight size={13} strokeWidth={2} aria-hidden="true" />
              </Link>
            </>
          )}
        </p>
      </div>
    </section>
  );
}

/** The static placeholder streamed while the coverage read resolves. It carries
 *  the band's shape so the page does not jump when the numbers arrive, and every
 *  cell starts at `n/a`: if the read never resolves, the fallback itself is an
 *  honest answer, not a lie of zeros. */
function CoverageBandFallback() {
  return (
    <section className="ds-section ds-section-raise ds-stats-band" aria-busy="true">
      <div className="ds-section-inner">
        <p className="ds-eyebrow">
          <Database size={13} strokeWidth={1.8} aria-hidden="true" />
          Live coverage
        </p>
        <h2 className="ds-h2 ds-h2-sm">Counting what the service is holding.</h2>
        <p className="ds-lede">
          Reading the live aggregate. A gap shows as <code className="ds-inline-code">n/a</code>, never as zero.
        </p>
      </div>
    </section>
  );
}

export function DeFiScopeLanding() {
  return (
    // `data-landing` ships in the server HTML on purpose: it is what holds the
    // hero back until the fonts are ready. `LandingReveal` only flips the value.
    <div className="ds-root" id="landing-root" data-landing="pending">
      <LandingReveal />

      <a className="ds-skip" href="#hero">
        Skip to content
      </a>

      <LandingNav current="home" anchors={{ platform: "#platform", how: "#how" }} />

      <main>
        <section className="ds-hero" id="hero">
          <LandingFilm />

          <div className="ds-tint" aria-hidden="true" />

          <div className="ds-hero-inner">
            <h1 className="ds-h1">
              <span className="ds-ln">
                <span className="ds-ln-inner">Protocol risk,</span>
              </span>
              <span className="ds-ln">
                <span className="ds-ln-inner">explained.</span>
              </span>
            </h1>

            <p className="ds-sub">
              Seven weighted indicators, scored from live DefiLlama data,
              <br />
              each one shipped with its evidence and what it cannot establish,
              <br />
              so a missing feed stays a gap, never a reassuring zero.
            </p>

            <div className="ds-ctas">
              <Link className="ds-btn ds-btn-lg ds-btn-primary" href={LINKS.board}>
                Open the board
                <Arrow className="ds-arrow" />
              </Link>
              <a className="ds-btn ds-btn-lg ds-btn-ghost" href="#how">
                See how it works
                <Arrow className="ds-arrow" />
              </a>
            </div>
          </div>
        </section>

        <Suspense fallback={<CoverageBandFallback />}>
          <CoverageBand />
        </Suspense>

        <section className="ds-section" id="platform">
          <div className="ds-section-inner">
            <p className="ds-eyebrow">Platform</p>
            <h2 className="ds-h2">
              One board for the whole
              <br />
              <em>due-diligence</em> pass.
            </h2>
            <p className="ds-lede">
              A scored market board, per-protocol evidence, rule-based monitoring
              and a grounded analyst: four views over the same numbers. Every
              figure traces back to a pure function with a test behind it, not to
              a model&apos;s guess.
            </p>

            <ul className="ds-cards">
              {CAPABILITIES.map(({ icon: Icon, title, text }) => (
                <li className="ds-card" key={title}>
                  <span className="ds-card-icon" aria-hidden="true">
                    <Icon size={19} strokeWidth={1.6} />
                  </span>
                  <h3 className="ds-card-title">{title}</h3>
                  <p className="ds-card-text">{text}</p>
                </li>
              ))}
            </ul>

            <p className="ds-paragraph">
              The full manual now lives in the product, not in a Swagger page.
              <Link className="ds-inline-link" href={LINKS.docs}>
                Read the documentation
                <ArrowRight size={13} strokeWidth={2} aria-hidden="true" />
              </Link>
            </p>
          </div>
        </section>

        <section className="ds-section ds-section-raise" id="how">
          <div className="ds-section-inner">
            <p className="ds-eyebrow">Anatomy of a score</p>
            <h2 className="ds-h2">
              Seven signals, and what each one <em>cannot</em> prove.
            </h2>
            <p className="ds-lede">
              The composite is a weighted mean over the indicators that could be
              computed. Their weights sum to 1.00, and no single one decides a band
              alone. The right-hand column is the reason the table exists.
            </p>

            <div className="ds-table-wrap" role="region" aria-label="Indicator weights, anchors and limitations" tabIndex={0}>
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
                  {INDICATORS.map((ind) => (
                    <tr key={ind.key}>
                      <th scope="row">{ind.name}</th>
                      <td className="ds-td-weight">{ind.weight}</td>
                      <td className="ds-td-anchor">{ind.anchor}</td>
                      <td className="ds-td-cannot">{ind.cannot}</td>
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

            <p className="ds-paragraph">
              The thresholds and the full anchor spans are documented.
              <Link className="ds-inline-link" href={LINKS.docs_scoring}>
                See the scoring reference
                <ArrowRight size={13} strokeWidth={2} aria-hidden="true" />
              </Link>
            </p>
          </div>
        </section>

        <section className="ds-section" id="monitoring">
          <div className="ds-section-inner">
            <p className="ds-eyebrow">
              <BellRing size={13} strokeWidth={1.8} aria-hidden="true" />
              Monitoring
            </p>
            <h2 className="ds-h2">
              Six rules, each storing the value that <em>made it fire.</em>
            </h2>
            <p className="ds-lede">
              An alert is a claim you can check, not a vibe: it keeps the metric it
              watched, the observed value and the threshold. Ids are deterministic
              per protocol, rule and day, so a re-run cannot duplicate a finding.
            </p>

            <div className="ds-table-wrap" role="region" aria-label="Monitoring rules" tabIndex={0}>
              <table className="ds-table">
                <thead>
                  <tr>
                    <th scope="col">Rule</th>
                    <th scope="col">Severity</th>
                    <th scope="col">Fires when</th>
                    <th scope="col">Default</th>
                  </tr>
                </thead>
                <tbody>
                  {RULES.map((r) => (
                    <tr key={r.rule}>
                      <th scope="row">
                        <code className="ds-inline-code">{r.rule}</code>
                      </th>
                      <td>{r.severity}</td>
                      <td>{r.trigger}</td>
                      <td className="ds-td-weight">{r.value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <section className="ds-section ds-section-raise" id="data">
          <div className="ds-section-inner">
            <p className="ds-eyebrow">
              <Database size={13} strokeWidth={1.8} aria-hidden="true" />
              Data and its limits
            </p>
            <h2 className="ds-h2">
              Two providers, and no source <em>without its weakness.</em>
            </h2>
            <p className="ds-lede">
              A source that cannot answer a question is named as unable, not quietly
              dropped. TVL is USD-denominated, so it moves with price as well as
              usage: the caveat that bounds every indicator on this page.
            </p>

            <ul className="ds-sources">
              {SOURCES.map((s) => (
                <li className="ds-source" key={s.name}>
                  <span className="ds-source-name">{s.name}</span>
                  <p className="ds-source-used">
                    <span className="ds-tag">Used for</span>
                    {s.usedFor}
                  </p>
                  <p className="ds-source-limit">
                    <span className="ds-tag ds-tag-warn">Limitation</span>
                    {s.limit}
                  </p>
                </li>
              ))}
            </ul>

            <div className="ds-how-grid">
              <ol className="ds-steps">
                {PIPELINE.map(({ title, text }) => (
                  <li className="ds-step" key={title}>
                    <h3 className="ds-step-title">{title}</h3>
                    <p className="ds-step-text">{text}</p>
                  </li>
                ))}
              </ol>

              <pre className="ds-code" aria-label="Shape of the public aggregate status response">
                <code>
                  <span className="ds-code-line">
                    <span className="ds-code-verb">GET</span> /api/status
                  </span>
                  <span className="ds-code-line"> </span>
                  <span className="ds-code-line">{"{"}</span>
                  <span className="ds-code-line">
                    {"  "}
                    <span className="ds-code-key">{'"status"'}</span>:{" "}
                    <span className="ds-code-str">{'"ok"'}</span>,
                  </span>
                  <span className="ds-code-line">
                    {"  "}
                    <span className="ds-code-key">{'"protocols_tracked"'}</span>: {""}
                    <span className="ds-code-str">64</span>,
                  </span>
                  <span className="ds-code-line">
                    {"  "}
                    <span className="ds-code-key">{'"scored_observations"'}</span>: {""}
                    <span className="ds-code-str">1820</span>,
                  </span>
                  <span className="ds-code-line">
                    {"  "}
                    <span className="ds-code-key">{'"monitor_interval_minutes"'}</span>:{" "}
                    <span className="ds-code-str">30</span>,
                  </span>
                  <span className="ds-code-line">
                    {"  "}
                    <span className="ds-code-key">{'"as_of"'}</span>: {""}
                    <span className="ds-code-str">{'"2026-10-30"'}</span>
                  </span>
                  <span className="ds-code-line">{"}"}</span>
                </code>
              </pre>
            </div>
          </div>
        </section>

        <section className="ds-section" id="limits">
          <div className="ds-section-inner">
            <p className="ds-eyebrow">Honest limits</p>
            <h2 className="ds-h2">
              What it will <em>not</em> claim.
            </h2>
            <p className="ds-lede">
              The same honesty that keeps a missing feed a gap bounds what a result
              can be. These are out of scope by design, not by omission, and every
              one of them surfaces in the product as a named data gap.
            </p>

            <ul className="ds-limits">
              {NON_CLAIMS.map((line) => (
                <li className="ds-limit" key={line}>
                  <span>{line}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="ds-section ds-contact" id="contact">
          <div className="ds-contact-inner">
            <h2 className="ds-contact-title">
              It flags the reason to investigate.
            </h2>
            <p className="ds-contact-text">
              DeFiScope never calls a protocol healthy because TVL rose. It scores
              what it can measure, shows what it could not, and tells you what to
              check next.
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
              <Link className="ds-btn ds-btn-ghost" href={LINKS.about}>
                The long-form About
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
