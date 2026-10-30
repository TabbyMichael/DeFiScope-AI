import type {
  Alert,
  ChatAnswer,
  DashboardResponse,
  ProtocolOverview,
  ProtocolResearch,
  ResearchBrief,
  RiskPoint,
  TvlPoint,
} from "./types";

/**
 * Resolve the browser-reachable API base URL.
 *
 * `serverUrl` is what the Next server uses for its own fetches. In Docker that
 * is the compose-internal host (e.g. `http://api:8000`), which a browser cannot
 * resolve — so a distinct `publicUrl` is configured for anything opened by the
 * user (the docs link, future client-side calls). With no `publicUrl` set (local
 * dev), it falls back to the server URL, then to localhost.
 */
export function resolveApiPublicUrl(
  publicUrl: string | undefined,
  serverUrl: string | undefined,
  fallback = "http://localhost:8000",
): string {
  return publicUrl ?? serverUrl ?? fallback;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

// Guard against a hung backend stalling a server-component render forever.
// Most reads hit the 5-min in-process cache / DB and return in well under this;
// the cold dashboard hydration and LLM briefs opt into longer budgets.
const DEFAULT_TIMEOUT_MS = 30_000;
const BRIEF_TIMEOUT_MS = 120_000; // LLM brief generation allows up to ~90s upstream

async function get<T>(
  path: string,
  revalidate = 300,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    next: { revalidate },
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status} ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

/**
 * Server-side POST to the backend. Used by the `/api/run-check` route handler
 * (never called directly from the browser) so the compose-internal `API_URL`
 * stays server-only and the client hits a same-origin Next endpoint instead.
 */
async function post<T>(path: string, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    signal: AbortSignal.timeout(timeoutMs),
    // A manual run must always hit fresh upstream data, never a cached response.
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status} ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

/** Server-side POST with a JSON body (used by the same-origin /api/chat proxy). */
async function postJson<T>(
  path: string,
  body: unknown,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status} ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

// A manual monitoring pass crawls the watchlist live; give it a generous budget.
const RUN_TIMEOUT_MS = 120_000;

export const api = {
  // Cold hydration may run a live DefiLlama crawl; give it a generous budget.
  dashboard: () => get<DashboardResponse>("/api/dashboard", 120, 60_000),
  protocols: () => get<ProtocolOverview[]>("/api/protocols", 300, 60_000),
  protocol: (slug: string) => get<ProtocolResearch>(`/api/protocols/${encodeURIComponent(slug)}`),
  protocolHistory: (slug: string, days = 30) =>
    get<TvlPoint[]>(`/api/protocols/${encodeURIComponent(slug)}/history?days=${days}`),
  riskHistory: (slug: string, days = 90) =>
    get<RiskPoint[]>(
      `/api/protocols/${encodeURIComponent(slug)}/risk-history?days=${days}`,
    ),
  brief: (slug: string) =>
    get<ResearchBrief>(`/api/briefs/${encodeURIComponent(slug)}`, 3600, BRIEF_TIMEOUT_MS),
  alerts: () => get<Alert[]>("/api/alerts"),
  alertHistory: () => get<Alert[]>("/api/alerts/history"),
  // Trigger a full monitoring pass server-side (invoked via the route handler).
  runAlerts: () => post<Alert[]>("/api/alerts/run", RUN_TIMEOUT_MS),
  // Grounded chat, called by the same-origin /api/chat route handler so the
  // compose-internal API_URL stays server-only. Non-streaming fallback for the
  // WS path; give it the brief-length budget (a model answer can take ~90s).
  chat: (question: string, protocol_slug?: string | null) =>
    postJson<ChatAnswer>("/api/chat", { question, protocol_slug: protocol_slug ?? null }, BRIEF_TIMEOUT_MS),
};

/**
 * Fetch a rendered brief export (md | csv | pdf) as raw bytes from the
 * server-only API. Called only by the same-origin `/api/brief-export/[slug]`
 * route handler, so the compose-internal `API_URL` is never exposed to the
 * browser. The upstream `Response` is returned un-parsed so the handler can
 * forward `Content-Type` / `Content-Disposition` straight to the client.
 */
export async function fetchBriefExport(slug: string, format: string): Promise<Response> {
  return fetch(
    `${API_URL}/api/briefs/${encodeURIComponent(slug)}/export?format=${encodeURIComponent(format)}`,
    { cache: "no-store", signal: AbortSignal.timeout(BRIEF_TIMEOUT_MS) },
  );
}

export function fmtUsd(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
  if (value >= 1e3) return `$${(value / 1e3).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
}

export function fmtPct(value: number | null | undefined, digits = 1): string {
  if (value == null) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
}
