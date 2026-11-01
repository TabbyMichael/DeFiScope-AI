// Protocol Explorer state: the single place that turns a browser URL's query
// string into a validated catalog query (and back). Every value is clamped to the
// closed sets the backend enforces, so a stray or hand-edited URL parameter can
// never produce a request the API would reject with a 422 - the UI simply falls
// back to the default for that field.
//
// The Explorer paginates, filters and sorts entirely server-side: this module
// only describes *which* page to ask for, never slices a local array.

import type { CatalogQuery } from "./api";

/** Allowed page sizes, mirroring the backend `CatalogPageSize` enum. */
export const PAGE_SIZES = [25, 50, 100] as const;
export type PageSize = (typeof PAGE_SIZES)[number];

/** Sort keys the catalog accepts, mapped to their display labels. */
export const SORT_LABELS = {
  tvl: "TVL",
  name: "Name",
  updated: "Recently updated",
  risk: "Risk score",
} as const;
export type SortKey = keyof typeof SORT_LABELS;
export type SortOrder = "asc" | "desc";

/** The Explorer's full view state - one page's worth of controls. */
export interface ExplorerState {
  page: number;
  pageSize: PageSize;
  q: string;
  chain: string;
  category: string;
  band: string;
  sort: SortKey;
  order: SortOrder;
}

/** Risk bands the catalog can be filtered by ("unknown" = never scored). */
export const RISK_BANDS = ["low", "moderate", "elevated", "high", "unknown"] as const;

const DEFAULTS: ExplorerState = {
  page: 1,
  pageSize: 25,
  q: "",
  chain: "",
  category: "",
  band: "",
  sort: "tvl",
  order: "desc",
};

/** Next hands searchParams values as string | string[] | undefined. */
type SearchParamValue = string | string[] | undefined;
export type SearchParamRecord = Record<string, SearchParamValue>;

function first(value: SearchParamValue): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value ?? "";
}

const SORT_KEYS = Object.keys(SORT_LABELS) as string[];

/**
 * Parse and sanitize a URL query into an ``ExplorerState``.
 *
 * Unknown or out-of-range values degrade to the default rather than throwing, so
 * a shared/bookmarked link always renders *something* valid.
 */
export function parseExplorerState(sp: SearchParamRecord): ExplorerState {
  const pageRaw = Number.parseInt(first(sp.page), 10);
  const page = Number.isFinite(pageRaw) && pageRaw >= 1 ? pageRaw : 1;

  const pageSizeRaw = Number.parseInt(first(sp.page_size), 10);
  const pageSize = (PAGE_SIZES as readonly number[]).includes(pageSizeRaw)
    ? (pageSizeRaw as PageSize)
    : DEFAULTS.pageSize;

  const sortRaw = first(sp.sort);
  const sort = (SORT_KEYS.includes(sortRaw) ? sortRaw : DEFAULTS.sort) as SortKey;
  const order: SortOrder = first(sp.order) === "asc" ? "asc" : "desc";

  return {
    page,
    pageSize,
    sort,
    order,
    q: first(sp.q).trim(),
    chain: first(sp.chain).trim(),
    category: first(sp.category).trim(),
    band: first(sp.band).trim(),
  };
}

/** Narrow an ``ExplorerState`` to the backend catalog query it represents. */
export function toCatalogQuery(state: ExplorerState): CatalogQuery {
  return {
    page: state.page,
    pageSize: state.pageSize,
    q: state.q || undefined,
    chain: state.chain || undefined,
    category: state.category || undefined,
    band: state.band || undefined,
    sort: state.sort,
    order: state.order,
  };
}

/**
 * Serialize state to a shareable browser URL, omitting fields at their default
 * so ordinary links stay short (`/explore`, `/explore?q=aave&page=2`).
 *
 * `basePath` lets the same component live on another route (the Dashboard embeds
 * it at `/`) while still writing a URL that reloads that route with this view.
 */
export function explorerHref(state: ExplorerState, basePath = "/explore"): string {
  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  if (state.chain) params.set("chain", state.chain);
  if (state.category) params.set("category", state.category);
  if (state.band) params.set("band", state.band);
  if (state.sort !== DEFAULTS.sort) params.set("sort", state.sort);
  if (state.order !== DEFAULTS.order) params.set("order", state.order);
  if (state.pageSize !== DEFAULTS.pageSize) params.set("page_size", String(state.pageSize));
  if (state.page !== 1) params.set("page", String(state.page));
  const qs = params.toString();
  return qs ? `${basePath}?${qs}` : basePath;
}

/**
 * Serialize state to the query string the same-origin proxy is fetched with.
 *
 * Always sends the explicit page size and page so the backend's own defaults can
 * never silently disagree with what the UI thinks it asked for.
 */
export function explorerFetchQuery(state: ExplorerState): string {
  const params = new URLSearchParams();
  params.set("page", String(state.page));
  params.set("page_size", String(state.pageSize));
  params.set("sort", state.sort);
  params.set("order", state.order);
  if (state.q) params.set("q", state.q);
  if (state.chain) params.set("chain", state.chain);
  if (state.category) params.set("category", state.category);
  if (state.band) params.set("band", state.band);
  return params.toString();
}

/**
 * Page numbers to show in the pager, as a compact window around the current page
 * with the first and last always present. Non-numeric gaps render as an ellipsis
 * (the sentinel ``null``), so the control never sprawls across 200 buttons.
 */
export function pageNumberWindow(
  current: number,
  pages: number,
  radius = 1,
): (number | null)[] {
  if (pages <= 0) return [];
  const wanted = new Set<number>([1, pages, current]);
  for (let p = current - radius; p <= current + radius; p += 1) {
    if (p >= 1 && p <= pages) wanted.add(p);
  }
  const sorted = [...wanted].sort((a, b) => a - b);
  const out: (number | null)[] = [];
  let prev = 0;
  for (const n of sorted) {
    if (prev && n - prev > 1) out.push(null); // ellipsis marker
    out.push(n);
    prev = n;
  }
  return out;
}
