import { Suspense } from "react";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Activity, ArrowLeft, ShieldCheck } from "lucide-react";

import { LoginForm } from "@/components/auth/login-form";
import { Skeleton } from "@/components/ui/skeleton";
import { DEMO_LOGIN, getSession } from "@/lib/auth";

// Outside the (dashboard) route group on purpose: no sidebar, no data fetches,
// nothing that could leak a scoped board to someone who is not signed in.

/** Only relative paths are honoured, so `?next=` cannot bounce off-site. */
function safeNext(value: string | string[] | undefined): string {
  const raw = Array.isArray(value) ? value[0] : value;
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/";
  if (raw.startsWith("/login")) return "/";
  return raw;
}

async function LoginGate({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  const [session, params] = await Promise.all([getSession(), searchParams]);
  const next = safeNext(params.next);
  if (session?.subject.authenticated) redirect(next);

  return (
    <LoginForm
      demo={DEMO_LOGIN}
      demoPassword={process.env.NEXT_PUBLIC_AUTH_DEMO_PASSWORD ?? "defiscope-demo"}
      next={next}
    />
  );
}

function LoginFallback() {
  return (
    <div className="space-y-3 rounded-xl border border-border/70 bg-card/70 p-6">
      <Skeleton className="h-6 w-48" />
      <Skeleton className="h-9 w-full" />
      <Skeleton className="h-9 w-full" />
      <Skeleton className="h-9 w-full" />
    </div>
  );
}

export default function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  return (
    <div className="relative isolate flex min-h-svh flex-col items-center justify-center gap-6 overflow-hidden bg-background px-4 py-10">
      {/*
        The backdrop is three passive layers: one emerald wash from the top, two
        slowly drifting blooms, and a blueprint grid masked to an ellipse. None
        of it carries information, so it is hidden from assistive tech, and it
        sits at `-z-10` inside an `isolate` so it can never cover the card.
      */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -z-10 overflow-hidden"
      >
        <div className="absolute inset-0 bg-[radial-gradient(75%_55%_at_50%_-8%,rgba(16,185,129,0.18),transparent_70%)] dark:bg-[radial-gradient(75%_55%_at_50%_-8%,rgba(16,185,129,0.26),transparent_70%)]" />
        <div className="auth-drift absolute top-1/3 -left-36 size-[34rem] rounded-full bg-emerald-500/10 blur-3xl dark:bg-emerald-500/15" />
        <div className="auth-drift auth-drift-slow absolute -right-44 -bottom-32 size-[30rem] rounded-full bg-emerald-400/10 blur-3xl dark:bg-emerald-400/15" />
        <div className="auth-grid absolute inset-0" />
      </div>

      <div
        className="auth-rise flex items-center gap-2.5"
        style={{ animationDelay: "40ms" }}
      >
        <span className="flex size-10 items-center justify-center rounded-xl bg-emerald-500/15 text-emerald-600 ring-1 ring-emerald-500/25 ring-inset dark:text-emerald-400 dark:ring-emerald-400/25">
          <Activity className="size-5" strokeWidth={2} />
        </span>
        <div className="leading-tight">
          <div className="auth-mask text-[17px] font-semibold tracking-tight">
            <span style={{ animationDelay: "160ms" }}>DeFiScope AI</span>
          </div>
          <div className="text-[11px] tracking-[0.16em] text-muted-foreground uppercase">
            research · risk · monitoring
          </div>
        </div>
      </div>

      {/* The card carries the entrance; the form inside staggers its own rows
          so the eye lands on the email field last. */}
      <div
        className="auth-rise w-full max-w-md"
        style={{ animationDelay: "180ms" }}
      >
        <Suspense fallback={<LoginFallback />}>
          <LoginGate searchParams={searchParams} />
        </Suspense>
      </div>

      <p
        className="auth-rise flex max-w-md items-start gap-2 text-center text-xs leading-relaxed text-muted-foreground"
        style={{ animationDelay: "520ms" }}
      >
        <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
        <span>
          The API authorizes every request. This page only stores a session
          cookie. It is not a security boundary, and requests sent straight to
          the API port are refused on their own.
        </span>
      </p>

      {/* The other half of the funnel: a visitor who came from the marketing
          page can get back to it without editing the URL. */}
      <Link
        href="/welcome"
        className="auth-rise group inline-flex items-center gap-1.5 rounded-full border border-transparent px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-border hover:bg-muted/60 hover:text-foreground"
        style={{ animationDelay: "580ms" }}
      >
        <ArrowLeft className="size-3.5 transition-transform group-hover:-translate-x-0.5" />
        Back to home
      </Link>
    </div>
  );
}
