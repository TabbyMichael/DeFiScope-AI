"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import {
  ArrowDownRight,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
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
import { fmtPct, fmtUsd, watchlistQuerystring } from "@/lib/api-config";
import type { DashboardStats, ProtocolOverview, WatchlistPage } from "@/lib/types";

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

const SIZES = [50, 100, 200] as const;

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
      <span className="w-7 shrink-0 text-center text-xs tabular-nums text-muted-foreground">
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

function EmptyRows() {
  return (
    <div className="flex flex-col items-center gap-1 rounded-xl border border-dashed py-10 text-center">
      <ShieldAlert className="size-5 text-muted-foreground" />
      <p className="text-sm text-muted-foreground">No scored protocols in this view yet.</p>
      <p className="text-xs text-muted-foreground/70">
        A missing score is a data gap, never a claim that a protocol is safe.
      </p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Section variant: the compact Overview board. Client-side over the capped   */
/* dashboard preview (a small, already-loaded slice) - no server round-trips. */
/* -------------------------------------------------------------------------- */

function SectionBoard({
  protocols,
  stats,
}: {
  protocols: ProtocolOverview[];
  stats: DashboardStats;
}) {
  // Highest risk first, mirroring the page's default sort so both surfaces
  // rank the same way. The full-market filter/sort/pagination lives on /watchlist.
  // Eight rows tall: the Overview's right column is grid-stretched to match the
  // tall protocols catalog beside it, so the card elongates to fill that space.
  const rows = useMemo(
    () => [...protocols].sort((a, b) => num(b.risk_score) - num(a.risk_score)).slice(0, 8),
    [protocols],
  );

  return (
    <Card>
      <CardHeader>
        <CardDescription className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5">
            <ShieldAlert className="size-3.5" /> Tracked protocols, by risk
            <span className="text-muted-foreground/70">
              · showing {rows.length} of {stats.protocol_count}
            </span>
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
      <CardContent>
        {rows.length === 0 ? (
          <EmptyRows />
        ) : (
          <div className="space-y-0.5">
            {rows.map((p, i) => (
              <WatchRow key={p.slug} p={p} rank={i + 1} dense index={i} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Page variant: server-paginated over the full ~5000-row market. Controls    */
/* mutate the URL search params (the server component re-fetches one page);   */
/* hero/band tiles read the server summary, never the current page's length.  */
/* -------------------------------------------------------------------------- */

function PageBoard({ data }: { data: WatchlistPage }) {
  const router = useRouter();
  const pathname = usePathname();

  const currentSort: SortKey = data.sort in SORT_LABELS ? (data.sort as SortKey) : "risk";
  const currentDir = data.dir === "asc" ? "asc" : "desc";
  const currentBand = data.band ?? undefined;
  const serverQ = data.q ?? "";

  const [qInput, setQInput] = useState(serverQ);

  // Re-sync the box when the URL (and thus data.q) changes from elsewhere
  // (band clicks, back/forward, a mover link). The "adjust state on prop
  // change during render" pattern - not an effect - per the React guidance,
  // so we never cascade a render from a synchronous setState in an effect.
  const [prevQ, setPrevQ] = useState(serverQ);
  if (serverQ !== prevQ) {
    setPrevQ(serverQ);
    setQInput(serverQ);
  }

  function push(patch: {
    page?: number;
    size?: number;
    sort?: SortKey;
    dir?: "asc" | "desc";
    band?: string;
    q?: string;
  }) {
    const merged = {
      page: patch.page ?? (patch.sort || patch.dir || patch.band !== undefined || patch.q !== undefined ? 1 : data.page),
      size: (patch.size ?? data.size) as 50 | 100 | 200,
      sort: patch.sort ?? currentSort,
      dir: patch.dir ?? currentDir,
      band: patch.band ?? currentBand,
      q: patch.q !== undefined ? patch.q : serverQ,
    };
    const qs = watchlistQuerystring(merged);
    router.push(`${pathname}${qs}`);
  }

  // Debounced search: one navigation per pause, not one per keystroke, so we
  // never stampede the paginated endpoint while a term is being typed.
  useEffect(() => {
    const term = qInput.trim();
    if (term === serverQ) return;
    const t = setTimeout(() => push({ q: term }), 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qInput]);

  const scoredCount = Object.entries(data.band_counts)
    .filter(([k]) => k !== "unknown")
    .reduce((s, [, v]) => s + v, 0);

  const offset = (data.page - 1) * data.size;
  const items = data.items ?? [];

  return (
    <div className="space-y-6">
      {/* Hero: market-wide totals straight from the server summary, so they
          stay truthful no matter which page / band / search is active. */}
      <section className="animate-in fade-in slide-in-from-bottom-3 rounded-2xl border bg-gradient-to-br from-card to-muted/40 p-5 sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-sm text-muted-foreground">Tracked protocols</p>
            <p className="text-3xl font-semibold tabular-nums">
              <AnimatedNumber value={data.stats.protocol_count} />
              <span className="ml-2 text-base font-normal text-muted-foreground">
                {scoredCount} scored
              </span>
            </p>
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-right sm:grid-cols-3">
            <div>
              <p className="text-xs text-muted-foreground">Board TVL</p>
              <p className="text-lg font-semibold tabular-nums">
                <AnimatedNumber value={data.stats.total_tvl} format={fmtUsd} />
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Active alerts</p>
              <p className="text-lg font-semibold tabular-nums">
                <AnimatedNumber value={data.stats.active_critical + data.stats.active_warning} />
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Top 7d mover</p>
              <p className="text-lg font-semibold tabular-nums">
                {data.stats.top_gainer ? (
                  <span className="text-emerald-600 dark:text-emerald-400">
                    {data.stats.top_gainer.name} {fmtPct(data.stats.top_gainer.change_7d)}
                  </span>
                ) : (
                  <span className="text-muted-foreground">n/a</span>
                )}
              </p>
            </div>
          </div>
        </div>
        {data.as_of && (
          <p className="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
            <Gauge className="size-3.5" /> data as of {data.as_of} · market-wide view,
            refreshed continuously
          </p>
        )}
      </section>

      {/* Band tiles: server-side counts over the whole scoped board. */}
      <section className="animate-in fade-in grid grid-cols-2 gap-2 sm:grid-cols-5">
        {BANDS.map((b) => {
          const count = data.band_counts[b] ?? 0;
          const pct = data.stats.protocol_count ? (count / data.stats.protocol_count) * 100 : 0;
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

      {/* Search + sort controls (URL-driven). */}
      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[180px] flex-1">
            <Input
              value={qInput}
              onChange={(e) => setQInput(e.target.value)}
              placeholder="Search tracked protocols…"
              className="h-9 pl-3"
              aria-label="Search protocols"
            />
          </div>
          <div className="flex items-center gap-1 rounded-lg border bg-card p-1 text-xs">
            <SlidersHorizontal className="ml-1 size-3.5 text-muted-foreground" />
            {(Object.keys(SORT_LABELS) as SortKey[]).map((k) => {
              const active = currentSort === k;
              return (
                <button
                  key={k}
                  type="button"
                  onClick={() =>
                    active
                      ? push({ sort: k, dir: currentDir === "desc" ? "asc" : "desc" })
                      : push({ sort: k, dir: "desc" })
                  }
                  className={`rounded-md px-2 py-1 transition-colors ${
                    active
                      ? "bg-emerald-500/15 font-medium text-emerald-700 dark:text-emerald-400"
                      : "text-muted-foreground hover:bg-accent hover:text-foreground"
                  }`}
                >
                  {SORT_LABELS[k]}
                  {active ? (currentDir === "desc" ? " ↓" : " ↑") : ""}
                </button>
              );
            })}
          </div>
        </div>

        {/* Band chips: driven by the tile counts, so they never contradict the hero. */}
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => push({ band: "" })}
            className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
              !currentBand
                ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                : "border-border bg-card text-muted-foreground hover:bg-accent"
            }`}
          >
            All ({data.stats.protocol_count})
          </button>
          {BANDS.filter((b) => (data.band_counts[b] ?? 0) > 0).map((b) => {
            const active = currentBand === b;
            return (
              <button
                key={b}
                type="button"
                onClick={() => push({ band: active ? "" : b })}
                className={`rounded-full border px-2.5 py-1 text-xs capitalize transition-colors ${
                  active
                    ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                    : "border-border bg-card text-muted-foreground hover:bg-accent"
                }`}
              >
                {b}
              </button>
            );
          })}
        </div>

        {items.length === 0 ? (
          <EmptyRows />
        ) : (
          <div className="space-y-0.5">
            {items.map((p, i) => (
              <WatchRow key={p.slug} p={p} rank={offset + i + 1} dense={false} index={i} />
            ))}
          </div>
        )}

        {/* Pagination footer: Prev/Next, page size and a truthful page window. */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-1 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <span>Rows per page</span>
            <select
              value={data.size}
              onChange={(e) => push({ size: Number(e.target.value), page: 1 })}
              className="rounded-md border bg-card px-1.5 py-1 text-foreground"
              aria-label="Rows per page"
            >
              {SIZES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div>
            {data.total > 0
              ? `Showing ${offset + 1}–${offset + items.length} of ${data.total.toLocaleString()}`
              : "No matching protocols"}
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => push({ page: data.page - 1 })}
              disabled={data.page <= 1}
              className="inline-flex items-center gap-1 rounded-md border bg-card px-2 py-1 transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ChevronLeft className="size-3.5" /> Prev
            </button>
            <span className="tabular-nums">
              Page {data.page} / {Math.max(data.pages, 1)}
            </span>
            <button
              type="button"
              onClick={() => push({ page: data.page + 1 })}
              disabled={data.page >= data.pages}
              className="inline-flex items-center gap-1 rounded-md border bg-card px-2 py-1 transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next <ChevronRight className="size-3.5" />
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

export default function WatchlistBoard({
  protocols,
  stats,
  variant = "section",
  data,
}: {
  protocols?: ProtocolOverview[];
  stats: DashboardStats;
  variant?: "section" | "page";
  data?: WatchlistPage;
}) {
  if (variant === "page") {
    if (!data) return null;
    return <PageBoard data={data} />;
  }
  return <SectionBoard protocols={protocols ?? []} stats={stats} />;
}
