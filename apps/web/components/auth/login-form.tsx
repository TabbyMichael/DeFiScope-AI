"use client";

import { Loader2, LogIn, RotateCcw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { DEMO_ACCOUNTS } from "@/lib/demo-accounts";

export function LoginForm({
  demo,
  demoPassword,
  next,
}: {
  demo: boolean;
  demoPassword: string;
  next: string;
}) {
  const router = useRouter();
  const emailRef = useRef<HTMLInputElement>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Anything to clear? Keeps the Reset button honest when the form is empty. */
  const dirty = email.length > 0 || password.length > 0 || error !== null;

  /**
   * Clears the form, not the session. This page owns exactly two pieces of
   * state, so "reset" means forget them and put the cursor back where a retry
   * starts — it must not touch the cookie, which only `/api/auth/login` and
   * `/api/auth/logout` may write.
   */
  function reset() {
    setEmail("");
    setPassword("");
    setError(null);
    emailRef.current?.focus();
  }

  async function signIn(withEmail: string, withPassword: string) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: withEmail, password: withPassword }),
      });
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      if (!res.ok) {
        setError(data.error ?? `Sign-in failed (${res.status})`);
        return;
      }
      // A fresh render is required: every server component below was resolved
      // as an unauthenticated caller.
      router.replace(next);
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="relative w-full overflow-hidden border-border/70 bg-card/80 shadow-[0_28px_70px_-34px_rgba(16,185,129,0.55)] backdrop-blur-xl">
      {/* A hairline of the same emerald the backdrop is lit by, so the card
          reads as part of the scene rather than a box dropped on top of it. */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-emerald-400/70 to-transparent"
      />
      <CardHeader>
        <CardTitle className="text-xl">
          {/* The landing hero's mask reveal, scaled to a title. */}
          <span className="auth-mask">
            <span style={{ animationDelay: "260ms" }}>Sign in to DeFiScope</span>
          </span>
        </CardTitle>
        <CardDescription>
          Access is per-account. Your role and data scope are decided by the API,
          not by this page.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            void signIn(email, password);
          }}
        >
          <div
            className="auth-rise space-y-1.5"
            style={{ animationDelay: "320ms" }}
          >
            <label htmlFor="email" className="text-xs font-medium text-muted-foreground">
              Email
            </label>
            <Input
              ref={emailRef}
              id="email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="analyst@demo"
              required
            />
          </div>
          <div
            className="auth-rise space-y-1.5"
            style={{ animationDelay: "380ms" }}
          >
            <label htmlFor="password" className="text-xs font-medium text-muted-foreground">
              Password
            </label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          {error && (
            <p
              // Re-keyed on the message so a second rejection shakes again
              // instead of silently re-using the settled element.
              key={error}
              className="auth-error rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-700 dark:text-red-300"
              role="alert"
            >
              {error}
            </p>
          )}
          <div
            className="auth-rise flex items-stretch gap-2"
            style={{ animationDelay: "440ms" }}
          >
            <Button type="submit" className="h-9 flex-1" disabled={busy}>
              {busy ? <Loader2 className="size-4 animate-spin" /> : <LogIn className="size-4" />}
              {busy ? "Signing in…" : "Sign in"}
            </Button>
            <Button
              type="button"
              variant="outline"
              className="h-9 shrink-0"
              onClick={reset}
              disabled={busy || !dirty}
              title="Clear the email and password fields"
            >
              <RotateCcw className="size-4" />
              Reset
            </Button>
          </div>
        </form>

        {demo && (
          <div
            className="auth-rise space-y-2 border-t pt-4"
            style={{ animationDelay: "520ms" }}
          >
            <p className="text-xs text-muted-foreground">
              Demo accounts. Each changes exactly one axis, so you can watch the
              policy layer decide.
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {DEMO_ACCOUNTS.map((acct) => (
                <Button
                  key={acct.email}
                  type="button"
                  variant="outline"
                  className="h-auto flex-col items-start gap-0.5 px-3 py-2 text-left"
                  disabled={busy}
                  onClick={() => void signIn(acct.email, demoPassword)}
                >
                  <span className="text-sm font-medium">{acct.label}</span>
                  <span className="text-[11px] font-normal text-muted-foreground">
                    {acct.hint}
                  </span>
                </Button>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
