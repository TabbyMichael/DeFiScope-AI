import { NextResponse } from "next/server";

import { ApiError, api } from "@/lib/api";
import { parseExplorerState, toCatalogQuery } from "@/lib/explorer";

/**
 * Same-origin read of the paginated discovery catalog.
 *
 * The Explorer is an interactive client surface, but the backend base URL is a
 * compose-internal host the browser cannot resolve (and the session cookie must
 * never be replayed from the client). So the browser calls *this* route, which
 * forwards its own validated query upstream via the server-only ``api``. Only one
 * page of rows ever crosses the wire - pagination, search, filtering and sorting
 * all stay server-side.
 *
 * Reading the request's cookies (through ``api``) already makes this route
 * dynamic under Cache Components; the explicit ``no-store`` response header also
 * keeps a scope-filtered page out of any shared cache.
 */
export async function GET(request: Request): Promise<NextResponse> {
  const sp = request.url ? new URL(request.url).searchParams : new URLSearchParams();
  const state = parseExplorerState({
    page: sp.get("page") ?? undefined,
    page_size: sp.get("page_size") ?? undefined,
    sort: sp.get("sort") ?? undefined,
    order: sp.get("order") ?? undefined,
    q: sp.get("q") ?? undefined,
    chain: sp.get("chain") ?? undefined,
    category: sp.get("category") ?? undefined,
  });

  try {
    const page = await api.protocols(toCatalogQuery(state));
    return NextResponse.json(page, { headers: { "Cache-Control": "no-store" } });
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json(e.toJSON(), {
        status: e.status,
        headers: { "Cache-Control": "no-store" },
      });
    }
    const message = e instanceof Error ? e.message : String(e);
    return NextResponse.json(
      { error: message, reason: message },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}
