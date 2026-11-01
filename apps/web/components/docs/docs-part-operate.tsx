import {
  ENDPOINTS,
  ENV_VARS,
  GLOSSARY,
  POLICIES,
  ROLES,
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
   Sections 14 to 18: the reference. The endpoint table is the HTTP surface from
   `app/routers/` mounted in `main.py`; the verbs and policies are from
   `security/rbac.py` and `security/policy.py`; the environment defaults are from
   `config.py`. This is the part a reader consults to check a fact, so it stays
   literal and marks the values that must never reach a browser.
   ========================================================================= */

const API_CONVENTIONS = [
  "One OpenAPI document is the contract. The web tier compiles against types generated from it (`make gen-types`), and CI fails if the schema and the types drift, so the two halves cannot disagree quietly.",
  "Prefixes are grouped by router: `/api/auth`, `/api/protocols`, `/api/alerts` and `/api/briefs` are mounted with their own prefix; the dashboard, chat and status endpoints carry absolute paths. Every payload is JSON with an `as_of` marking the newest underlying observation.",
  "Health and readiness are separate probes. `/api/health` always returns 200 with the database state inside it, so liveness is not confused with serving; `/api/health/ready` returns 503 until the database answers, which is what an orchestrator gates on.",
  "Aggregate coverage is public at `/api/status`. It exposes counts and configuration booleans (`llm_configured`, `onchain_configured`), never row-level data and never a secret value, so the landing page can show real numbers without a session.",
  "Authenticated reads are marked no-store and excluded from the framework's shared cache, so one subject's scope-filtered board can never be replayed to another.",
] as const;

function Api() {
  return (
    <DocsSection n={14} id="api" eyebrow="Reference" title="API reference">
      <Lead>
        {"The whole surface is a documented REST API with one machine-readable contract. The table below is the human view; the Swagger page and the open schema are the ones a client generates against."}
      </Lead>

      <DocsSub id="api-conventions">{"Conventions"}</DocsSub>
      <ul className="ds-ticks">
        {API_CONVENTIONS.map((line, i) => (
          <li className="ds-tick" key={i}>
            <span>{line}</span>
          </li>
        ))}
      </ul>

      <DocsSub id="api-endpoints">{"Endpoints"}</DocsSub>
      <P>
        {"Twenty routes, and the "}
        <Code>{"auth"}</Code>
        {" column is the verb from "}
        <Code>{"security/rbac.py"}</Code>
        {" a caller must hold, or public for the three probes."}
      </P>
      <DocTable
        caption="Endpoints, their methods, required auth and purpose"
        head={["Method", "Path", "Auth", "What it does"]}
        wide
      >
        {ENDPOINTS.map((e) => (
          <tr key={`${e.method} ${e.path}`}>
            <th scope="row" className="ds-td-method">
              {e.method}
            </th>
            <td className="ds-td-path">
              <Code>{e.path}</Code>
            </td>
            <td>{e.auth}</td>
            <td>{e.what}</td>
          </tr>
        ))}
      </DocTable>

      <DocsSub id="api-errors">{"Errors and denials"}</DocsSub>
      <P>
        {"A failure is a structured object, never a bare string, so a client can branch on the cause without parsing prose. A 401 reads "}
        <Code>{"{error: \"unauthorized\", reason}"}</Code>
        {". A 403 from an attribute policy reads "}
        <Code>{"{error, policy, reason, failed_predicate}"}</Code>
        {", where "}
        <Code>{"policy"}</Code>
        {" is the same stable id this manual names and "}
        <Code>{"failed_predicate"}</Code>
        {" names the attribute that could not be satisfied. A role that simply lacks a verb adds a "}
        <Code>{"permission"}</Code>
        {" field."}
      </P>
      <Note label={"Withheld, not hidden"}>
        <P>
          {"Where a clearance gate removes rows rather than blocking the call, the response keeps the count of what was withheld. A filtered feed is never allowed to read as an empty one, and \"nothing to show\" is never the same message as \"you may not see this.\""}
        </P>
      </Note>
    </DocsSection>
  );
}

const AUTH_MODES = [
  { name: "off", text: "No authentication. Reproduces the pre-auth open demo; for a showcase you fully control, never a deployment." },
  { name: "demo", text: "The default. Seeds four local identities and enables the role switcher so a visitor can watch a permission change the board. The demo password is published on purpose." },
  { name: "required", text: "Login is mandatory and nothing is seeded. This is the mode for anything real." },
] as const;

function Auth() {
  return (
    <DocsSection n={15} id="auth" eyebrow="Reference" title="Access model">
      <Lead>
        {"Roles grant verbs; attributes decide which records those verbs reach. Splitting the two is what lets a new team scope be added without inventing a new role, and what lets a denial be explained instead of merely delivered."}
      </Lead>

      <DocsSub id="auth-roles">{"Roles"}</DocsSub>
      <DocTable caption="Roles and the verbs each grants" head={["Role", "Verbs"]} wide>
        {ROLES.map((r) => (
          <tr key={r.role}>
            <th scope="row">
              <Code>{r.role}</Code>
            </th>
            <td>{r.verbs}</td>
          </tr>
        ))}
      </DocTable>

      <DocsSub id="auth-abac">{"Attribute policies"}</DocsSub>
      <P>
        {"Five predicates run behind the verb gate, each in "}
        <Code>{"security/policy.py"}</Code>
        {". The id is the same string that appears in a denial and a log line, so this table, a 403 body and the audit trail all name one rule."}
      </P>
      <DocTable
        caption="ABAC policies, when they fire and how the denial is shaped"
        head={["Policy id", "Fires when", "Shape of the response"]}
        wide
      >
        {POLICIES.map((p) => (
          <tr key={p.id}>
            <th scope="row">
              <Code>{p.id}</Code>
            </th>
            <td>{p.fires}</td>
            <td>{p.shape}</td>
          </tr>
        ))}
      </DocTable>

      <DocsSub id="auth-modes">{"Auth modes"}</DocsSub>
      <P>
        {"Set by "}
        <Code>{"DEFISCOPE_AUTH_MODE"}</Code>
        {". The middleware redirect in the web tier is a courtesy, not the control: the API re-authorizes every request, so a visitor who types the port instead of the URL gets a 401 rather than a dashboard."}
      </P>
      <ul className="ds-limits">
        {AUTH_MODES.map((m) => (
          <li className="ds-limit" key={m.name}>
            <Code>{m.name}</Code>
            <span>{m.text}</span>
          </li>
        ))}
      </ul>
    </DocsSection>
  );
}

function Config() {
  return (
    <DocsSection n={16} id="config" eyebrow="Reference" title="Configuration">
      <Lead>
        {"Behaviour is environment driven, every variable carrying the "}
        <Code>{"DEFISCOPE_"}</Code>
        {" prefix. The default column is what the code in "}
        <Code>{"config.py"}</Code>
        {" falls back to when the variable is absent, so a stack with no env file still runs."}
      </Lead>

      <DocsSub id="config-env">{"Environment variables"}</DocsSub>
      <P>
        {"The rows marked "}
        <Code>{"secret"}</Code>
        {" must never be published to the browser. The public API only ever reports whether such a feature is switched on, as a boolean, not the value behind it."}
      </P>
      <DocTable
        caption="Selected environment variables, their defaults and notes"
        head={["Variable", "Default", "Note"]}
        wide
      >
        {ENV_VARS.map((v) => (
          <tr key={v.name}>
            <th scope="row">
              <Code>{v.name}</Code>
              {v.secret ? (
                <span className="ds-tag ds-tag-warn" style={{ marginLeft: 8 }}>
                  {"secret"}
                </span>
              ) : null}
            </th>
            <td className="ds-td-weight">
              <Code>{v.def}</Code>
            </td>
            <td>{v.note}</td>
          </tr>
        ))}
      </DocTable>
      <Note label={"What is deliberately not a variable"}>
        <P>
          {"The indicator anchors and weights live in the scoring module, not the environment. Rule thresholds are configuration; what a score means is a code review. Changing a weight should be visible in a diff, not hidden in a deployment value."}
        </P>
      </Note>
    </DocsSection>
  );
}

const NON_CLAIMS = [
  "No wash-trading or sybil detection: that needs transaction-level classification this pipeline does not do.",
  "No token emission-schedule analysis: it is not in the free DefiLlama endpoints.",
  "No per-protocol price-normalized TVL on the board yet: the decomposition is written and tested but needs a reliable protocol-to-token map before it is shown rather than approximated.",
  "Peg watch covers only the stablecoins in the curated map, against a $1.00 target; it does not model collateral or redemption, and a coin outside the map reads as not assessed.",
  "Security posture is a weak proxy: an audit count is a prompt for manual review, never a guarantee of safety.",
  "No smart-contract audit and no incident forensics.",
  "No investment advice: it tells you what to check next, not what to buy.",
  "Retrieval bounds the chat: it can only explain what the pipeline already measured, and it inherits every limit above.",
] as const;

function Limits() {
  return (
    <DocsSection n={17} id="limits" eyebrow="Reference" title="Limitations">
      <Lead>
        {"The boundaries, written as a list you can hold the product to. Each is surfaced in the interface as a "}
        <Code>{"data_gaps"}</Code>
        {" entry rather than smoothed over, because a tool that hides its edges eventually presents a guess as a finding."}
      </Lead>

      <DocsSub id="limits-list">{"What DeFiScope will not claim"}</DocsSub>
      <ul className="ds-limits">
        {NON_CLAIMS.map((line) => (
          <li className="ds-limit" key={line}>
            <span>{line}</span>
          </li>
        ))}
      </ul>
      <P>
        {"Two readings matter more than the list. A low band means low risk on the dimensions TVL data can observe, not a clean bill of health. And "}
        <Code>{"n/a"}</Code>
        {" means the series does not exist, a statement about the data, not the protocol. Confusing those two is how a dashboard becomes a liability."}
      </P>
    </DocsSection>
  );
}

function Glossary() {
  return (
    <DocsSection n={18} id="glossary" eyebrow="Reference" title="Glossary">
      <Lead>
        {"The terms this manual and the product use, defined in the product's own words."}
      </Lead>
      <dl className="ds-gloss">
        {GLOSSARY.map((t) => (
          <div className="ds-gloss-item" key={t.term}>
            <dt className="ds-gloss-term">
              <Code>{t.term}</Code>
            </dt>
            <dd className="ds-gloss-def">{t.def}</dd>
          </div>
        ))}
      </dl>
    </DocsSection>
  );
}

export function OperateSections() {
  return (
    <>
      <Api />
      <Auth />
      <Config />
      <Limits />
      <Glossary />
    </>
  );
}
