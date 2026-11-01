import { Check, X } from "lucide-react";

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
   Sections 1 to 3: what the product is, how to stand it up, and the four views
   a signed-in reader lands on. Every command is copied from the repo README and
   the root Makefile; every account from security/seed.py. Nothing here is a
   capability the backend does not implement.
   ========================================================================= */

const DOES = [
  "Scores protocol risk from public TVL, fee, volume and price data, and shows the arithmetic",
  "Flags crashes, one-day shocks, surges, depegs, incentive-heavy structures and stale feeds on a schedule",
  "Answers questions only from its own methodology and a protocol's captured evidence, or refuses",
  "States, next to every number, what that number cannot establish",
] as const;

const DOES_NOT = [
  "Give investment advice or tell you to buy, sell or avoid anything",
  "Read a smart contract, or treat an audit count as proof of safety",
  "See a wallet's owner, wash trading, or sybil activity; it counts aggregates, not identities",
  "Invent a figure when a feed is missing: a gap is drawn as a gap, never as zero",
] as const;

function Overview() {
  return (
    <DocsSection n={1} id="overview" eyebrow="Start here" title="What DeFiScope measures">
      <Lead>
        {"DeFiScope AI is a research tool that turns raw DeFi aggregates into an explainable risk score, a monitored watchlist and grounded answers, and it says out loud what each of those cannot prove."}
      </Lead>
      <P>
        {"It reads live data from DefiLlama, with Dune as an optional second provider, normalizes it to a daily frame, and runs a small set of pure, documented functions over it. The result is one composite number per protocol plus the seven indicators that produced it, the evidence behind each, and the limitation each carries."}
      </P>

      <DocsSub id="overview-in-one-line">{"In one line"}</DocsSub>
      <P>
        {"Answer three questions for any protocol: is its growth sustainable or incentive- and price-driven, what are its liquidity, concentration and security exposures, and what should an analyst check next."}
      </P>
      <ul className="ds-ticks">
        {DOES.map((line) => (
          <li className="ds-tick" key={line}>
            <Check size={17} strokeWidth={2} aria-hidden="true" />
            <span>{line}</span>
          </li>
        ))}
      </ul>

      <DocsSub id="overview-what-it-is-not">{"What it is not"}</DocsSub>
      <P>
        {"The same honesty that keeps a missing feed a gap also bounds what a claim can be. These are out of scope by design, not by omission."}
      </P>
      <ul className="ds-limits">
        {DOES_NOT.map((line) => (
          <li className="ds-limit" key={line}>
            <X size={17} strokeWidth={2} aria-hidden="true" />
            <span>{line}</span>
          </li>
        ))}
      </ul>
      <Note label={"The one rule"}>
        <P>
          {"A value is either measured or missing. "}
          <Code>{"n/a"}</Code>
          {" means it could not be measured; "}
          <Code>{"0"}</Code>
          {" means it was measured and there were none. The interface never collapses the two, and neither should you read them as the same thing."}
        </P>
      </Note>
    </DocsSection>
  );
}

function Command({ n, children }: { n: string; children: string }) {
  return (
    <div className="ds-docs-step">
      <span className="ds-docs-step-n">{n}</span>
      <code className="ds-docs-step-c">{children}</code>
    </div>
  );
}

const DEMO_ACCOUNTS = [
  { email: "viewer@demo", role: "viewer", clearance: "1", shows: "Read-only. Critical alerts are counted but withheld." },
  { email: "analyst@demo", role: "analyst", clearance: "1", shows: "Board and pages filtered to a Lending and Dexes slice." },
  { email: "officer@demo", role: "risk_officer", clearance: "2", shows: "Unlocks critical-alert content and low-confidence export." },
  { email: "admin@demo", role: "admin", clearance: "3", shows: "Every permission, including a forced monitoring pass." },
] as const;

function GettingStarted() {
  return (
    <DocsSection n={2} id="getting-started" eyebrow="Start here" title="Run the stack">
      <Lead>
        {"One command brings up the API, the web app and a database. The whole model runs without a single API key, because DefiLlama is a public endpoint."}
      </Lead>

      <DocsSub id="start-requirements">{"What you need"}</DocsSub>
      <P>
        {"For the container path, Docker with the Compose plugin. For running from source, the Python package manager uv and Node 20 or newer. That is all: no cloud account is required to see the board."}
      </P>

      <DocsSub id="start-compose">{"Start with Docker"}</DocsSub>
      <P>
        {"Compose builds three services and wires them together: web on port 4000, the API on port 3646, and Postgres. Open the web port and sign in."}
      </P>
      <div className="ds-docs-steps">
        <Command n="1">{"docker compose up --build"}</Command>
        <Command n="2">{"# web app: http://localhost:4000"}</Command>
        <Command n="3">{"# API docs: http://localhost:3646/docs"}</Command>
      </div>

      <DocsSub id="start-local">{"Run it from source"}</DocsSub>
      <P>
        {"Two processes, two terminals, or the repo-root Makefile wrappers. The API serves on 8000 and the Next dev server on 3000 and calls it server-side."}
      </P>
      <div className="ds-docs-steps">
        <Command n="1">{"make install        # uv sync + npm install"}</Command>
        <Command n="2">{"make api-dev        # FastAPI on :8000, autoreload"}</Command>
        <Command n="3">{"make web-dev        # Next.js on :3000"}</Command>
        <Command n="4">{"make check          # lint + typecheck + tests"}</Command>
      </div>

      <DocsSub id="start-env">{"Optional keys"}</DocsSub>
      <P>
        {"Copy the example env and set only what you want to light up. Each feature stays a labelled gap until its own input exists, so a half-configured stack still runs."}
      </P>
      <div className="ds-docs-steps">
        <Command n="1">{"cp .env.example services/api/.env"}</Command>
        <Command n="2">{"# DEFISCOPE_OPENAI_API_KEY   -> LLM briefs and chat"}</Command>
        <Command n="3">{"# DEFISCOPE_DUNE_API_KEY     -> on-chain activity (with query id)"}</Command>
        <Command n="4">{"# DEFISCOPE_SLACK_WEBHOOK_URL and friends -> alert delivery"}</Command>
      </div>
      <Note label={"Demo logins"}>
        <P>
          {"The showcase seeds four local accounts under "}
          <Code>{"DEFISCOPE_AUTH_MODE=demo"}</Code>
          {", all sharing the published demo password. Switch roles from the header avatar to watch a permission change what the board shows. See "}
          <a href="#auth" className="ds-inline-code" style={{ textDecoration: "none" }}>
            {"the access model"}
          </a>
          {" for what each role unlocks."}
        </P>
      </Note>
      <DocTable
        caption="Seeded demo accounts and what each demonstrates"
        head={["Account", "Role", "Clearance", "What it shows"]}
      >
        {DEMO_ACCOUNTS.map((a) => (
          <tr key={a.email}>
            <th scope="row">{a.email}</th>
            <td>{a.role}</td>
            <td>{a.clearance}</td>
            <td>{a.shows}</td>
          </tr>
        ))}
      </DocTable>
    </DocsSection>
  );
}

const TOUR = [
  {
    id: "tour-board",
    title: "The board",
    body: "The landing view of a signed-in session: every protocol on the watchlist as a row, sortable by TVL, 7-day and 30-day change, volatility, fees, DEX volume, chain concentration and risk band. It reads from daily snapshots in the database first and only reaches for a live crawl when the newest snapshot is older than the staleness window.",
  },
  {
    id: "tour-protocol",
    title: "A protocol",
    body: "One protocol opened into its full research pack: the composite and its band, the seven indicator cards each with value, score, evidence and limitation, the data gaps listed by name, the TVL and risk history charts, and any on-chain activity captured for it. This is where the arithmetic is shown rather than asserted.",
  },
  {
    id: "tour-alerts",
    title: "Alerts",
    body: "Today's fired rules and the persisted log. Each alert names its metric, the observed value and the threshold that triggered it. Where your clearance withholds a critical row, the count of what was withheld stays visible, so a filtered feed is never mistaken for an empty one.",
  },
  {
    id: "tour-ask",
    title: "Ask",
    body: "A grounded question box. It answers from the methodology and the protocol's own captured evidence, cites numbered sources, and refuses when nothing relevant was retrieved. It streams over a WebSocket when one is available and falls back to a single request when it is not.",
  },
] as const;

function Tour() {
  return (
    <DocsSection n={3} id="tour" eyebrow="Start here" title="The five-minute tour">
      <Lead>
        {"Four views over one set of numbers. None of them invents a figure the pipeline did not produce."}
      </Lead>
      {TOUR.map((t) => (
        <div key={t.id}>
          <DocsSub id={t.id}>{t.title}</DocsSub>
          <P>{t.body}</P>
        </div>
      ))}
    </DocsSection>
  );
}

export function StartSections() {
  return (
    <>
      <Overview />
      <GettingStarted />
      <Tour />
    </>
  );
}
