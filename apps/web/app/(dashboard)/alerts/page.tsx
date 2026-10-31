import { Suspense } from "react";
import { Bell, Inbox } from "lucide-react";

import AlertItem, { severityStyle } from "@/components/dashboard/alert-item";
import WithheldBanner from "@/components/dashboard/withheld-banner";
import RunCheck from "@/components/run-check";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import type { Alert } from "@/lib/types";

const SEVERITY_ORDER = ["critical", "warning", "info"] as const;

function AlertEmptyState({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-10 text-center">
      <Inbox className="size-6 text-muted-foreground" />
      <p className="text-sm font-medium text-foreground">{title}</p>
      <p className="max-w-sm text-xs leading-relaxed text-muted-foreground">{hint}</p>
    </div>
  );
}

function SeverityChip({ severity, count }: { severity: string; count: number }) {
  const s = severityStyle(severity);
  return (
    <div className="flex items-center gap-3 rounded-lg border bg-card p-3">
      <span className={`flex size-9 shrink-0 items-center justify-center rounded-full bg-muted ${s.icon}`}>
        <s.Icon className="size-4.5" />
      </span>
      <div className="min-w-0">
        <div className="text-xl leading-none font-semibold tabular-nums">{count}</div>
        <div className="mt-1 truncate text-xs text-muted-foreground">{s.label}</div>
      </div>
    </div>
  );
}

async function AlertsContent() {
  let current: Alert[] = [];
  let history: Alert[] = [];
  let withheld = 0;
  let historyWithheld = 0;
  let error: string | null = null;
  let denial: ApiError | null = null;
  try {
    const [today, past] = await Promise.all([api.alerts(), api.alertHistory()]);
    current = today.alerts;
    withheld = today.withheld;
    history = past.alerts;
    historyWithheld = past.withheld;
  } catch (e) {
    // A 403 here is an authorization verdict, not an outage — say so plainly
    // instead of blaming the backend for being down.
    if (e instanceof ApiError && e.isDenial) denial = e;
    else error = e instanceof Error ? e.message : String(e);
  }

  if (denial) {
    return (
      <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm sm:p-6">
        <h2 className="mb-1 flex items-center gap-2 font-semibold text-amber-800 dark:text-amber-200">
          <Inbox className="size-4" /> {denial.reason}
        </h2>
        {denial.policy && (
          <p className="text-xs text-amber-700/80 dark:text-amber-300/80">
            policy: <code className="font-mono">{denial.policy}</code>
            {denial.permission && ` · needs ${denial.permission}`}
          </p>
        )}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm sm:p-6">
        <h2 className="mb-1 flex items-center gap-2 font-semibold text-red-600 dark:text-red-300">
          <Inbox className="size-4" /> API unavailable
        </h2>
        <p className="text-red-700/80 dark:text-red-200/80">
          Start the backend to view monitoring results. ({error})
        </p>
      </div>
    );
  }

  const counts = {
    critical: current.filter((a) => a.severity === "critical").length,
    warning: current.filter((a) => a.severity === "warning").length,
    info: current.filter((a) => a.severity !== "critical" && a.severity !== "warning").length,
  };

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-3">
        {SEVERITY_ORDER.map((sev) => (
          <SeverityChip key={sev} severity={sev} count={counts[sev]} />
        ))}
      </div>

      <Card>
        <CardHeader className="flex-row items-center gap-3 space-y-0">
          <div className="min-w-0">
            <CardTitle>Active alerts ({current.length})</CardTitle>
            <CardDescription>Evaluated on the current data window.</CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          <WithheldBanner withheld={withheld} />
          {current.length === 0 ? (
            <AlertEmptyState
              title={withheld > 0 ? "Nothing you are cleared to read" : "No rules triggered"}
              hint={
                withheld > 0
                  ? "Alerts did fire, but all of them are above your clearance. Ask a risk officer to review them."
                  : "Quiet ≠ safe: rules only fire on TVL-observable signals. Open a protocol to review its full risk evidence."
              }
            />
          ) : (
            current.map((a) => <AlertItem key={a.id} alert={a} />)
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
          <WithheldBanner withheld={historyWithheld} />
          {history.length === 0 ? (
            <AlertEmptyState
              title="No persisted triggers yet"
              hint="Historical alerts appear here after each monitoring pass. Use Run check to trigger one now."
            />
          ) : (
            history.map((a) => <AlertItem key={a.id} alert={a} />)
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function AlertsFallback() {
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-3">
        <Skeleton className="h-16" />
        <Skeleton className="h-16" />
        <Skeleton className="h-16" />
      </div>
      <Skeleton className="h-40" />
      <Skeleton className="h-40" />
    </div>
  );
}

export default function AlertsPage() {
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <Bell className="size-5" /> Monitoring
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Rules run every 30 minutes against DefiLlama data. Every alert shows the
            metric, observed value and threshold that triggered it.
          </p>
        </div>
        <RunCheck />
      </header>
      <Suspense fallback={<AlertsFallback />}>
        <AlertsContent />
      </Suspense>
    </div>
  );
}
