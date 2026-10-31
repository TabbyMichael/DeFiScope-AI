import Link from "next/link";
import { Suspense } from "react";
import { notFound } from "next/navigation";
import { LockKeyhole } from "lucide-react";

import IndicatorCard from "@/components/IndicatorCard";
import RiskBadge from "@/components/RiskBadge";
import RiskTrendChart from "@/components/RiskTrendChart";
import TvlChart from "@/components/TvlChart";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import { fmtPct, fmtUsd } from "@/lib/api-config";
import { getSession, hasPermission, type Session } from "@/lib/auth";
import type { OnchainActivity, ProtocolResearch, ResearchBrief, RiskPoint } from "@/lib/types";

async function ProtocolContent({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const session = await getSession();
  let data: ProtocolResearch;
  let brief: ResearchBrief | null = null;
  let riskHistory: RiskPoint[] = [];
  try {
    data = await api.protocol(slug);
    try {
      brief = await api.brief(slug);
    } catch {
      brief = null; // brief generation failure must not break the research page
    }
    try {
      riskHistory = await api.riskHistory(slug);
    } catch {
      riskHistory = []; // trend is best-effort; no snapshots yet is not an error
    }
  } catch (e) {
    // An out-of-scope protocol is an authorization verdict, not a missing page.
    // Answering 404 would imply the protocol does not exist — the opposite of
    // what the policy actually decided.
    if (e instanceof ApiError && e.isDenial) {
      return <DenialPanel denial={e} />;
    }
    console.error("protocol page error", e);
    notFound();
  }

  const o = data.overview;
  const exportBlocked = briefExportGate(session, brief);
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <nav className="text-xs text-muted-foreground">
        <Link href="/" className="hover:text-foreground">
          ← Dashboard
        </Link>
      </nav>

      <header className="flex flex-wrap items-end justify-between gap-x-4 gap-y-3">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{data.name}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {data.category ?? "Uncategorized"} · source:{" "}
            {data.url ? (
              <a href={data.url} target="_blank" rel="noreferrer" className="underline hover:text-foreground">
                DefiLlama/{data.slug}
              </a>
            ) : (
              "DefiLlama"
            )}
          </p>
        </div>
        <div className="text-right">
          <div className="text-2xl font-semibold tabular-nums sm:text-3xl">{fmtUsd(o.tvl)}</div>
          <div className="mt-1 flex items-center justify-end gap-2 text-xs text-muted-foreground">
            <span>7d {fmtPct(o.change_7d)}</span>
            <span>·</span>
            <span>30d {fmtPct(o.change_30d)}</span>
            <span>·</span>
            <span>as of {data.as_of}</span>
          </div>
        </div>
      </header>

      {o.stale_days != null && o.stale_days > 1 && (
        <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-3 text-sm text-yellow-800 dark:text-yellow-300">
          Data freshness: the latest DefiLlama observation is {o.stale_days} days
          old. Treat conclusions as provisional.
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>TVL history (180d)</CardTitle>
        </CardHeader>
        <CardContent>
          <TvlChart data={data.tvl_series} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardDescription>Fees, revenue & volume (DefiLlama adapters)</CardDescription>
          <CardTitle>Economic activity</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            <Metric label="Fees (24h)" value={fmtUsd(o.fees_1d)} />
            <Metric label="Revenue (24h)" value={fmtUsd(o.revenue_1d)} />
            <Metric label="Volume (24h)" value={fmtUsd(o.volume_1d)} />
            <Metric label="Fees / TVL (30d)" value={fmtRatio(o.fees_tvl)} />
            <Metric label="Volume / TVL (30d)" value={fmtRatio(o.volume_tvl)} />
          </div>
          <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
            “n/a” means DefiLlama has no tracked series for this protocol. That is
            a data gap, not zero. A low fee/volume-to-TVL ratio can also reflect
            capital-efficient stores of value (liquid staking, stablecoins) rather
            than weak real yield.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardDescription>Dune-measured contract activity</CardDescription>
          <CardTitle>Network usage</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            <Metric label="Active wallets" value={fmtCount(data.onchain.active_wallets)} />
            <Metric label="Transactions" value={fmtCount(data.onchain.tx_count)} />
            <Metric label="Transfer volume" value={fmtUsd(data.onchain.tx_volume_usd)} />
            <Metric
              label="Returning wallets"
              value={fmtReturning(data.onchain.returning_wallets, data.onchain.returning_wallet_share)}
            />
          </div>
          <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
            These count activity at the protocol&apos;s tracked contracts, not
            unique users: a router or wrapper contract inflates the transaction
            count without meaning more people, and transfer volume counts inflows
            only, so the two legs of a swap are not both counted. Usage evidence,
            deliberately not an input to the composite score below.
          </p>
          <OnchainStatusLine activity={data.onchain} />
        </CardContent>
      </Card>

      {o.depeg_asset && (
        <Card>
          <CardHeader>
            <CardDescription>
              Stablecoin this protocol mints ({o.depeg_asset})
            </CardDescription>
            <CardTitle>Stablecoin peg watch</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
              <Metric label="Worst 30d peg deviation" value={fmtBps(o.depeg_worst_bps)} />
              <Metric label="Tracked coin" value={o.depeg_asset ?? "n/a"} />
            </div>
            <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
              Deviation from the $1.00 peg, measured from DefiLlama price history
              over the trailing window. A larger move means the coin traded away
              from its peg at some point. It is a prompt to verify the peg
              mechanism, not proof of an ongoing depeg. Protocols that mint no
              tracked stablecoin show nothing here.
            </p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex-row items-center gap-3 space-y-0">
          <div>
            <CardDescription>Weighted, explainable indicators</CardDescription>
            <CardTitle>Explainable risk assessment</CardTitle>
          </div>
          <div className="ml-auto">
            <RiskBadge score={data.risk.composite_score} band={data.risk.band} />
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 md:grid-cols-2">
            {data.risk.indicators?.map((i) => (
              <IndicatorCard key={i.key} indicator={i} />
            ))}
          </div>
          {data.data_gaps.length > 0 && (
            <p className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground">Data gaps: </span>
              {data.data_gaps.join(", ")}. Excluded from the composite rather than
              treated as &quot;safe&quot;.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardDescription>
            Composite score captured by the scheduler over time
          </CardDescription>
          <CardTitle>Risk-score trend</CardTitle>
        </CardHeader>
        <CardContent>
          <RiskTrendChart data={riskHistory} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>TVL by chain</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1.5">
          <div className="grid gap-3 sm:grid-cols-2">
            {data.chains.map((c) => (
              <div key={c.chain} className="flex min-w-0 items-center gap-3 text-sm">
                <span className="w-24 shrink-0 truncate text-muted-foreground sm:w-32">
                  {c.chain}
                </span>
                <div className="h-2 min-w-8 flex-1 overflow-hidden rounded bg-muted">
                  <div
                    className="h-full rounded bg-sky-500/60 dark:bg-sky-500/70"
                    style={{ width: `${Math.max(0.5, c.share * 100)}%` }}
                  />
                </div>
                <span className="w-28 shrink-0 text-right tabular-nums text-xs text-muted-foreground">
                  {fmtUsd(c.tvl)} · {(c.share * 100).toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {brief && (
        <Card>
          <CardHeader className="flex-row items-center gap-3 space-y-0">
            <CardTitle>Generated research brief</CardTitle>
            <Badge variant="outline" className="ml-auto text-[10px] uppercase">
              {brief.generated_by === "llm" ? "LLM-generated" : "template engine · no LLM key"}
            </Badge>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-relaxed text-foreground">
              {brief.sections.executive_summary}
            </p>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <BriefList title="Growth drivers" items={brief.sections.growth_drivers} />
              <BriefList title="Risks" items={brief.sections.risks} />
              <BriefList title="Cannot establish" items={brief.sections.data_gaps} />
              <BriefList title="Next steps" items={brief.sections.recommendations} />
            </div>
            <p className="mt-4 border-t pt-3 text-xs text-muted-foreground">
              Confidence: {brief.sections.confidence} · as of {brief.as_of} · sources:{" "}
              {brief.sources.map((s, i) => (
                <a key={s} href={s} target="_blank" rel="noreferrer" className="underline hover:text-foreground">
                  {i > 0 && " · "}
                  {s.replace("https://", "")}
                </a>
              ))}
            </p>
            <BriefDownloads slug={data.slug} blockedReason={exportBlocked} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function ProtocolFallback() {
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <Skeleton className="h-4 w-24" />
      <div className="flex items-end justify-between gap-3">
        <div className="space-y-2">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-4 w-64" />
        </div>
        <Skeleton className="h-10 w-32" />
      </div>
      <Skeleton className="h-64" />
      <Skeleton className="h-64" />
    </div>
  );
}

export default function ProtocolPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  return (
    <Suspense fallback={<ProtocolFallback />}>
      <ProtocolContent params={params} />
    </Suspense>
  );
}

function BriefList({ title, items }: { title: string; items: string[] }) {
  if (!items?.length) return null;
  return (
    <div>
      <h3 className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      <ul className="space-y-1.5">
        {items.map((item, i) => (
          <li key={i} className="text-xs leading-relaxed text-muted-foreground">
            • {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

const EXPORT_FORMATS = [
  { format: "md", label: "Markdown" },
  { format: "csv", label: "CSV" },
  { format: "pdf", label: "PDF" },
] as const;

/**
 * Why a download would be refused, or `null` if it is allowed.
 *
 * Both gates are mirrored from FastAPI so the button is disabled *before* the
 * click: RBAC (does the role hold `briefs:export`?) and the ABAC confidence gate
 * (a low-confidence brief needs risk-officer sign-off). FastAPI re-decides on
 * the real request — this only avoids a dead-end click.
 */
function briefExportGate(
  session: Session | null,
  brief: ResearchBrief | null,
): string | null {
  if (!brief) return null;
  if (!hasPermission(session, "briefs:export")) {
    const role = session?.subject.role ?? "anonymous";
    return `Your role (${role}) cannot export briefs; analyst or above required.`;
  }
  const role = session?.subject.role;
  const maySignOff = role === "risk_officer" || role === "admin";
  if (brief.sections.confidence === "low" && !maySignOff) {
    const gaps = brief.sections.data_gaps.length;
    return `Brief confidence is low (${gaps} data gap${gaps === 1 ? "" : "s"}); export needs risk-officer sign-off.`;
  }
  return null;
}

// Server-rendered download links: each anchors to the same-origin
// /api/brief-export proxy, so no client JS and the API host stays server-only.
function BriefDownloads({
  slug,
  blockedReason,
}: {
  slug: string;
  blockedReason: string | null;
}) {
  const base =
    "inline-flex items-center rounded-md border border-input px-2.5 py-1 text-xs font-medium";
  return (
    <div className="mt-4 space-y-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">Download brief:</span>
        {EXPORT_FORMATS.map(({ format, label }) =>
          blockedReason ? (
            <span
              key={format}
              aria-disabled="true"
              title={blockedReason}
              className={`${base} cursor-not-allowed border-dashed text-muted-foreground/60`}
            >
              {label}
            </span>
          ) : (
            <a
              key={format}
              href={`/api/brief-export/${encodeURIComponent(slug)}?format=${format}`}
              download
              className={`${base} bg-transparent transition-colors hover:bg-accent hover:text-accent-foreground`}
            >
              {label}
            </a>
          ),
        )}
      </div>
      {blockedReason && (
        <p className="text-xs leading-relaxed text-amber-700 dark:text-amber-300">
          Export disabled: {blockedReason}
        </p>
      )}
    </div>
  );
}

/**
 * Shown when FastAPI refuses access to this protocol (data scope).
 * Names the policy and the attribute that failed so the denial is auditable by
 * the person who hit it.
 */
function DenialPanel({ denial }: { denial: ApiError }) {
  return (
    <div className="mx-auto max-w-5xl space-y-3">
      <nav className="text-xs text-muted-foreground">
        <Link href="/" className="hover:text-foreground">
          ← Dashboard
        </Link>
      </nav>
      <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 sm:p-6">
        <h1 className="mb-1 flex items-center gap-2 text-lg font-semibold text-amber-800 dark:text-amber-200">
          <LockKeyhole className="size-4" /> {denial.reason}
        </h1>
        <p className="text-sm text-amber-700/80 dark:text-amber-300/80">
          {denial.policy === "scope.category_chain"
            ? "Data scope is applied per category and primary chain, so a protocol outside your remit is not readable even though the rest of the board is."
            : "The API refused this request. Ask an administrator if you believe you should have access."}
        </p>
        <p className="mt-2 text-xs text-amber-700/70 dark:text-amber-300/70">
          policy: <code className="font-mono">{denial.policy ?? "unknown"}</code>
          {denial.failedPredicate && (
            <>
              {" · failed predicate: "}
              <code className="font-mono">{denial.failedPredicate}</code>
            </>
          )}
        </p>
      </div>
    </div>
  );
}

// A 0..1 fraction rendered as a percent; null reads n/a (a data gap).
function fmtRatio(v: number | null | undefined): string {
  if (v == null) return "n/a";
  return `${(v * 100).toFixed(2)}%`;
}

// Whole counts with separators (locale pinned so server and client agree);
// null reads n/a, never 0.
function fmtCount(v: number | null | undefined): string {
  if (v == null) return "n/a";
  return Math.round(v).toLocaleString("en-US");
}

// "1,204 · 38.10%" when both are known, the bare count when the share is not,
// and n/a when neither is.
function fmtReturning(count: number | null | undefined, share: number | null | undefined): string {
  if (count == null) return "n/a";
  if (share == null) return fmtCount(count);
  return `${fmtCount(count)} · ${fmtRatio(share)}`;
}

// Basis points from the $1 peg; null reads n/a (a data gap).
function fmtBps(v: number | null | undefined): string {
  if (v == null) return "n/a";
  return `${v.toFixed(0)} bps`;
}

/**
 * One line stating why the numbers above may be missing or incomplete.
 *
 * The status is decided by the backend (key? mapping? rows? complete newest
 * day?) and this only phrases it. The page must not re-derive freshness from
 * `as_of`, or the two would disagree the moment the stale window is retuned.
 */
function OnchainStatusLine({ activity }: { activity: OnchainActivity }) {
  const covered = activity.chains.length ? activity.chains.join(", ") : null;
  if (activity.status === "ok") {
    return (
      <p className="mt-2 text-xs text-muted-foreground">
        Measured on {covered} · as of {activity.as_of}
      </p>
    );
  }
  if (activity.status === "partial") {
    return (
      <p className="mt-2 text-xs leading-relaxed text-amber-700 dark:text-amber-300">
        Partial coverage: {activity.note}
        {covered ? ` Figures cover ${covered} only.` : ""}
      </p>
    );
  }
  if (activity.status === "stale") {
    return (
      <p className="mt-2 text-xs leading-relaxed text-amber-700 dark:text-amber-300">
        Data freshness: {activity.note} Treat on-chain conclusions as provisional.
      </p>
    );
  }
  // `unconfigured` / `no_data`: the backend's note already explains the gap,
  // and naming the missing environment variable is the whole point of it.
  return (
    <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{activity.note}</p>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-0.5 truncate text-base font-semibold tabular-nums">{value}</div>
    </div>
  );
}
