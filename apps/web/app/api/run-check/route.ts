import { NextResponse } from "next/server";

import { ApiError, api } from "@/lib/api";

// Manual monitoring trigger. Runs server-side (the backend base URL is a
// compose-internal host the browser cannot resolve) and returns the alerts that
// fired. POST handlers are always dynamic - no cache is applied.
//
// A refusal is forwarded with its own status and reason: "the snapshot is fresh,
// a crawl would be redundant" and "outside business hours" are the point of the
// endpoint, not an error to be swallowed into a generic 502.
export async function POST(): Promise<NextResponse> {
  try {
    const alerts = await api.runAlerts();
    return NextResponse.json({ ok: true, count: alerts.length, alerts });
  } catch (e) {
    if (e instanceof ApiError) {
      return NextResponse.json(
        { ok: false, ...e.toJSON() },
        { status: e.status },
      );
    }
    const message = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ ok: false, error: message }, { status: 502 });
  }
}
