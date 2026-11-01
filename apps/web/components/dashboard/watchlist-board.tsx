"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowDownRight,
  ArrowUpRight,
  Gauge,
  ShieldAlert,
  SlidersHorizontal,
} from "lucide-react";

import AnimatedNumber from "@/components/dashboard/animated-number";
import MiniSparkline from "@/components/dashboard/mini-sparkline";
import RiskBadge from "@/components/RiskBadge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { fmtPct, fmtUsd } from "@/lib/api-config";
import type { DashboardStats, ProtocolOverview } from "@/lib/types";

type SortKey = "risk" | "tvl" | "7d" | "30d";

const BANDS = ["low", "moderate", "elevated", "high", "unknown"] as const;

// Band -> meter gradient + text tone. Kept in lockstep with <RiskBadge>.
const METER: Record<string, string> = {
  low: "from-emerald-400 to-emerald-500",
  moderate: "from-yellow-400 to-yellow-500",
  elevated: "from-orange-400 to-orange-500",
  high: "from-red-400 to-red-500",
  unknown: "from-zinc-300 to-zinc-400 dark:from-zinc-600 dark:to-zinc-500",
};

const SORT_LABELS: Record<SortKey, string> = {
  risk: "Highest risk",
  tvl: "Largest TVL",
  "7d": "7d change",
  "30d": "30d change",
};

function num(v: number | null | undefined): number {
  return v == null || Number.isNaN(v) ? -Infinity : v;
}

/** The row one protocol contributes to the ranked board. Presentational only. */
function WatchRow({
  p,
  rank,
  dense,
  index,
}: {
  p: ProtocolOverview;
  rank: number;
  dense: boolean;
  index: number;
}) {
  const scored = p.risk_score != null && p.risk_band !== "unknown";
  const score = p.risk_score ?? 0;
  const band = scored ? p.risk_band : "unknown";
  const gain = p.change_7d != null && p.change_7d >= 0;
  const delay = Math.min(index, 14) * 45; // stagger, capped so long tails stay snappy

  return (
    <Link
      href={`/protocols/${p.slug}`}
      style={{ animationDelay: `${delay}ms` }}
      className="group animate-in fade-in slide-in-from-bottom-2 flex items-center gap-3 rounded-xl border border-transparent px-2.5 py-2 transition-colors duration-200 hover:border-border hover:bg-accent/60 focus-visible:border-ring"
    >
      <span className="w-5 shrink-0 text-center text-xs tabular-nums text-muted-foreground">
        {rank}
      </span>

      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium group-hover:text-emerald-600 dark:group-hover:text-emerald-400">
          {p.name}
        </div>
        {/* Dense (section) rows keep only the category - the sidebar column is
            narrow, and chain detail belongs on the full page / protocol view. */}
        <div className="truncate text-xs text-muted-foreground">
          {p.category ?? "Uncategorized"}
          {!dense && p.top_chain ? ` · ${p.top_chain}` : ""}
        </div>
      </div>

      <div className={`hidden shrink-0 text-right sm:block ${dense ? "w-20" : "w-24"}`}>
        <div className="text-sm tabular-nums">{fmtUsd(p.tvl)}</div>
        <div
          className={`text-xs tabular-nums ${
            p.change_7d == null
              ? "text-muted-foreground"
              : gain
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-red-600 dark:text-red-400"
          }`}
        >
          {p.change_7d == null ? "n/a" : fmtPct(p.change_7d)} <span className="opacity-60">7d</span>
        </div>
      </div>

      {!dense && p.change_30d != null && (
        <div
          className={`hidden w-16 shrink-0 items-center justify-end gap-1 text-xs tabular-nums lg:flex ${
            p.change_30d >= 0
              ? "text-emerald-600 dark:text-emerald-400"
              : "text-red-600 dark:text-red-400"
          }`}
        >
          {p.change_30d >= 0 ? (
            <ArrowUpRight className="size-3" />
          ) : (
            <ArrowDownRight className="size-3" />
          )}
          {fmtPct(p.change_30d)}
        </div>
      )}

      {/* Sparklines only on the full page: in the narrow sidebar column they
          steal the width the protocol name needs. */}
      {!dense && (
        <div className="hidden shrink-0 text-zinc-400 dark:text-zinc-600 md:block">
          <MiniSparkline points={p.sparkline ?? []} />
        </div>
      )}

      <div className={`flex shrink-0 flex-col items-end gap-1 ${dense ? "w-20" : "w-32"}`}>
        <RiskBadge score={p.risk_score} band={band} />
        <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
          <div
            className={`wl-meter h-full rounded-full bg-gradient-to-r ${METER[band]}`}
            style={{ width: `${scored ? Math.max(4, score) : 100}%` }}
          />
        </div>
      </div>
    </Link>
  );
}

export default function WatchlistBoard({
  protocols,
  stats,
  asOf,
  variant = "section",
}: {
  protocols: ProtocolOverview[];
  stats: DashboardStats;
  asOf?: string | null;
  variant?: "section" | "page";
}) {
  const [sort, setSort] = useState<SortKey>("risk");
  const [band, setBand] = useState<string>("all");
  const [q, setQ] = useState("");

  const page = variant === "page";

  const scoredCount = useMemo(
    () => protocols.filter((p) => p.risk_score != null && p.risk_band !== "unknown").length,
    [protocols],
  );

  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const rows = protocols.filter((p) => {
      if (band !== "all") {
        const b = p.risk_score != null && p.risk_band !== "unknown" ? p.risk_band : "unknown";
        if (b !== band) return false;
      }
      if (needle && !p.name.toLowerCase().includes(needle) && !p.slug.includes(needle)) {
        return false;
      }
      return true;
    });
    const key = (p: ProtocolOverview): number =>
      sort === "risk"
        ? num(p.risk_score)
        : sort === "tvl"
          ? num(p.tvl)
          : sort === "7d"
            ? num(p.change_7d)
            : num(p.change_30d);
    // Highest-first for every key (risk, tvl, and changes all read "top" high).
    return [...rows].sort((a, b) => key(b) - key(a));
  }, [protocols, band, q, sort]);

  const rows = page ? visible : visible.slice(0, 6);

  const body = (
    <>
      {page && (
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[180px] flex-1">
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search tracked protocols…"
              className="h-9 pl-3"
              aria-label="Search protocols"
            />
          </div>
          <div className="flex items-center gap-1 rounded-lg border bg-card p-1 text-xs">
            <SlidersHorizontal className="ml-1 size-3.5 text-muted-foreground" />
            {(Object.keys(SORT_LABELS) as SortKey[]).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setSort(k)}
                className={`rounded-md px-2 py-1 transition-colors ${
                  sort === k
                    ? "bg-emerald-500/15 font-medium text-emerald-700 dark:text-emerald-400"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground"
                }`}
              >
                {SORT_LABELS[k]}
              </button>
            ))}
          </div>
        </div>
      )}

      {page && (
        <div className="flex flex-wrap gap-1.5">
          {["all", ...BANDS.filter((b) => protocols.some((p) =>
            (p.risk_score != null && p.risk_band !== "unknown" ? p.risk_band : "unknown") === b,
          ))].map((b) => (
            <button
              key={b}
              type="button"
              onClick={() => setBand(b)}
              className={`rounded-full border px-2.5 py-1 text-xs capitalize transition-colors ${
                band === b
                  ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                  : "border-border bg-card text-muted-foreground hover:bg-accent"
              }`}
            >
              {b === "all" ? `All (${protocols.length})` : b}
            </button>
          ))}
        </div>
      )}

      {rows.length === 0 ? (
        <div className="flex flex-col items-center gap-1 rounded-xl border border-dashed py-10 text-center">
          <ShieldAlert className="size-5 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            No scored protocols in this view yet.
          </p>
          <p className="text-xs text-muted-foreground/70">
            A missing score is a data gap, never a claim that a protocol is safe.
          </p>
        </div>
      ) : (
        <div className="space-y-0.5">
          {rows.map((p, i) => (
            <WatchRow key={p.slug} p={p} rank={i + 1} dense={!page} index={i} />
          ))}
        </div>
      )}
    </>
  );

  if (!page) {
    // Compact dashboard section: a tight "highest risk" board that links out.
    return (
      <Card>
        <CardHeader>
          <CardDescription className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5">
              <ShieldAlert className="size-3.5" /> Tracked protocols, by risk
            </span>
          </CardDescription>
          <div className="flex items-baseline justify-between gap-2">
            <CardTitle>Risk watchlist</CardTitle>
            <Link
              href="/watchlist"
              className="text-xs font-normal text-muted-foreground underline-offset-2 hover:text-emerald-600 hover:underline dark:hover:text-emerald-400"
            >
              Open watchlist →
            </Link>
          </div>
        </CardHeader>
        <CardContent>{body}</CardContent>
      </Card>
    );
  }

  // Full page: a hero summary + the interactive ranked board.
  const avgRisk =
    scoredCount > 0
      ? protocols.reduce((s, p) => s + (p.risk_score ?? 0), 0) / scoredCount
      : 0;

  return (
    <div className="space-y-6">
      <section className="animate-in fade-in slide-in-from-bottom-3 rounded-2xl border bg-gradient-to-br from-card to-muted/40 p-5 sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-sm text-muted-foreground">Tracked protocols</p>
            <p className="text-3xl font-semibold tabular-nums">
              <AnimatedNumber value={protocols.length} />
              <span className="ml-2 text-base font-normal text-muted-foreground">
                {scoredCount} scored
              </span>
            </p>
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-right sm:grid-cols-3">
            <div>
              <p className="text-xs text-muted-foreground">Board TVL</p>
              <p className="text-lg font-semibold tabular-nums">
                <AnimatedNumber value={stats.total_tvl} format={fmtUsd} />
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Avg composite</p>
              <p className="text-lg font-semibold tabular-nums">
                <AnimatedNumber value={Math.round(avgRisk)} />
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Active alerts</p>
              <p className="text-lg font-semibold tabular-nums">
                <AnimatedNumber value={stats.active_critical + stats.active_warning} />
              </p>
            </div>
          </div>
        </div>
        {asOf && (
          <p className="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
            <Gauge className="size-3.5" /> data as of {asOf}
          </p>
        )}
      </section>

      {page && (
        <section className="animate-in fade-in grid grid-cols-2 gap-2 sm:grid-cols-5">
          {BANDS.map((b) => {
            const count = protocols.filter(
              (p) => (p.risk_score != null && p.risk_band !== "unknown" ? p.risk_band : "unknown") === b,
            ).length;
            const pct = protocols.length ? (count / protocols.length) * 100 : 0;
            return (
              <div key={b} className="rounded-xl border bg-card p-3">
                <div className="flex items-baseline justify-between">
                  <span className="text-xs capitalize text-muted-foreground">{b}</span>
                  <span className="text-lg font-semibold tabular-nums">{count}</span>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
                  <div
                    className={`wl-meter h-full rounded-full bg-gradient-to-r ${METER[b]}`}
                    style={{ width: `${Math.max(pct, count > 0 ? 6 : 0)}%` }}
                  />
                </div>
              </div>
            );
          })}
        </section>
      )}

      <section className="space-y-3">{body}</section>
    </div>
  );
}
