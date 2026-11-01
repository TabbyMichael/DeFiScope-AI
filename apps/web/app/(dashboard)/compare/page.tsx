import { Suspense } from "react";
import { GitCompare } from "lucide-react";

import CompareMatrix from "@/components/dashboard/compare-matrix";
import ComparePicker from "@/components/dashboard/compare-picker";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import {
  MAX_COMPARE,
  parseSlugs,
  type CompareItem,
  type CompareOption,
} from "@/lib/compare";

async function CompareContent({
  searchParams,
}: {
  searchParams: Promise<{ slugs?: string | string[] }>;
}) {
  const { slugs, truncated } = parseSlugs((await searchParams).slugs);

  // Resolve each selected slug to a column; a failing slug becomes "unavailable".
  const items: CompareItem[] = await Promise.all(
    slugs.map(async (slug) => {
      try {
        const data = await api.protocol(slug);
        return { slug, data };
      } catch {
        return { slug, data: null };
      }
    }),
  );

  // Labels for the selected badges, resolved server-side so the picker never has
  // to keep the whole catalog around just to name a chosen protocol. The picker
  // itself searches the full discovery catalog on demand via /api/catalog.
  const selected: CompareOption[] = items.map((it) => ({
    slug: it.slug,
    name: it.data?.name ?? it.slug,
    category: it.data?.category ?? null,
  }));

  return (
    <div className="space-y-6">
      <div className="space-y-3 rounded-lg border bg-card p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            Pick 2 to {MAX_COMPARE} protocols to compare. The selection lives in
            the URL, so any view is shareable.
          </p>
          <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
            {slugs.length}/{MAX_COMPARE}
          </span>
        </div>
        <ComparePicker selected={selected} />
        {truncated && (
          <p className="text-xs text-yellow-700 dark:text-yellow-400">
            Only the first {MAX_COMPARE} protocols are compared. Extra slugs in
            the URL were ignored.
          </p>
        )}
      </div>

      {slugs.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-14 text-center">
          <GitCompare className="size-6 text-muted-foreground" />
          <p className="text-sm font-medium text-foreground">
            Nothing to compare yet
          </p>
          <p className="max-w-sm text-xs leading-relaxed text-muted-foreground">
            Search above and select at least two protocols, for example Aave v3
            and Uniswap v3, to see their metrics and risk side by side.
          </p>
        </div>
      ) : slugs.length === 1 ? (
        <p className="text-sm text-muted-foreground">
          Select one more protocol to see a side-by-side comparison.
        </p>
      ) : (
        <CompareMatrix items={items} />
      )}
    </div>
  );
}

function CompareFallback() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-28" />
      <Skeleton className="h-96" />
    </div>
  );
}

export default function ComparePage({
  searchParams,
}: {
  searchParams: Promise<{ slugs?: string | string[] }>;
}) {
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <GitCompare className="size-5" /> Compare
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Side-by-side TVL trends and explainable risk for up to {MAX_COMPARE}{" "}
            protocols. Scores reflect what TVL data can show. Gaps are surfaced,
            not hidden.
          </p>
        </div>
      </header>
      <Suspense fallback={<CompareFallback />}>
        <CompareContent searchParams={searchParams} />
      </Suspense>
    </div>
  );
}
