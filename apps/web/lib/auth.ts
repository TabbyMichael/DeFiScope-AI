/**
 * Server-only session helpers.
 *
 * The browser holds an httpOnly cookie; this module is the only place that
 * knows its name and can read it. FastAPI remains the authority — every call
 * here is a *lookup*, and a 401 from the backend is the real signal that a
 * session is gone. Nothing in `apps/web` is a security boundary: `proxy.ts`
 * only redirects, and every request that matters is re-authorized by FastAPI.
 */

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";

import type { SubjectOut } from "./types";

/** Name of the httpOnly cookie holding the opaque session token. */
export const SESSION_COOKIE =
  process.env.DEFISCOPE_AUTH_COOKIE_NAME ?? "defiscope_session";

/**
 * `off` | `demo` | `required`. Not a security control on this side — it only
 * decides whether the UI nags about signing in and whether the role switcher
 * is offered. FastAPI refuses requests on its own.
 */
export const AUTH_MODE = (process.env.DEFISCOPE_AUTH_MODE ?? "demo").toLowerCase();
export const AUTH_ENFORCED = AUTH_MODE !== "off";

/** Four one-click demo buttons on the login page (demo mode only). */
export const DEMO_LOGIN = process.env.NEXT_PUBLIC_AUTH_DEMO === "1";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Session {
  /** Raw bearer token. `null` in `off` mode, where FastAPI needs no credential. */
  token: string | null;
  subject: SubjectOut;
  expiresAt: string | null;
}

/**
 * Subject used when `DEFISCOPE_AUTH_MODE=off` and the API is unreachable, and
 * as the shape the UI degrades to if `/api/auth/me` fails. Deliberately
 * permissive: in `off` mode there is no authorization to model, and the backend
 * agrees.
 */
export const ANONYMOUS_SUBJECT: SubjectOut = {
  user_id: "anonymous",
  email: "anonymous@local",
  role: "admin",
  team: null,
  clearance: 3,
  categories: ["*"],
  chains: ["*"],
  authenticated: false,
  permissions: [],
};

/**
 * Read the session token from the incoming cookie jar.
 *
 * Returns `null` outside a request scope (build-time prerender, unit tests):
 * `cookies()` throws there, and a missing cookie must never be fatal.
 */
export async function readToken(): Promise<string | null> {
  try {
    const jar = await cookies();
    return jar.get(SESSION_COOKIE)?.value ?? null;
  } catch {
    return null;
  }
}

/**
 * Current session, or `null` when the caller holds no valid credential.
 *
 * Wrapped in React's `cache()` so the server component tree resolves it once
 * per request even though the header, the page and the data loader all ask.
 */
export const getSession = cache(async (): Promise<Session | null> => {
  const token = await readToken();
  try {
    const res = await fetch(`${API_URL}/api/auth/me`, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok) return null;
    const subject = (await res.json()) as SubjectOut;
    return { token, subject, expiresAt: null };
  } catch {
    // Backend down. In `off` mode nothing is being authorized anyway, so keep
    // the board rendering instead of bouncing the user to /login.
    if (!AUTH_ENFORCED) {
      return { token, subject: ANONYMOUS_SUBJECT, expiresAt: null };
    }
    return null;
  }
});

/** Convenience for server components that must have a caller. */
export async function requireUser(): Promise<Session> {
  const session = await getSession();
  if (session) return session;
  redirect("/login");
}

/**
 * Permission check for UI affordances only (hiding a button, disabling a
 * download). The same permission is enforced again by FastAPI on the actual
 * call — this function existing does not make the UI authoritative.
 */
export function hasPermission(
  session: Session | null,
  permission: string,
): boolean {
  if (!AUTH_ENFORCED) return true;
  return Boolean(session?.subject.permissions.includes(permission));
}

/** Role switcher is a demo affordance; `required` mode never offers it. */
export function canSwitchRole(session: Session | null): boolean {
  return AUTH_MODE === "demo" && Boolean(session);
}

/**
 * Cookie attributes for the session token.
 *
 * `httpOnly` keeps it out of reach of any script on the page, `SameSite=Lax`
 * lets a top-level navigation land signed in while still blocking cross-site
 * POSTs, and `Secure` is on in production unless explicitly disabled
 * (`DEFISCOPE_COOKIE_SECURE=0` for a plain-http staging tunnel).
 */
export function sessionCookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure:
      process.env.NODE_ENV === "production" &&
      process.env.DEFISCOPE_COOKIE_SECURE !== "0",
    path: "/",
    maxAge,
  };
}
