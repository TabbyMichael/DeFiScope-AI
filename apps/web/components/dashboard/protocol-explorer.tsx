"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowDown,
  ArrowUp,
  ChevronLeft,
  ChevronRight,
  Search,
} from "lucide-react";

import RiskBadge from "@/components/RiskBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fmtPct, fmtUsd } from "@/lib/api-config";
import {
  PAGE_SIZES,
  SORT_LABELS,
  RISK_BANDS,
  explorerFetchQuery,
  explorerHref,
  pageNumberWindow,
  type ExplorerState,
  type SortKey,
} from "@/lib/explorer";
import type { CatalogFacets, ProtocolCatalogPage } from "@/lib/types";

const ALL = "all";
const DEBOUNCE_MS = 300;

/** A null-safe percentage cell: a missing change reads "n/a", never 0%. */
function ChangeCell({ value }: { value: number | null }) {
  if (value == null) return <span className="text-muted-foreground">n/a</span>;
  const tone =
    value > 1
      ? "text-emerald-600 dark:text-emerald-400"
      : value < -1
        ? "text-red-600 dark:text-red-400"
        : "text-muted-foreground";
  return <span className={`tabular-nums ${tone}`}>{fmtPct(value)}</span>;
}

/**
 * The Protocol Explorer: a fully server-paginated view over the discovery
 * catalog. The component never holds the whole catalog - it holds one page and
 * refetches from the same-origin `/api/catalog` proxy whenever a control changes.
 *
 * Data always originates server-side; the URL is kept in sync (via the history
 * API) so any view is shareable, and a hard load is served its first page from the
 * React Server Component before hydration (no client refetch on boot).
 */
export default function ProtocolExplorer({
  initialState,
  initialPage,
  facets,
  initialError,
  basePath = "/explore",
}: {
  initialState: ExplorerState;
  initialPage: ProtocolCatalogPage | null;
  facets: CatalogFacets;
  initialError: string | null;
  /** Route the controls write back into; the Dashboard embeds this at "/". */
  basePath?: string;
}) {
  const [state, setState] = useState<ExplorerState>(initialState);
  const [page, setPage] = useState<ProtocolCatalogPage | null>(initialPage);
  const [searchText, setSearchText] = useState(initialState.q);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(initialError);
  // The RSC already served the first page, so skip one client fetch on mount.
  const booted = useRef(false);

  // Debounce the search box into committed state (a keystroke must not fetch).
  useEffect(() => {
    const trimmed = searchText.trim();
    const t = setTimeout(() => {
      setState((s) => (s.q === trimmed && s.page === 1 ? s : { ...s, q: trimmed, page: 1 }));
    }, DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [searchText]);

  // Refetch whenever the committed query changes (never on the server-rendered boot).
  useEffect(() => {
    if (!booted.current) {
      booted.current = true;
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetch(`/api/catalog?${explorerFetchQuery(state)}`)
      .then(async (res) => {
        if (!res.ok) {
          const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
          throw new Error(String(body.reason || body.error || `HTTP ${res.status}`));
        }
        return (await res.json()) as ProtocolCatalogPage;
      })
      .then((data) => {
        if (cancelled) return;
        setPage(data);
        setError(null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [state]);

  // Keep the address bar in sync for shareable/bookmarkable views.
  useEffect(() => {
    window.history.replaceState(null, "", explorerHref(state, basePath));
  }, [state, basePath]);

  // Filters, sort and page size return to page 1; only paging changes `page`.
  const patch = useCallback(
    (partial: Partial<ExplorerState>) =>
      setState((s) => ({ ...s, page: 1, ...partial })),
    [],
  );
  const goToPage = useCallback(
    (p: number) => setState((s) => (s.page === p ? s : { ...s, page: p })),
    [],
  );

  const items = page?.items ?? [];
  const total = page?.total ?? 0;
  const pages = page?.pages ?? 0;
  const window_ = useMemo(() => pageNumberWindow(state.page, pages), [state.page, pages]);

  const toggleOrder = () =>
    patch({ order: state.order === "asc" ? "desc" : "asc" });

  return (
    <div className="space-y-4">
      {/* Controls: search, filters, sort, page size - all drive server queries. */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[12rem] flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            placeholder="Search name or slug…"
            aria-label="Search protocols"
            className="pl-8"
          />
        </div>

        <Select value={state.category || ALL} onValueChange={(v) => patch({ category: v === ALL ? "" : v })}>
          <SelectTrigger size="sm" className="w-[150px]" aria-label="Filter by category">
            <SelectValue placeholder="Category" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All categories</SelectItem>
            {facets.categories.map((c) => (
              <SelectItem key={c} value={c}>{c}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={state.chain || ALL} onValueChange={(v) => patch({ chain: v === ALL ? "" : v })}>
          <SelectTrigger size="sm" className="w-[150px]" aria-label="Filter by chain">
            <SelectValue placeholder="Chain" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All chains</SelectItem>
            {facets.chains.map((c) => (
              <SelectItem key={c} value={c}>{c}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Risk-band filter: only monitored/scored protocols carry a real band;
            "unknown" is the honest bucket for the never-scored majority. */}
        <Select value={state.band || ALL} onValueChange={(v) => patch({ band: v === ALL ? "" : v })}>
          <SelectTrigger size="sm" className="w-[150px]" aria-label="Filter by risk band">
            <SelectValue placeholder="Risk band" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All risk bands</SelectItem>
            {RISK_BANDS.map((b) => (
              <SelectItem key={b} value={b}>{b}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={state.sort} onValueChange={(v) => patch({ sort: v as SortKey })}>
          <SelectTrigger size="sm" className="w-[160px]" aria-label="Sort by">
            <SelectValue placeholder="Sort by" />
          </SelectTrigger>
          <SelectContent>
            {(Object.keys(SORT_LABELS) as SortKey[]).map((k) => (
              <SelectItem key={k} value={k}>{SORT_LABELS[k]}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Button variant="outline" size="sm" onClick={toggleOrder} aria-label="Toggle sort direction">
          {state.order === "asc" ? <ArrowUp className="size-3.5" /> : <ArrowDown className="size-3.5" />}
          <span className="ml-1 hidden sm:inline">{state.order}</span>
        </Button>

        <Select
          value={String(state.pageSize)}
          onValueChange={(v) => patch({ pageSize: Number(v) as ExplorerState["pageSize"] })}
        >
          <SelectTrigger size="sm" className="w-[110px]" aria-label="Rows per page">
            <SelectValue placeholder="Per page" />
          </SelectTrigger>
          <SelectContent>
            {PAGE_SIZES.map((n) => (
              <SelectItem key={n} value={String(n)}>{n} / page</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span aria-live="polite">
          {loading ? "Loading…" : `${total.toLocaleString()} protocols`}
          {total > 0 && !loading ? ` · page ${state.page} of ${pages}` : null}
        </span>
      </div>

      {error ? (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm">
          <h2 className="mb-1 font-semibold text-red-600 dark:text-red-300">
            Could not load protocols
          </h2>
          <p className="text-red-700/80 dark:text-red-200/80">{error}</p>
        </div>
      ) : (
        <Card>
          {/* Fixed-height, scrollable container: the box stays the same size
              whatever the page size (25/50/100) or the row count on the last
              page - only the list scrolls inside it. The header is sticky so the
              column labels stay readable while scrolling. */}
          <CardContent className="p-0 [&_[data-slot=table-container]]:h-[420px] [&_[data-slot=table-container]]:overflow-auto">
            <Table>
              <TableHeader className="[&>tr>th]:sticky [&>tr>th]:top-0 [&>tr>th]:z-10 [&>tr>th]:bg-card">
                <TableRow>
                  <TableHead>Protocol</TableHead>
                  <TableHead className="hidden md:table-cell">Category</TableHead>
                  <TableHead className="text-right">TVL</TableHead>
                  <TableHead className="hidden text-right sm:table-cell">1d</TableHead>
                  <TableHead className="hidden text-right lg:table-cell">1m</TableHead>
                  <TableHead>Risk</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading && items.length === 0
                  ? Array.from({ length: state.pageSize }).map((_, i) => (
                      <TableRow key={`sk-${i}`}>
                        <TableCell colSpan={6}>
                          <div className="h-5 w-full animate-pulse rounded bg-muted" />
                        </TableCell>
                      </TableRow>
                    ))
                  : items.map((p) => (
                      <TableRow key={p.slug}>
                        <TableCell className="font-medium">
                          <Link
                            href={`/protocols/${p.slug}`}
                            className="text-emerald-600 hover:underline dark:text-emerald-400"
                          >
                            {p.name}
                          </Link>
                          {p.monitored && (
                            <span className="ml-2 rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] text-emerald-700 dark:text-emerald-400">
                              monitored
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="hidden text-muted-foreground md:table-cell">
                          {p.category ?? "n/a"}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">{fmtUsd(p.tvl)}</TableCell>
                        <TableCell className="hidden text-right sm:table-cell">
                          <ChangeCell value={p.change_1d} />
                        </TableCell>
                        <TableCell className="hidden text-right lg:table-cell">
                          <ChangeCell value={p.change_1m} />
                        </TableCell>
                        <TableCell>
                          {p.risk_score == null ? (
                            <span className="text-xs text-muted-foreground">not scored</span>
                          ) : (
                            <RiskBadge score={p.risk_score} band={p.risk_band} />
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                {!loading && items.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="h-24 text-center text-muted-foreground">
                      No protocols match your search. Try clearing filters or a different term.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Pagination: prev / windowed page numbers / next, all server-driven. */}
      {!error && pages > 1 && (
        <div className="flex flex-wrap items-center justify-center gap-1">
          <Button
            variant="outline"
            size="sm"
            onClick={() => goToPage(state.page - 1)}
            disabled={state.page <= 1 || loading}
            aria-label="Previous page"
          >
            <ChevronLeft className="size-4" />
          </Button>
          {window_.map((n, i) =>
            n === null ? (
              <span key={`gap-${i}`} className="px-1 text-muted-foreground">
                …
              </span>
            ) : (
              <Button
                key={n}
                variant={n === state.page ? "default" : "outline"}
                size="sm"
                onClick={() => goToPage(n)}
                disabled={loading}
                aria-current={n === state.page ? "page" : undefined}
              >
                {n}
              </Button>
            ),
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => goToPage(state.page + 1)}
            disabled={state.page >= pages || loading}
            aria-label="Next page"
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
