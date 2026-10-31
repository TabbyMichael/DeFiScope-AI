import { NextResponse } from "next/server";

import { SESSION_COOKIE, readToken, sessionCookieOptions } from "@/lib/auth";
import { apiBase, readJson, reasonOf } from "@/lib/auth-proxy";

// Demo role switching. FastAPI re-issues a session for another seeded account
// and revokes the caller's old one; this handler just swaps the cookie.
//
// Refused in `DEFISCOPE_AUTH_MODE=required` by the backend (403 `auth.switch`),
// and that refusal is surfaced verbatim rather than hidden behind a generic
// error — impersonation is a tour affordance, not a feature.
export async function POST(req: Request): Promise<NextResponse> {
  const body = await readJson(req);
  const email = typeof body.email === "string" ? body.email.trim() : "";
  if (!email) {
    return NextResponse.json({ error: "email is required" }, { status: 400 });
  }

  const token = await readToken();
  if (!token) {
    return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${apiBase()}/api/auth/switch`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ email }),
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    return NextResponse.json({ error: "Authentication service unreachable" }, { status: 502 });
  }

  const data = (await upstream.json().catch(() => ({}))) as {
    token?: string;
    expires_at?: string;
    subject?: unknown;
  };
  if (!upstream.ok || !data.token) {
    return NextResponse.json(
      { error: reasonOf(data, "Could not switch role") },
      { status: upstream.status || 400 },
    );
  }

  const response = NextResponse.json({ ok: true, subject: data.subject });
  response.cookies.set(
    SESSION_COOKIE,
    data.token,
    sessionCookieOptions(maxAgeSeconds(data.expires_at)),
  );
  return response;
}

function maxAgeSeconds(expiresAt: string | undefined): number {
  if (!expiresAt) return 60 * 60 * 12;
  const ms = Date.parse(expiresAt) - Date.now();
  return Number.isFinite(ms) && ms > 0 ? Math.floor(ms / 1000) : 60 * 60 * 12;
}
