import { cookies } from "next/headers";

import { SESSION_COOKIE } from "./auth";
import type {
  Alert,
  CatalogFacets,
  ChatAnswer,
  DashboardResponse,
  ProtocolCatalogPage,
  ProtocolResearch,
  ResearchBrief,
  RiskPoint,
  TvlPoint,
} from "./types";

// Client-safe constants and formatters live in ./api-config so browser
// components can import them without dragging `next/headers` into the bundle.
export {
  API_PUBLIC_URL,
  API_WS_URL,
  fmtPct,
  fmtUsd,
  resolveApiPublicUrl,
  resolveApiWsUrl,
} from "./api-config";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Guard against a hung backend stalling a server-component render forever.
// Most reads hit the 5-min in-process cache / DB and return in well under this;
// the cold dashboard hydration and LLM briefs opt into longer budgets.
const DEFAULT_TIMEOUT_MS = 30_000;
const BRIEF_TIMEOUT_MS = 120_000; // LLM brief generation allows up to ~90s upstream

/**
 * A structured failure from FastAPI.
 *
 * Authorization denials are not exceptional here: they are the product
 * behaviour we want to show. The backend returns
 * `{error, policy, reason, failed_predicate[, permission]}`, and the UI renders
 * `reason` verbatim, so `ApiError` carries it rather than flattening to text.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly policy: string | null;
  readonly reason: string;
  readonly failedPredicate: string | null;
  readonly permission: string | null;

  constructor(
    readonly path: string,
    status: number,
    detail: {
      error?: unknown;
      reason?: unknown;
      policy?: unknown;
      failed_predicate?: unknown;
      permission?: unknown;
      detail?: unknown;
    },
    fallbackText = "",
  ) {
    const reason =
      str(detail.reason) ??
      str(detail.error) ??
      str(detail.detail) ??
      fallbackText ??
      "";
    super(`API ${path} failed: ${status} ${reason}`.trim());
    this.name = "ApiError";
    this.status = status;
    this.reason = reason;
    this.policy = str(detail.policy);
    this.failedPredicate = str(detail.failed_predicate);
    this.permission = str(detail.permission);
  }

  /** 401/403: a deliberate refusal with an explanation, not a bug. */
  get isDenial(): boolean {
    return this.status === 401 || this.status === 403;
  }

  /** Serializable shape, so a Next route handler can forward it unchanged. */
  toJSON() {
    return {
      error: this.reason,
      policy: this.policy,
      reason: this.reason,
      failed_predicate: this.failedPredicate,
      permission: this.permission,
    };
  }
}

function str(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

async function readDetail(
  res: Response,
): Promise<{ detail: Record<string, unknown>; text: string }> {
  const text = await res.text().catch(() => "");
  try {
    const parsed = JSON.parse(text) as Record<string, unknown>;
    if (parsed && typeof parsed === "object") {
      // FastAPI wraps plain HTTPExceptions in `{"detail": {...}}`.
      const nested = parsed.detail;
      if (nested && typeof nested === "object" && !Array.isArray(nested)) {
        return { detail: { ...parsed, ...(nested as Record<string, unknown>) }, text };
      }
      return { detail: parsed, text };
    }
  } catch {
    /* not JSON, so keep the raw text */
  }
  return { detail: {}, text };
}

async function fail(path: string, res: Response): Promise<never> {
  const { detail, text } = await readDetail(res);
  throw new ApiError(path, res.status, detail, text);
}

/**
 * The session token, read from the incoming request's cookie jar.
 *
 * Returns `{}` when there is no cookie or no request scope (build-time
 * prerender, unit tests): the request then goes out unauthenticated and
 * FastAPI answers 401, which is the correct outcome rather than a crash.
 */
async function authHeaders(): Promise<Record<string, string>> {
  try {
    const jar = await cookies();
    const token = jar.get(SESSION_COOKIE)?.value;
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}

/**
 * Cache policy for one call.
 *
 * Authenticated responses are scope-filtered per subject, so they must never
 * enter Next's shared data cache. Another user's board would be replayed to
 * this one. `no-store` also keeps the browser/CDN out of it. Anonymous calls
 * (auth mode `off`) keep the previous revalidate windows.
 */
function cachePolicy(auth: Record<string, string>, revalidate: number) {
  return auth.Authorization
    ? ({ cache: "no-store" } as const)
    : ({ next: { revalidate } } as const);
}

async function get<T>(
  path: string,
  revalidate = 300,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const auth = await authHeaders();
  const res = await fetch(`${API_URL}${path}`, {
    headers: auth,
    ...cachePolicy(auth, revalidate),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) await fail(path, res);
  return res.json() as Promise<T>;
}

/**
 * Server-side GET that also exposes a response header. Used for the withheld
 * alert count, which rides in `X-Withheld-Alerts` so the payload stays a plain
 * array (no existing consumer breaks).
 */
async function getWithHeaders<T>(
  path: string,
  revalidate = 300,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<{ body: T; headers: Headers }> {
  const auth = await authHeaders();
  const res = await fetch(`${API_URL}${path}`, {
    headers: auth,
    ...cachePolicy(auth, revalidate),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) await fail(path, res);
  return { body: (await res.json()) as T, headers: res.headers };
}

/**
 * Server-side POST to the backend. Used by the `/api/run-check` route handler
 * (never called directly from the browser) so the compose-internal `API_URL`
 * stays server-only and the client hits a same-origin Next endpoint instead.
 */
async function post<T>(path: string, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const auth = await authHeaders();
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: auth,
    // A manual run must always hit fresh upstream data, never a cached response.
    cache: "no-store",
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) await fail(path, res);
  return res.json() as Promise<T>;
}

/** Server-side POST with a JSON body (used by the same-origin /api/chat proxy). */
async function postJson<T>(
  path: string,
  body: unknown,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const auth = await authHeaders();
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { ...auth, "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) await fail(path, res);
  return res.json() as Promise<T>;
}

// A manual monitoring pass crawls the watchlist live; give it a generous budget.
const RUN_TIMEOUT_MS = 120_000;

/** Alerts plus how many were withheld by a sensitivity gate. */
export interface AlertPage {
  alerts: Alert[];
  /** Rows removed by the clearance/scope gates. Always surfaced, never hidden. */
  withheld: number;
}

function withheldOf(headers: Headers): number {
  const raw = headers.get("X-Withheld-Alerts");
  const n = raw ? Number.parseInt(raw, 10) : 0;
  return Number.isFinite(n) && n > 0 ? n : 0;
}

/** Query for the paginated discovery catalog (`GET /api/protocols`). */
export interface CatalogQuery {
  page?: number;
  pageSize?: 25 | 50 | 100;
  q?: string;
  chain?: string;
  category?: string;
  band?: string;
  sort?: "tvl" | "name" | "updated" | "risk";
  order?: "asc" | "desc";
}

/**
 * Build the catalog query string, forwarding only the params that are set.
 *
 * Deliberately allowlisted: an unknown key can never reach the backend, and the
 * server still re-validates every value (page size / sort / order are closed
 * sets upstream), so this is a convenience boundary, not the security one.
 */
export function catalogQuerystring(query: CatalogQuery): string {
  const params = new URLSearchParams();
  if (query.page && query.page > 1) params.set("page", String(query.page));
  if (query.pageSize) params.set("page_size", String(query.pageSize));
  const q = query.q?.trim();
  if (q) params.set("q", q);
  if (query.chain) params.set("chain", query.chain);
  if (query.category) params.set("category", query.category);
  if (query.band) params.set("band", query.band);
  if (query.sort) params.set("sort", query.sort);
  if (query.order) params.set("order", query.order);
  const s = params.toString();
  return s ? `?${s}` : "";
}

export const api = {
  // Cold hydration may run a live DefiLlama crawl; give it a generous budget.
  dashboard: () => get<DashboardResponse>("/api/dashboard", 120, 60_000),
  // Discovery catalog: one page, filtered/sorted/served entirely server-side.
  protocols: (query: CatalogQuery = {}) =>
    get<ProtocolCatalogPage>(`/api/protocols${catalogQuerystring(query)}`, 120, 60_000),
  protocolFacets: () => get<CatalogFacets>("/api/protocols/facets", 300, 60_000),
  protocol: (slug: string) =>
    get<ProtocolResearch>(`/api/protocols/${encodeURIComponent(slug)}`),
  protocolHistory: (slug: string, days = 30) =>
    get<TvlPoint[]>(`/api/protocols/${encodeURIComponent(slug)}/history?days=${days}`),
  riskHistory: (slug: string, days = 90) =>
    get<RiskPoint[]>(
      `/api/protocols/${encodeURIComponent(slug)}/risk-history?days=${days}`,
    ),
  brief: (slug: string) =>
    get<ResearchBrief>(`/api/briefs/${encodeURIComponent(slug)}`, 3600, BRIEF_TIMEOUT_MS),
  alerts: async (): Promise<AlertPage> => {
    const { body, headers } = await getWithHeaders<Alert[]>("/api/alerts");
    return { alerts: body, withheld: withheldOf(headers) };
  },
  alertHistory: async (): Promise<AlertPage> => {
    const { body, headers } = await getWithHeaders<Alert[]>("/api/alerts/history");
    return { alerts: body, withheld: withheldOf(headers) };
  },
  // Trigger a full monitoring pass server-side (invoked via the route handler).
  runAlerts: () => post<Alert[]>("/api/alerts/run", RUN_TIMEOUT_MS),
  // Grounded chat, called by the same-origin /api/chat route handler so the
  // compose-internal API_URL stays server-only. Non-streaming fallback for the
  // WS path; give it the brief-length budget (a model answer can take ~90s).
  chat: (question: string, protocol_slug?: string | null) =>
    postJson<ChatAnswer>(
      "/api/chat",
      { question, protocol_slug: protocol_slug ?? null },
      BRIEF_TIMEOUT_MS,
    ),
};

/**
 * Fetch a rendered brief export (md | csv | pdf) as raw bytes from the
 * server-only API. Called only by the same-origin `/api/brief-export/[slug]`
 * route handler, so the compose-internal `API_URL` is never exposed to the
 * browser. The upstream `Response` is returned un-parsed so the handler can
 * forward `Content-Type` / `Content-Disposition` straight to the client.
 *
 * A refusal (403 `briefs.export.confidence_gate`, or an RBAC 403) comes back as
 * the standard `{error, policy, reason}` JSON body, which the handler forwards
 * verbatim so the UI can explain *why* the download was refused.
 */
export async function fetchBriefExport(slug: string, format: string): Promise<Response> {
  const auth = await authHeaders();
  return fetch(
    `${API_URL}/api/briefs/${encodeURIComponent(slug)}/export?format=${encodeURIComponent(format)}`,
    { headers: auth, cache: "no-store", signal: AbortSignal.timeout(BRIEF_TIMEOUT_MS) },
  );
}

/**
 * Mint a single-use WebSocket ticket.
 *
 * The socket is opened by the browser against the API port directly, and an
 * `Authorization` header cannot be set on `new WebSocket()`. The credential
 * therefore has to be something the browser can put in a URL: a short-lived,
 * single-use ticket redeemed before the socket is accepted.
 */
export async function mintChatTicket(): Promise<{ ticket: string; expiresIn: number }> {
  const body = await postJson<{ ticket: string; expires_in: number }>(
    "/api/auth/ticket",
    {},
  );
  return { ticket: body.ticket, expiresIn: body.expires_in };
}
