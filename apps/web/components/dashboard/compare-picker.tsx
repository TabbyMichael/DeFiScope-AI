"use client";

import { useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Plus, Search, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { MAX_COMPARE, parseSlugs, type CompareOption } from "@/lib/compare";

/**
 * Client-side protocol picker that drives the comparison via the URL
 * (`/compare?slugs=a,b,c`). The selected slugs are the single source of truth,
 * so the page stays shareable/bookmarkable and the RSC re-renders columns.
 *
 * Options are passed down from the server component so this client never calls
 * the internal `API_URL` directly (keeps it server-only, per lib/api.ts).
 */
export default function ComparePicker({ options }: { options: CompareOption[] }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { slugs } = parseSlugs(searchParams.get("slugs") ?? undefined);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const selectedSet = useMemo(() => new Set(slugs), [slugs]);
  const nameBySlug = useMemo(
    () => new Map(options.map((o) => [o.slug, o.name])),
    [options],
  );
  const full = slugs.length >= MAX_COMPARE;

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    return options
      .filter((o) => !selectedSet.has(o.slug))
      .filter(
        (o) =>
          !q ||
          o.name.toLowerCase().includes(q) ||
          o.slug.toLowerCase().includes(q) ||
          (o.category ?? "").toLowerCase().includes(q),
      )
      .slice(0, 60);
  }, [options, query, selectedSet]);

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
                ? `Comparison is limited to ${MAX_COMPARE} protocols — remove one to add another`
                : "Search protocols to compare…"
            }
            className="pl-8"
            aria-label="Search protocols to compare"
          />
        </div>

        {open && !full && matches.length > 0 && (
          <ul className="absolute z-10 mt-1 max-h-64 w-full overflow-auto rounded-md border bg-popover p-1 text-popover-foreground shadow-md">
            {matches.map((o) => (
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
            ))}
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
