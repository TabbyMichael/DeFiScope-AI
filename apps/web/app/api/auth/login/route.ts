import { NextResponse } from "next/server";

import { SESSION_COOKIE, sessionCookieOptions } from "@/lib/auth";
import { apiBase, readJson } from "@/lib/auth-proxy";

// Sign in. The Next server holds the token in an httpOnly cookie and FastAPI
// never sees a password beyond this one call. Failures are forwarded with the
// upstream status so a 401 stays a 401 (the login form shows the message).
export async function POST(req: Request): Promise<NextResponse> {
  const body = await readJson(req);
  const email = typeof body.email === "string" ? body.email.trim() : "";
  const password = typeof body.password === "string" ? body.password : "";
  if (!email || !password) {
    return NextResponse.json(
      { error: "Email and password are required" },
      { status: 400 },
    );
  }

  let upstream: Response;
  try {
    upstream = await postLogin(email, password);
  } catch {
    // One retry, seconds later. The usual cause is not a dead API but a busy
    // one: the startup catalog pre-seed can hold the API's single event loop
    // for a stretch, and the first attempt times out mid-queue. By the second
    // the loop has usually yielded again. A real outage just fails twice.
    await new Promise((r) => setTimeout(r, 1_500));
    try {
      upstream = await postLogin(email, password);
    } catch {
      return NextResponse.json({ error: "Authentication service unreachable" }, { status: 502 });
    }
  }

  const data = (await upstream.json().catch(() => ({}))) as {
    token?: string;
    expires_at?: string;
    subject?: unknown;
    detail?: unknown;
  };
  if (!upstream.ok || !data.token) {
    const message =
      typeof data.detail === "string" ? data.detail : "Email or password is incorrect";
    return NextResponse.json({ error: message }, { status: upstream.status || 401 });
  }

  const response = NextResponse.json({ ok: true, subject: data.subject });
  response.cookies.set(
    SESSION_COOKIE,
    data.token,
    sessionCookieOptions(maxAgeSeconds(data.expires_at)),
  );
  return response;
}

/** One upstream attempt. Generous timeout: a busy API answers late, not never. */
function postLogin(email: string, password: string): Promise<Response> {
  return fetch(`${apiBase()}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
    cache: "no-store",
    signal: AbortSignal.timeout(30_000),
  });
}

/** Cookie lifetime derived from the session row, not guessed. */
function maxAgeSeconds(expiresAt: string | undefined): number {
  if (!expiresAt) return 60 * 60 * 12;
  const ms = Date.parse(expiresAt) - Date.now();
  return Number.isFinite(ms) && ms > 0 ? Math.floor(ms / 1000) : 60 * 60 * 12;
}
