import { NextResponse } from "next/server";

import { fetchBriefExport } from "@/lib/api";

// Brief downloads are proxied through the Next server so the browser only ever
// hits a same-origin URL and the compose-internal API host stays server-only.
// Reading `format` from the request URL (and the dynamic slug segment) makes
// this handler inherently dynamic - under Cache Components we must NOT set the
// `dynamic` segment config, which is disallowed there.
const ALLOWED = new Set(["md", "csv", "pdf"]);

export async function GET(
  req: Request,
  ctx: { params: Promise<{ slug: string }> },
): Promise<NextResponse> {
  const { slug } = await ctx.params;
  const format = new URL(req.url).searchParams.get("format") ?? "md";
  if (!ALLOWED.has(format)) {
    return new NextResponse("unsupported format", { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await fetchBriefExport(slug, format);
  } catch {
    return new NextResponse("export unavailable", { status: 502 });
  }

  if (!upstream.ok) {
    const detail = await upstream.text().catch(() => "");
    return new NextResponse(detail || "export failed", { status: upstream.status });
  }

  const body = await upstream.arrayBuffer();
  const headers = new Headers();
  headers.set(
    "Content-Type",
    upstream.headers.get("Content-Type") ?? "application/octet-stream",
  );
  headers.set(
    "Content-Disposition",
    upstream.headers.get("Content-Disposition") ?? `attachment; filename="defiscope-${slug}.${format}"`,
  );
  return new NextResponse(body, { status: 200, headers });
}
