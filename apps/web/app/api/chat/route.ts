import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { ApiError, api } from "@/lib/api";

// Same-origin proxy for the non-streaming chat fallback. The browser hits this
// Next endpoint (never the compose-internal API host directly); we forward the
// question to the backend and return its ChatAnswer verbatim. Used whenever the
// WebSocket can't be established (locked-down networks, tunnel quirks).
export async function POST(req: NextRequest): Promise<NextResponse> {
  let question = "";
  let protocolSlug: string | null = null;
  try {
    const body = await req.json();
    question = typeof body?.question === "string" ? body.question.trim() : "";
    protocolSlug = typeof body?.protocol_slug === "string" ? body.protocol_slug : null;
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }
  if (!question) {
    return NextResponse.json({ error: "question is required" }, { status: 400 });
  }
  try {
    const answer = await api.chat(question, protocolSlug);
    return NextResponse.json(answer);
  } catch (e) {
    // A refusal keeps its own status: `chat:ask` missing or an expired session is
    // an authorization answer, not the "API unavailable" a 502 would imply.
    if (e instanceof ApiError) {
      return NextResponse.json(e.toJSON(), { status: e.status });
    }
    const message = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
