/**
 * Shared plumbing for the same-origin `/api/auth/*` route handlers.
 *
 * These handlers exist so the browser never talks to the API host directly with
 * a credential in the URL or the body: the token is minted server-side and
 * parked in an httpOnly cookie. They forward to FastAPI and translate the
 * answer — they do not decide anything. A refusal from FastAPI is passed
 * through with its status and message intact.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function apiBase(): string {
  return API_URL;
}

/** Parse a JSON body, tolerating an empty or malformed one. */
export async function readJson(req: Request): Promise<Record<string, unknown>> {
  try {
    const parsed: unknown = await req.json();
    return parsed && typeof parsed === "object"
      ? (parsed as Record<string, unknown>)
      : {};
  } catch {
    return {};
  }
}

/**
 * The reason from a FastAPI error body, whether it is a bare string `detail`
 * or the structured `{error, policy, reason, failed_predicate}` denial shape.
 */
export function reasonOf(data: unknown, fallback: string): string {
  if (!data || typeof data !== "object") return fallback;
  const record = data as Record<string, unknown>;
  const detail = record.detail;
  if (typeof detail === "string" && detail) return detail;
  if (detail && typeof detail === "object") {
    const nested = detail as Record<string, unknown>;
    if (typeof nested.reason === "string" && nested.reason) return nested.reason;
    if (typeof nested.error === "string" && nested.error) return nested.error;
  }
  if (typeof record.reason === "string" && record.reason) return record.reason;
  if (typeof record.error === "string" && record.error) return record.error;
  return fallback;
}
