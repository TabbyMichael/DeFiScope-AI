import { NextResponse } from "next/server";

import { SESSION_COOKIE, readToken, sessionCookieOptions } from "@/lib/auth";
import { apiBase } from "@/lib/auth-proxy";

// Sign out. The session row is deleted first, so the token is dead even if the
// response is lost in flight; the cookie is cleared regardless of the outcome.
export async function POST(): Promise<NextResponse> {
  const token = await readToken();
  if (token) {
    try {
      await fetch(`${apiBase()}/api/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
        signal: AbortSignal.timeout(10_000),
      });
    } catch {
      /* unreachable backend: still clear the local cookie below */
    }
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, "", sessionCookieOptions(0));
  return response;
}
