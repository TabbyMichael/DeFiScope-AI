"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Plus, Search, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { MAX_COMPARE, parseSlugs, type CompareOption } from "@/lib/compare";
import type { ProtocolCatalogPage } from "@/lib/types";

/** Max suggestions pulled per search - always a bounded page, never the catalog.
 * 50 is a value the /api/catalog proxy accepts unclamped (its allowed set is
 * 25/50/100), so the dropdown fills with a useful list instead of a silent 25. */
const RESULT_LIMIT = 50;
const DEBOUNCE_MS = 250;

/**
 * Client-side protocol picker that drives the comparison via the URL
 * (`/compare?slugs=a,b,c`). The selected slugs are the single source of truth,
 * so the page stays shareable/bookmarkable and the RSC re-renders columns.
 *
 * Search runs against the *full discovery catalog* (5,000+ protocols), entirely
 * server-side through the same-origin `/api/catalog` proxy: the browser never
 * calls the internal `API_URL` (kept server-only, per lib/api.ts) and never
 * downloads the whole catalog to filter it locally - only one bounded page of
 * matches is ever fetched, for the current query.
 */
export default function ComparePicker({ selected }: { selected: CompareOption[] }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { slugs } = parseSlugs(searchParams.get("slugs") ?? undefined);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<CompareOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const selectedSet = useMemo(() => new Set(slugs), [slugs]);
  // Selected badges always know their name (resolved server-side by the RSC),
  // so a chosen protocol keeps its label even once it leaves the suggestion list.
  const nameBySlug = useMemo(
    () => new Map(selected.map((o) => [o.slug, o.name])),
    [selected],
  );
  const full = slugs.length >= MAX_COMPARE;

  // Debounced server search. An empty query returns the top protocols by TVL, so
  // the list is useful the moment it is opened, before anything is typed.
  useEffect(() => {
    if (!open || full) return;
    const trimmed = query.trim();
    const params = new URLSearchParams();
    params.set("page", "1");
    params.set("page_size", String(RESULT_LIMIT));
    params.set("sort", "tvl");
    params.set("order", "desc");
    if (trimmed) params.set("q", trimmed);

    let cancelled = false;
    const t = setTimeout(() => {
      setLoading(true);
      fetch(`/api/catalog?${params.toString()}`)
        .then(async (res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return (await res.json()) as ProtocolCatalogPage;
        })
        .then((data) => {
          if (cancelled) return;
          setResults(
            data.items.map((i) => ({
              slug: i.slug,
              name: i.name,
              category: i.category ?? null,
            })),
          );
          setError(null);
        })
        .catch((e: unknown) => {
          if (cancelled) return;
          setError(e instanceof Error ? e.message : String(e));
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [query, open, full]);

  const matches = useMemo(
    () => results.filter((o) => !selectedSet.has(o.slug)).slice(0, RESULT_LIMIT),
    [results, selectedSet],
  );

  function commit(next: string[]) {
    const qs = next.length ? `?slugs=${next.join(",")}` : "";
    router.replace(`/compare${qs}`, { scroll: false });
  }

  function add(slug: string) {
    if (selectedSet.has(slug) || full) return;
    commit([...slugs, slug]);
    setQuery("");
    setOpen(false);
  }

  function remove(slug: string) {
    commit(slugs.filter((s) => s !== slug));
  }

  return (
    <div className="space-y-3">
      {slugs.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {slugs.map((slug) => (
            <Badge
              key={slug}
              variant="secondary"
              className="gap-1.5 py-1 pr-1 text-sm"
            >
              <span className="max-w-[16rem] truncate">
                {nameBySlug.get(slug) ?? slug}
              </span>
              <button
                type="button"
                onClick={() => remove(slug)}
                aria-label={`Remove ${nameBySlug.get(slug) ?? slug}`}
                className="flex size-4 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                <X className="size-3" />
              </button>
            </Badge>
          ))}
          <button
            type="button"
            onClick={() => commit([])}
            className="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
          >
            Clear all
          </button>
        </div>
      )}

      <div className="relative">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => setOpen(false)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && matches[0]) add(matches[0].slug);
              if (e.key === "Escape") setOpen(false);
            }}
            disabled={full}
            placeholder={
              full
                ? `Comparison is limited to ${MAX_COMPARE} protocols. Remove one to add another`
                : "Search all protocols to compare…"
            }
            className="pl-8"
            aria-label="Search protocols to compare"
          />
        </div>

        {open && !full && (loading || error || matches.length > 0) && (
          <ul className="absolute z-10 mt-1 max-h-64 w-full overflow-auto rounded-md border bg-popover p-1 text-popover-foreground shadow-md">
            {error ? (
              <li className="px-2 py-1.5 text-sm text-red-600 dark:text-red-400">
                Could not search protocols right now.
              </li>
            ) : loading && matches.length === 0 ? (
              <li className="px-2 py-1.5 text-sm text-muted-foreground">
                Searching…
              </li>
            ) : (
              matches.map((o) => (
                <li key={o.slug}>
                  <button
                    type="button"
                    // Keep focus while picking so the list stays open for multi-add.
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => add(o.slug)}
                    className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground"
                  >
                    <Plus className="size-3.5 shrink-0 text-muted-foreground" />
                    <span className="min-w-0 flex-1 truncate">{o.name}</span>
                    {o.category && (
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {o.category}
                      </span>
                    )}
                  </button>
                </li>
              ))
            )}
          </ul>
        )}
      </div>

      {full && (
        <p className="text-xs text-muted-foreground">
          Showing {slugs.length} of {MAX_COMPARE} slots.
        </p>
      )}
    </div>
  );
}
