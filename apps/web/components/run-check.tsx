"use client";

import { Loader2, Play, RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";

// How often the auto-refresh poll re-fetches the server-rendered alerts.
const AUTO_REFRESH_MS = 60_000;

export default function RunCheck() {
  const router = useRouter();
  const [running, setRunning] = useState(false);
  const [auto, setAuto] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  // A 403 from FastAPI here is the feature, not a bug: "the snapshot is fresh,
  // a crawl would be redundant" is an explanation we want to show verbatim.
  const [denied, setDenied] = useState(false);
  const [policy, setPolicy] = useState<string | null>(null);
  const inFlight = useRef(false);

  const runCheck = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setRunning(true);
    setMessage(null);
    setDenied(false);
    setPolicy(null);
    try {
      const res = await fetch("/api/run-check", { method: "POST" });
      const data = (await res.json()) as {
        ok: boolean;
        count?: number;
        error?: string;
        reason?: string;
        policy?: string;
      };
      if (!res.ok || !data.ok) {
        // Render the policy's own words. A generic "run failed" toast would
        // throw away the only useful part of the response.
        setDenied(res.status === 403 || res.status === 401);
        setPolicy(data.policy ?? null);
        setMessage(data.reason ?? data.error ?? "Run failed");
      } else {
        setMessage(`Check complete · ${data.count ?? 0} active alert(s)`);
        // Re-run the server component so the board reflects the fresh pass.
        router.refresh();
      }
    } catch (e) {
      setDenied(false);
      setMessage(e instanceof Error ? e.message : "Network error");
    } finally {
      setRunning(false);
      inFlight.current = false;
    }
  }, [router]);

  useEffect(() => {
    if (!auto) return;
    const id = setInterval(() => router.refresh(), AUTO_REFRESH_MS);
    return () => clearInterval(id);
  }, [auto, router]);

  return (
    <div className="flex flex-wrap items-center gap-2">
      {message && (
        <span
          role="status"
          className={
            denied
              ? "max-w-md rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-xs leading-relaxed text-amber-800 dark:text-amber-200"
              : "text-xs text-muted-foreground"
          }
        >
          {message}
          {denied && policy && (
            <code className="ml-1.5 font-mono text-[10px] opacity-70">{policy}</code>
          )}
        </span>
      )}
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={() => setAuto((v) => !v)}
        aria-pressed={auto}
        title="Poll for updates every 60s"
      >
        <RefreshCw className={`size-4 ${auto ? "animate-spin" : ""}`} />
        Auto-refresh {auto ? "on" : "off"}
      </Button>
      <Button type="button" size="sm" onClick={runCheck} disabled={running}>
        {running ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
        {running ? "Running…" : "Run check"}
      </Button>
    </div>
  );
}
