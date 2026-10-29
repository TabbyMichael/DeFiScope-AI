import { NextResponse } from "next/server";

import { api } from "@/lib/api";

// Manual monitoring trigger. Runs server-side (the backend base URL is a
// compose-internal host the browser cannot resolve) and returns the alerts that
// fired. POST handlers are always dynamic - no cache is applied.
export async function POST(): Promise<NextResponse> {
  try {
    const alerts = await api.runAlerts();
    return NextResponse.json({ ok: true, count: alerts.length, alerts });
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ ok: false, error: message }, { status: 502 });
  }
}
