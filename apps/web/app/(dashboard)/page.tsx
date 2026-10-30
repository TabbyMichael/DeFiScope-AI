import { Suspense } from "react";
import { AlertTriangle } from "lucide-react";

import TvlChart from "@/components/TvlChart";
import AlertFeed from "@/components/dashboard/alert-feed";
import ProtocolTable from "@/components/dashboard/protocol-table";
import RiskWatchlist from "@/components/dashboard/risk-watchlist";
import StatCards from "@/components/dashboard/stat-cards";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { DashboardResponse } from "@/lib/types";

async function DashboardContent({
  searchParams,
}: {
  searchParams: Promise<{ band?: string }>;
}) {
  // Read the (optional) band deep-link INSIDE the Suspense boundary: Next 16
  // Cache Components treats `searchParams` as runtime data, so accessing it in
  // the page shell (outside <Suspense>) would block prerendering.
  const { band: initialBand } = await searchParams;
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
          Could not reach the DeFiScope API. Start the backend with{" "}
          <code className="block break-all rounded bg-muted px-1.5 py-0.5 text-xs sm:inline-block">
            cd services/api &amp;&amp; uv run uvicorn app.main:app --port 8000
          </code>
        </p>
        <p className="mt-2 text-xs text-red-600/60 dark:text-red-400/60">{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            TVL trends only — rising or falling TVL alone does not prove
            sustainable growth or risk. Open a protocol for evidence and limitations.
          </p>
        </div>
        {data.as_of && (
          <span className="hidden shrink-0 text-xs text-muted-foreground sm:inline">
            data as of {data.as_of}
          </span>
        )}
      </section>

      <StatCards stats={data.stats} />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <div id="protocols" className="scroll-mt-4">
            <ProtocolTable
              key={initialBand ?? "all"}
              protocols={data.protocols}
              initialBand={initialBand}
            />
          </div>
        </div>
        <div className="space-y-6">
          <RiskWatchlist protocols={data.protocols} />
          <AlertFeed alerts={data.alerts} />
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardDescription>Aggregate tracked TVL across all protocols</CardDescription>
          <CardTitle>Total TVL trend</CardTitle>
        </CardHeader>
        <CardContent>
          <TvlChart data={data.aggregate_history} />
        </CardContent>
      </Card>
    </div>
  );
}

function DashboardFallback() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-4 w-full max-w-2xl" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <Skeleton className="h-[360px] lg:col-span-2" />
        <div className="space-y-6">
          <Skeleton className="h-[200px]" />
          <Skeleton className="h-[140px]" />
        </div>
      </div>
      <Skeleton className="h-[300px]" />
    </div>
  );
}

export default function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ band?: string }>;
}) {
  return (
    <Suspense fallback={<DashboardFallback />}>
      <DashboardContent searchParams={searchParams} />
    </Suspense>
  );
}
