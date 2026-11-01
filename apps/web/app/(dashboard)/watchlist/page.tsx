import { Suspense } from "react";
import Link from "next/link";
import { AlertTriangle, ShieldAlert } from "lucide-react";

import WatchlistBoard from "@/components/dashboard/watchlist-board";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { DashboardResponse } from "@/lib/types";

export const metadata = {
  title: "Risk Watchlist · DeFiScope AI",
  description:
    "The full ranked watchlist of tracked protocols: search, filter by risk band, and sort by risk, TVL or trend.",
};

// Same monitored-board payload the Overview stats read (`/api/dashboard`): the
// watchlist is a full-screen view of `data.protocols`, so no extra endpoint is
// needed and both surfaces can never disagree about who is tracked or scored.
async function WatchlistContent() {
  let data: DashboardResponse | null = null;
  let error: string | null = null;
  try {
    data = await api.dashboard();
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

  return (
    <WatchlistBoard
      protocols={data.protocols}
      stats={data.stats}
      asOf={data.as_of}
      variant="page"
    />
  );
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

export default function WatchlistPage() {
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <ShieldAlert className="size-5" /> Risk watchlist
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Every monitored protocol, ranked by composite risk. Sort by risk,
            TVL or trend and filter by band. An unscored protocol is a data
            gap, never a claim that it is safe.
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
        <WatchlistContent />
      </Suspense>
    </div>
  );
}
