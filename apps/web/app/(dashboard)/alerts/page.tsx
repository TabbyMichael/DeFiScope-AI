import Link from "next/link";
import { Suspense } from "react";
import { Bell } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { Alert } from "@/lib/types";

const SEVERITY_STYLE: Record<string, string> = {
  critical: "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300",
  warning: "border-yellow-500/40 bg-yellow-500/10 text-yellow-800 dark:text-yellow-300",
  info: "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300",
};

async function AlertsContent() {
  let current: Alert[] = [];
  let history: Alert[] = [];
  let error: string | null = null;
  try {
    [current, history] = await Promise.all([api.alerts(), api.alertHistory()]);
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-700/80 sm:p-6 dark:text-red-200/80">
        API unavailable — start the backend to view monitoring results. ({error})
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Bell className="size-5" /> Monitoring
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Rules run every 30 minutes against DefiLlama data. Every alert shows the
          metric, observed value and threshold that triggered it.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Active alerts ({current.length})</CardTitle>
          <CardDescription>
            Evaluated on the current data window.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {current.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No rules triggered on the current data window. Quiet ≠ safe: rules
              only fire on TVL-observable signals.
            </p>
          ) : (
            current.map((a) => <AlertRow key={a.id} alert={a} />)
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Trigger history ({history.length})</CardTitle>
          <CardDescription>
            Persisted from the alert log; accumulates as the scheduler runs.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {history.length === 0 ? (
            <p className="text-sm text-muted-foreground">No persisted triggers yet.</p>
          ) : (
            history.map((a) => <AlertRow key={a.id} alert={a} />)
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function AlertsFallback() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-4 w-full max-w-2xl" />
      </div>
      <Skeleton className="h-40" />
      <Skeleton className="h-40" />
    </div>
  );
}

export default function AlertsPage() {
  return (
    <Suspense fallback={<AlertsFallback />}>
      <AlertsContent />
    </Suspense>
  );
}

function AlertRow({ alert }: { alert: Alert }) {
  const style = SEVERITY_STYLE[alert.severity] ?? SEVERITY_STYLE.info;
  return (
    <div className={`rounded-lg border p-3 text-sm ${style}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">
          <Link href={`/protocols/${alert.slug}`} className="underline-offset-2 hover:underline">
            {alert.protocol}
          </Link>{" "}
          · <Badge variant="outline" className="text-[10px] uppercase">{alert.rule}</Badge>
        </span>
        <span className="text-xs opacity-70">
          {new Date(alert.triggered_at).toISOString().slice(0, 16)}Z
        </span>
      </div>
      <p className="mt-1 text-xs leading-relaxed opacity-90">{alert.message}</p>
      <p className="mt-1.5 font-mono text-[10px] opacity-70">
        {Object.entries(alert.evidence)
          .map(([k, v]) => `${k}=${typeof v === "number" ? v.toLocaleString() : v}`)
          .join("  ")}
      </p>
    </div>
  );
}
