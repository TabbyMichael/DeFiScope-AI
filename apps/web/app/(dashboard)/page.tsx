import { Suspense } from "react";
import Link from "next/link";
import { AlertTriangle } from "lucide-react";

import TvlChart from "@/components/TvlChart";
import AlertFeed from "@/components/dashboard/alert-feed";
import ProtocolExplorer from "@/components/dashboard/protocol-explorer";
import StatCards from "@/components/dashboard/stat-cards";
import WatchlistBoard from "@/components/dashboard/watchlist-board";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import {
  parseExplorerState,
  toCatalogQuery,
  type ExplorerState,
  type SearchParamRecord,
} from "@/lib/explorer";
import type {
  CatalogFacets,
  DashboardResponse,
  ProtocolCatalogPage,
} from "@/lib/types";

const EMPTY_FACETS: CatalogFacets = { categories: [], chains: [] };

// The board's "Protocols" section is backed by the *full discovery catalog*, not
// just the monitored set: thousands of protocols, paginated entirely server-side.
// Only one page ever reaches the browser; the client component drives subsequent
// pages/filters through the same-origin /api/catalog proxy. Fetched independently
// of the monitored board data so a catalog hiccup never blanks the whole page.
async function ProtocolsCatalogSection({ state }: { state: ExplorerState }) {
  const [pageResult, facetsResult] = await Promise.allSettled([
    api.protocols(toCatalogQuery(state)),
    api.protocolFacets(),
  ]);
  const page: ProtocolCatalogPage | null =
    pageResult.status === "fulfilled" ? pageResult.value : null;
  const error =
    pageResult.status === "rejected"
      ? pageResult.reason instanceof Error
        ? pageResult.reason.message
        : String(pageResult.reason)
      : null;
  const facets: CatalogFacets =
    facetsResult.status === "fulfilled" ? facetsResult.value : EMPTY_FACETS;
  return (
    <ProtocolExplorer
      initialState={state}
      initialPage={page}
      facets={facets}
      initialError={error}
      basePath="/"
    />
  );
}

async function DashboardContent({
  searchParams,
}: {
  searchParams: Promise<SearchParamRecord>;
}) {
  // Read the catalog view state (search/sort/filters/page + the legacy band
  // deep-link) INSIDE the Suspense boundary: Next 16 Cache Components treats
  // `searchParams` as runtime data, so accessing it in the page shell (outside
  // <Suspense>) would block prerendering.
  const catalogState = parseExplorerState(await searchParams);
  let data: DashboardResponse | null = null;
  let error: string | null = null;
  /* Did the API answer, or did nothing pick up? */
  let answered = false;
  try {
    data = await api.dashboard();
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
    answered = e instanceof ApiError;
  }

  if (error || !data) {
    /* Two failures wear the same face here and they are not the same problem.
       A refused connection means the backend is not running, so the fix is to
       start it. An HTTP status means it is running and said no, and telling
       someone to start a process that is already up sends them down the wrong
       path. The message underneath carries the URL that was tried either way. */
    return (
      <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm sm:p-6">
        <h2 className="mb-1 flex items-center gap-2 font-semibold text-red-600 dark:text-red-300">
          <AlertTriangle className="size-4" />
          {answered ? "API error" : "API unavailable"}
        </h2>
        {answered ? (
          <p className="text-red-700/80 dark:text-red-200/80">
            The API is reachable but returned an error instead of the board, so
            the backend is running. The status and detail are below.
          </p>
        ) : (
          <p className="text-red-700/80 dark:text-red-200/80">
            Could not reach the DeFiScope API. Start the backend with{" "}
            <code className="block break-all rounded bg-muted px-1.5 py-0.5 text-xs sm:inline-block">
              cd services/api &amp;&amp; uv run uvicorn app.main:app --port 8000
            </code>
          </p>
        )}
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
            TVL trends only. Rising or falling TVL alone does not prove
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
          <div id="protocols" className="scroll-mt-4 space-y-3">
            <div className="flex items-baseline justify-between gap-4">
              <h2 className="text-lg font-semibold tracking-tight">
                Protocols
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  full discovery catalog
                </span>
              </h2>
              <Link
                href="/explore"
                className="shrink-0 text-xs text-muted-foreground underline-offset-2 hover:underline"
              >
                Open explorer →
              </Link>
            </div>
            <Suspense fallback={<Skeleton className="h-[440px] w-full rounded-lg" />}>
              <ProtocolsCatalogSection
                key={JSON.stringify(catalogState)}
                state={catalogState}
              />
            </Suspense>
          </div>
        </div>
        <div className="space-y-6">
          <WatchlistBoard
            protocols={data.protocols}
            stats={data.stats}
            asOf={data.as_of}
            variant="section"
          />
          <AlertFeed alerts={data.alerts} withheld={data.withheld_alerts} />
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
  searchParams: Promise<SearchParamRecord>;
}) {
  return (
    <Suspense fallback={<DashboardFallback />}>
      <DashboardContent searchParams={searchParams} />
    </Suspense>
  );
}
