import {
  CHANNELS,
  ONCHAIN_FIELDS,
  ONCHAIN_STATUSES,
  RULES,
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
   Sections 9 to 13: the monitoring and research surface. The rules and channels
   are read from `config.py` and `services/alerts.py`; the on-chain fields from
   `services/onchain.py`; the chat outcomes and the export gate from the RAG
   module and `security/policy.py`. Each carries the limitation that makes it
   honest rather than merely impressive.
   ========================================================================= */

function Rules() {
  return (
    <DocsSection n={9} id="rules" eyebrow="Monitoring and research" title="Alert rules">
      <Lead>
        {"Six rules run on the scheduler. Each one stores the metric it watched, the value it observed and the threshold that fired, so an alert is a claim you can check rather than a vibe."}
      </Lead>

      <DocsSub id="rules-table">{"The six rules"}</DocsSub>
      <P>
        {"The thresholds are environment driven under the "}
        <Code>{"DEFISCOPE_ALERT_*"}</Code>
        {" names; the defaults below are what "}
        <Code>{"config.py"}</Code>
        {" falls back to. A critical severity is reached when the observed value is twice the trigger, except the daily shock, which is critical on sight."}
      </P>
      <DocTable
        caption="Monitoring rules, their triggers and thresholds"
        head={["Rule", "Severity", "Fires when", "Default"]}
        wide
      >
        {RULES.map((r) => (
          <tr key={r.rule}>
            <th scope="row">
              <Code>{r.rule}</Code>
            </th>
            <td>{r.severity}</td>
            <td>{r.trigger}</td>
            <td className="ds-td-weight">{r.value}</td>
          </tr>
        ))}
      </DocTable>

      <DocsSub id="rules-idempotency">{"Idempotent per day"}</DocsSub>
      <P>
        {"An alert id is derived deterministically from the protocol slug, the rule and the UTC day. Re-running the pass the same day cannot duplicate a finding, and a delivery is sent once: after a channel notifies, a cooldown stamp keeps the same alert from re-pinging until it lapses."}
      </P>
      <Note label={"Why it matters"}>
        <P>
          {"A monitoring tool that re-fires the same crash an hour later trains its readers to ignore it. The idempotency is the difference between an alert and noise, and it is a property of the identity function in "}
          <Code>{"services/alerts.py"}</Code>
          {", not a UI courtesy."}
        </P>
      </Note>
    </DocsSection>
  );
}

function Delivery() {
  return (
    <DocsSection n={10} id="delivery" eyebrow="Monitoring and research" title="Delivery channels">
      <Lead>
        {"New alerts fan out to whichever sinks are configured. Nothing is on by default except the console, and each channel activates only when its own credential exists, so a half-configured stack still runs and still tells you where it looked."}
      </Lead>

      <DocsSub id="delivery-channels">{"Channels and their gates"}</DocsSub>
      <DocTable caption="Notifier channels and what activates each" head={["Channel", "Activates when"]} wide>
        {CHANNELS.map((c) => (
          <tr key={c.name}>
            <th scope="row">
              <Code>{c.name}</Code>
            </th>
            <td>{c.activates}</td>
          </tr>
        ))}
      </DocTable>
      <P>
        {"The list is set by "}
        <Code>{"DEFISCOPE_ALERT_NOTIFY_CHANNELS"}</Code>
        {", and a failure to deliver is logged rather than allowed to break the run: the snapshot and the alert record persist first, so a dead webhook loses a notification, not the finding."}
      </P>
    </DocsSection>
  );
}

const CALIBRATION =
  "On-chain activity is displayed, cited and monitored, but deliberately not scored. A risk weight needs a calibration story, and no replay over a resolved failure has yet shown that falling activity would have flagged it earlier than TVL already did. The bar for promoting it is written down in section 11 of the About page and in the methodology: a stretch of continuous history spanning real stress, a stated mechanism and direction, and a backtest that adds signal rather than re-flagging what the seven indicators already catch.";

function Onchain() {
  return (
    <DocsSection n={11} id="onchain" eyebrow="Monitoring and research" title="On-chain evidence">
      <Lead>
        {"Dune is an optional second provider that answers a question TVL cannot: how many addresses touched a protocol today. Four metrics, per tracked contract set, per UTC day, kept beside the rest of the picture and not folded into the score."}
      </Lead>

      <DocsSub id="onchain-fields">{"The four metrics"}</DocsSub>
      <DocTable caption="On-chain activity fields and their definitions" head={["Field", "Definition"]} wide>
        {ONCHAIN_FIELDS.map((f) => (
          <tr key={f.term}>
            <th scope="row">
              <Code>{f.term}</Code>
            </th>
            <td>{f.def}</td>
          </tr>
        ))}
      </DocTable>
      <Note label={"Two limits that always apply"}>
        <P>
          {"These count contract activity, not people, and the volume figure sums inbound legs only, so it is not DEX volume and must never be compared with the DefiLlama turnover beside it."}
        </P>
      </Note>

      <DocsSub id="onchain-status">{"Five states of a number"}</DocsSub>
      <P>
        {"The gap between configured and measured is where a second provider gets interesting, so each absence is named specifically rather than drawn as a dash. The status comes from "}
        <Code>{"services/onchain.py"}</Code>
        {":"}
      </P>
      <DocTable caption="On-chain availability statuses" head={["Status", "Meaning"]} wide>
        {ONCHAIN_STATUSES.map((s) => (
          <tr key={s.status}>
            <th scope="row">
              <Code>{s.status}</Code>
            </th>
            <td>{s.meaning}</td>
          </tr>
        ))}
      </DocTable>

      <DocsSub id="onchain-calibration">{"Why it is not scored"}</DocsSub>
      <P>{CALIBRATION}</P>
    </DocsSection>
  );
}

const ASK_OUTCOMES = [
  {
    engine: "llm",
    title: "Grounded prose",
    text: "A key is configured and the call succeeded. Each claim is tied to a numbered source, and the answer says what the retrieved context cannot establish.",
    when: "OpenAI-compatible key present and the relevance gate cleared.",
  },
  {
    engine: "extractive",
    title: "Verbatim evidence",
    text: "No key, or the model call failed. You get quoted passages from the corpus: nothing synthesized, nothing invented, the same sources.",
    when: "The default offline path; the demo never hard-depends on a model.",
  },
  {
    engine: "none",
    title: "A refusal",
    text: "No retrieved chunk cleared the gate, so the answer names what it cannot establish and lists the missing evidence instead of writing a paragraph.",
    when: "Off-topic questions, and questions the pipeline has no data for.",
  },
] as const;

const RETRIEVAL = [
  "Two kinds of chunks: documentation (methodology, architecture, the mechanics primer, the sample research, the curated security notes) split on heading and paragraph boundaries, and one evidence pack per protocol carrying its overview, each indicator's evidence and limitation, its gaps and its recent alerts.",
  "Ranking degrades honestly. With an embedding key, chunks rank by cosine similarity (pgvector on Postgres, in-process cosine on SQLite); with none, the same store ranks by Okapi BM25, k1 1.5 and b 0.75. Same top k, no external call.",
  "The gate knows which method ranked. Cosine and BM25 are not comparable scales, so the vector path requires a cosine floor of 0.5 while the lexical path requires the passage to share at least two distinct informative query terms after stopword removal.",
  "Provenance is in the primary key. A chunk id hashes document, section and body together, so unchanged text keeps a stable id across re-indexes while the same boilerplate under a different heading is a distinct row, not a collision.",
] as const;

function Ask() {
  return (
    <DocsSection n={12} id="ask" eyebrow="Monitoring and research" title="Ask the analyst">
      <Lead>
        {"The chat adds no new claims. It is a window onto the evidence the pipeline already produced: it can re-state it, cite it by number and admit what it cannot establish. It never overrides a data gap with a confident sentence."}
      </Lead>

      <DocsSub id="ask-retrieval">{"How retrieval works"}</DocsSub>
      <P>
        {"Questions are answered over a chunked corpus, ranked, gated and then either composed or quoted. The streaming path is a WebSocket (see "}
        <Code>{"POST /api/chat"}</Code>
        {" for the single-request fallback); the answer carries its citations, whether it is grounded, and which engine produced it, all as fields on the response rather than secrets in a log."}
      </P>
      <ul className="ds-ticks">
        {RETRIEVAL.map((line, i) => (
          <li className="ds-tick" key={i}>
            <span>{line}</span>
          </li>
        ))}
      </ul>

      <DocsSub id="ask-refusal">{"The three outcomes"}</DocsSub>
      <P>
        {"There is no fourth outcome where the system guesses. The engine value on a response is one of these three, and a refusal is a first-class answer, not an error."}
      </P>
      <ul className="ds-cards ds-cards-3">
        {ASK_OUTCOMES.map(({ engine, title, text, when }) => (
          <li className="ds-card ds-card-outcome" key={engine}>
            <span className="ds-engine">{engine}</span>
            <h4 className="ds-card-title">{title}</h4>
            <p className="ds-card-text">{text}</p>
            <p className="ds-when">{when}</p>
          </li>
        ))}
      </ul>
    </DocsSection>
  );
}

function Briefs() {
  return (
    <DocsSection n={13} id="briefs" eyebrow="Monitoring and research" title="Research briefs">
      <Lead>
        {"A brief is a structured write-up of one protocol assembled from the same evidence the score is built on, with a confidence label that changes what you are allowed to do with it."}
      </Lead>

      <DocsSub id="brief-confidence">{"Confidence and the export gate"}</DocsSub>
      <P>
        {"Every brief carries a "}
        <Code>{"confidence"}</Code>
        {" field and the list of "}
        <Code>{"data_gaps"}</Code>
        {" behind it. The read is always allowed to whoever can see the protocol. The export, as markdown, CSV or print-ready PDF, is gated: a low-confidence brief will not leave the tool looking settled unless a risk officer or admin signs it off."}
      </P>
      <Note label={"The policy, by name"}>
        <P>
          {"The gate is "}
          <Code>{"briefs.export.confidence_gate"}</Code>
          {". When it refuses, it answers 403 naming the gap count rather than silently returning an empty file, because a shaky document should not be downloadable as though it were finished. See "}
          <a href="#auth" className="ds-inline-code" style={{ textDecoration: "none" }}>
            {"the access model"}
          </a>
          {" for how a denial is shaped."}
        </P>
      </Note>
    </DocsSection>
  );
}

export function MonitorSections() {
  return (
    <>
      <Rules />
      <Delivery />
      <Onchain />
      <Ask />
      <Briefs />
    </>
  );
}
