import { NextResponse } from "next/server";

import { readToken } from "@/lib/auth";
import { apiBase, reasonOf } from "@/lib/auth-proxy";

// Mint a single-use WebSocket ticket for the browser-opened `/ws/chat`.
//
// `new WebSocket()` cannot carry an Authorization header, and the socket is
// opened against the API port directly — so the credential has to be a URL
// parameter. This handler exchanges the httpOnly cookie for a 60-second,
// single-use ticket, which keeps the long-lived session token out of the URL
// (and out of access logs and browser history).
export async function POST(): Promise<NextResponse> {
  const token = await readToken();
  if (!token) {
    return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${apiBase()}/api/auth/ticket`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
  } catch {
    return NextResponse.json({ error: "Authentication service unreachable" }, { status: 502 });
  }

  const data = (await upstream.json().catch(() => ({}))) as {
    ticket?: string;
    expires_in?: number;
  };
  if (!upstream.ok) {
    return NextResponse.json(
      { error: reasonOf(data, "Could not mint a chat ticket") },
      { status: upstream.status },
    );
  }

  return NextResponse.json({
    ticket: data.ticket ?? "",
    expires_in: data.expires_in ?? 0,
  });
}
