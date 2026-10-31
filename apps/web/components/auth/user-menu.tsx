"use client";

import { ChevronDown, LogIn, LogOut, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { DEMO_ACCOUNTS } from "@/lib/demo-accounts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { SubjectOut } from "@/lib/types";

/** Per-role styling for the role chip; purely cosmetic. */
const ROLE_STYLE: Record<string, string> = {
  admin: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  risk_officer: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  analyst: "bg-sky-500/15 text-sky-700 dark:text-sky-300",
  viewer: "bg-muted text-muted-foreground",
};

function scopeLabel(values: string[]): string {
  if (!values.length) return "none";
  if (values.includes("*")) return "all";
  return values.join(", ");
}

function initials(subject: SubjectOut): string {
  const source = subject.email.split("@")[0] ?? "";
  return source.slice(0, 2).toUpperCase() || "??";
}

export function UserMenu({
  subject,
  demo,
}: {
  subject: SubjectOut;
  demo: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function switchTo(email: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/switch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      if (!res.ok) {
        setError(data.error ?? `Switch failed (${res.status})`);
        return;
      }
      // Every server component above was rendered for the previous subject.
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error");
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    setBusy(true);
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      // A full navigation, not `router.replace`. Signing out must drop every
      // client-cached RSC payload for the pages this session was allowed to
      // see — otherwise Back resurrects the dashboard from the router cache.
      // The landing page is public, so it is the one destination that cannot
      // bounce a signed-out visitor straight back into a login form.
      window.location.replace("/welcome");
    }
  }

  if (!subject.authenticated) {
    return (
      <Button asChild variant="outline" size="sm">
        <a href="/login">
          <LogIn className="size-3.5" />
          Sign in
        </a>
      </Button>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-2 rounded-full border px-2 py-1 text-xs transition-colors hover:bg-accent"
          aria-label={`Signed in as ${subject.email}`}
        >
          <span
            className={`flex size-6 items-center justify-center rounded-full text-[10px] font-semibold ${ROLE_STYLE[subject.role] ?? ROLE_STYLE.viewer}`}
          >
            {initials(subject)}
          </span>
          <span className="hidden text-left leading-tight sm:block">
            <span className="block font-medium">{subject.role.replace("_", " ")}</span>
            <span className="block text-[10px] text-muted-foreground">
              clearance {subject.clearance} · {scopeLabel(subject.categories)}
            </span>
          </span>
          <ChevronDown className="size-3.5 text-muted-foreground" />
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel>
          <span className="block text-sm font-medium text-foreground">{subject.email}</span>
          <span className="block text-xs">
            {subject.team ?? "no team"} · clearance {subject.clearance}
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <div className="space-y-1 px-1.5 py-1.5 text-xs text-muted-foreground">
          <p>
            <span className="font-medium text-foreground">Categories:</span>{" "}
            {scopeLabel(subject.categories)}
          </p>
          <p>
            <span className="font-medium text-foreground">Chains:</span>{" "}
            {scopeLabel(subject.chains)}
          </p>
          <p className="flex items-center gap-1">
            <ShieldCheck className="size-3" />
            {subject.permissions.length} permission
            {subject.permissions.length === 1 ? "" : "s"}
          </p>
        </div>

        {demo && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuLabel>Switch role: demo</DropdownMenuLabel>
            {DEMO_ACCOUNTS.map((acct) => (
              <DropdownMenuItem
                key={acct.email}
                disabled={busy || acct.email === subject.email}
                onSelect={() => void switchTo(acct.email)}
              >
                <span className="flex-1">{acct.label}</span>
                {acct.email === subject.email && (
                  <Badge variant="secondary" className="text-[10px]">
                    current
                  </Badge>
                )}
              </DropdownMenuItem>
            ))}
          </>
        )}

        {error && (
          <p className="px-1.5 py-1 text-xs text-red-600 dark:text-red-400" role="alert">
            {error}
          </p>
        )}

        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" onSelect={() => void signOut()}>
          <LogOut />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
