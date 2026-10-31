import { NextResponse, type NextRequest } from "next/server";

/**
 * UX redirect only. This is NOT the security boundary.
 *
 * The browser reaches FastAPI two ways this file cannot see: the published API
 * port (`:8000` / `:3646`) and the direct WebSocket at `/ws/chat`. A guard that
 * lived here would be a lock on a door nobody uses. FastAPI re-authorizes every
 * request, so deleting this file costs a nicer first impression — not access
 * control.
 *
 * Its only job: an unauthenticated visitor to a page gets sent to `/login`
 * instead of watching three panels call the API and fail.
 *
 * `DEFISCOPE_AUTH_MODE=off` disables the redirect so the legacy escape hatch
 * (synthetic all-permissions principal) keeps working end to end.
 */
const SESSION_COOKIE = process.env.DEFISCOPE_AUTH_COOKIE_NAME ?? "defiscope_session";
const AUTH_MODE = (process.env.DEFISCOPE_AUTH_MODE ?? "demo").toLowerCase();

/** Paths that must stay reachable without a session. */
function isPublic(pathname: string): boolean {
  if (pathname === "/login") return true;
  // The marketing page has no data to leak — a visitor's only credential is
  // curiosity. Keeping it public is what lets the front door exist at all.
  if (pathname === "/welcome") return true;
  if (pathname.startsWith("/api/auth/")) return true;
  if (pathname === "/icon.svg" || pathname === "/favicon.ico") return true;
  return false;
}

export function proxy(req: NextRequest): NextResponse {
  if (AUTH_MODE === "off") return NextResponse.next();

  const { pathname, search } = req.nextUrl;
  if (isPublic(pathname)) return NextResponse.next();
  if (req.cookies.get(SESSION_COOKIE)?.value) return NextResponse.next();

  // The front door: an anonymous visitor landing on "/" gets the marketing
  // page instead of a login form. Deep links still go to /login so `?next=`
  // survives the sign-in and the visitor resumes where they were headed.
  if (pathname === "/") {
    const landing = req.nextUrl.clone();
    landing.pathname = "/welcome";
    return NextResponse.rewrite(landing);
  }

  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.search = "";
  url.searchParams.set("next", `${pathname}${search}`);
  return NextResponse.redirect(url);
}

export const config = {
  // Skip build assets and static files; everything else (pages + route
  // handlers) is checked. `/api/auth/*` is re-allowed inside `proxy`.
  matcher: [
    "/((?!_next/static|_next/image|favicon\\.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|css|js|map|txt|woff2?)$).*)",
  ],
};
