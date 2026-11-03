import { Suspense } from "react";
import Link from "next/link";
import { AlertTriangle, ShieldAlert } from "lucide-react";

import WatchlistBoard from "@/components/dashboard/watchlist-board";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type WatchlistQuery } from "@/lib/api";
import type { WatchlistPage } from "@/lib/types";

export const metadata = {
  title: "Risk Watchlist · DeFiScope AI",
  description:
    "The full market-wide risk watchlist: every monitored protocol, server-paginated and searchable, ranked by risk, TVL or trend.",
};

// Coerce a raw search-param value into a member of a closed set, else fallback.
function pick<T extends string>(raw: string | string[] | undefined, allowed: readonly T[], fallback: T): T {
  const v = Array.isArray(raw) ? raw[0] : raw;
  return v && (allowed as readonly string[]).includes(v) ? (v as T) : fallback;
}

function pickSize(raw: string | string[] | undefined): 50 | 100 | 200 {
  const v = Array.isArray(raw) ? raw[0] : raw;
  const n = v ? Number.parseInt(v, 10) : NaN;
  return n === 50 || n === 100 || n === 200 ? n : 100;
}

function pickPage(raw: string | string[] | undefined): number {
  const v = Array.isArray(raw) ? raw[0] : raw;
  const n = v ? Number.parseInt(v, 10) : NaN;
  return Number.isFinite(n) && n >= 1 ? n : 1;
}

// The board reads ONE server-paginated slice of the full market (GET
// /api/watchlist) driven entirely by the URL: the server sorts/filters/searches
// and pages in SQL, and returns the market-wide summary for the hero/tiles, so
// the page never fetches all ~5000 rows to the browser.
async function WatchlistContent({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const query: WatchlistQuery = {
    page: pickPage(sp.page),
    size: pickSize(sp.size),
    sort: pick(sp.sort, ["risk", "tvl", "7d", "30d"] as const, "risk"),
    dir: pick(sp.dir, ["asc", "desc"] as const, "desc"),
    band: (Array.isArray(sp.band) ? sp.band[0] : sp.band) || undefined,
    q: (Array.isArray(sp.q) ? sp.q[0] : sp.q) || undefined,
  };

  let data: WatchlistPage | null = null;
  let error: string | null = null;
  try {
    data = await api.watchlist(query);
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  if (error || !data) {
    return (
      <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm sm:p-6">
        <h2 className="mb-1 flex items-center gap-2 font-semibold text-red-600 dark:text-red-300">
          <AlertTriangle className="size-4" /> API unavailable
        </h2>
        <p className="text-red-700/80 dark:text-red-200/80">
          Could not reach the DeFiScope API, so the watchlist board has no data
          to show. Start the backend with{" "}
          <code className="block break-all rounded bg-muted px-1.5 py-0.5 text-xs sm:inline-block">
            cd services/api &amp;&amp; uv run uvicorn app.main:app --port 8000
          </code>
        </p>
        <p className="mt-2 text-xs text-red-600/60 dark:text-red-400/60">{error}</p>
      </div>
    );
  }

  return <WatchlistBoard data={data} stats={data.stats} variant="page" />;
}

function WatchlistFallback() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-32 rounded-2xl" />
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-20 rounded-xl" />
        ))}
      </div>
      <div className="space-y-2">
        <Skeleton className="h-9 w-full max-w-xs" />
        <Skeleton className="h-[420px] w-full rounded-xl" />
      </div>
    </div>
  );
}

export default function WatchlistPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <ShieldAlert className="size-5" /> Risk watchlist
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Every monitored protocol across the market, ranked by composite
            risk. Sort by risk, TVL or trend and filter by band - server-
            paginated, so the full watchlist stays fast. An unscored protocol
            is a data gap, never a claim that it is safe.
          </p>
        </div>
        <Link
          href="/"
          className="shrink-0 text-xs text-muted-foreground underline-offset-2 hover:text-emerald-600 hover:underline dark:hover:text-emerald-400"
        >
          ← Back to overview
        </Link>
      </header>
      <Suspense fallback={<WatchlistFallback />}>
        <WatchlistContent searchParams={searchParams} />
      </Suspense>
    </div>
  );
}
