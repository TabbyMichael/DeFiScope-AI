/**
 * Client-safe API configuration and formatting helpers.
 *
 * This module must stay free of `next/headers` and any other server-only import:
 * client components (`chat-panel.tsx`, `stat-cards.tsx`, `protocol-explorer.tsx`,
 * `compare-matrix.tsx`, `watchlist-board.tsx`) pull from here, while
 * `lib/api.ts` — which reads the session cookie — pulls from here *and* adds the
 * server-only plumbing. Keeping the split means the browser bundle never
 * accidentally imports a `cookies()` accessor.
 */

/**
 * Resolve the browser-reachable API base URL.
 *
 * `serverUrl` is what the Next server uses for its own fetches. In Docker that
 * is the compose-internal host (e.g. `http://api:8000`), which a browser cannot
 * resolve — so a distinct `publicUrl` is configured for anything opened by the
 * user (the docs link, client-side calls). With no `publicUrl` set (local dev),
 * it falls back to the server URL, then to localhost.
 */
export function resolveApiPublicUrl(
  publicUrl: string | undefined,
  serverUrl: string | undefined,
  fallback = "http://localhost:8000",
): string {
  return publicUrl ?? serverUrl ?? fallback;
}

/**
 * Base URL a browser can actually open. Referenced statically so Next.js
 * inlines `NEXT_PUBLIC_API_PUBLIC_URL` at build time.
 */
export const API_PUBLIC_URL = resolveApiPublicUrl(
  process.env.NEXT_PUBLIC_API_PUBLIC_URL,
  process.env.NEXT_PUBLIC_API_URL,
);

/**
 * Resolve the browser-reachable WebSocket base for streamed chat tokens.
 * Prefers an explicit `NEXT_PUBLIC_API_WS_URL`; otherwise derives ws:/wss: from
 * the public (then server) HTTP URL. The browser must reach the API directly
 * here - the compose-internal `api:8000` host is not resolvable client-side,
 * so in Docker this is set to `ws://localhost:3646`.
 */
export function resolveApiWsUrl(
  wsUrl: string | undefined,
  publicUrl: string | undefined,
  serverUrl: string | undefined,
  fallback = "ws://localhost:8000",
): string {
  if (wsUrl) return wsUrl.replace(/\/+$/, "");
  const base = publicUrl ?? serverUrl ?? fallback;
  return base.replace(/^http/, "ws").replace(/\/+$/, "");
}

export const API_WS_URL = resolveApiWsUrl(
  process.env.NEXT_PUBLIC_API_WS_URL,
  process.env.NEXT_PUBLIC_API_PUBLIC_URL,
  process.env.NEXT_PUBLIC_API_URL,
);

export function fmtUsd(value: number | null | undefined): string {
  if (value == null) return "n/a";
  if (value >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
  if (value >= 1e3) return `$${(value / 1e3).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
}

export function fmtPct(value: number | null | undefined, digits = 1): string {
  if (value == null) return "n/a";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
}
