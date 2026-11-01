import { Suspense } from "react";
import { Search } from "lucide-react";

import ProtocolExplorer from "@/components/dashboard/protocol-explorer";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import {
  parseExplorerState,
  toCatalogQuery,
  type ExplorerState,
  type SearchParamRecord,
} from "@/lib/explorer";
import type { CatalogFacets, ProtocolCatalogPage } from "@/lib/types";

export const metadata = {
  title: "Protocol Explorer · DeFiScope AI",
  description: "Search and browse the full DeFiScope protocol discovery catalog.",
};

const EMPTY_FACETS: CatalogFacets = { categories: [], chains: [] };

// The Explorer's data is always fetched server-side. The initial page and facets
// are resolved here (so the first paint is complete and shareable from the URL),
// then handed to the client component, which drives every subsequent page/filter
// through the same-origin /api/catalog proxy. Discovery spans 5,000+ protocols;
// only one page ever reaches the browser.
async function ExplorerContent({
  searchParams,
}: {
  searchParams: Promise<SearchParamRecord>;
}) {
  const state: ExplorerState = parseExplorerState(await searchParams);

  // Facets power the filter selectors; a cold catalog simply yields none.
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
    />
  );
}

function ExplorerFallback() {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Skeleton className="h-9 w-full max-w-xs" />
        <Skeleton className="h-9 w-[150px]" />
        <Skeleton className="h-9 w-[150px]" />
      </div>
      <Skeleton className="h-[480px] w-full rounded-lg" />
    </div>
  );
}

export default function ExplorePage({
  searchParams,
}: {
  searchParams: Promise<SearchParamRecord>;
}) {
  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Search className="size-5" /> Protocol Explorer
        </h1>
        <p className="text-sm text-muted-foreground">
          The full discovery catalog. Search, filter and page across every
          protocol DefiLlama lists - not just the monitored ones. A protocol
          without a score is shown as a gap, never as safe.
        </p>
      </header>
      <Suspense fallback={<ExplorerFallback />}>
        <ExplorerContent searchParams={searchParams} />
      </Suspense>
    </div>
  );
}
