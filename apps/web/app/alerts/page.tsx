import Link from "next/link";

import { api } from "@/lib/api";
import type { Alert } from "@/lib/types";

const SEVERITY_STYLE: Record<string, string> = {
  critical: "border-red-500/40 bg-red-500/10 text-red-300",
  warning: "border-yellow-500/40 bg-yellow-500/10 text-yellow-300",
  info: "border-sky-500/40 bg-sky-500/10 text-sky-300",
};

export default async function AlertsPage() {
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
      <div className="rounded-lg border border-red-900/50 bg-red-950/30 p-6 text-sm text-red-200/80">
        API unavailable — start the backend to view monitoring results. ({error})
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Monitoring</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Rules run every 30 minutes against DefiLlama data. Every alert shows the
          metric, observed value and threshold that triggered it.
        </p>
      </header>

      <section>
        <h2 className="mb-3 text-sm font-medium text-zinc-300">
          Active alerts ({current.length})
        </h2>
        {current.length === 0 ? (
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 text-sm text-zinc-500">
            No rules triggered on the current data window. Quiet ≠ safe: rules only
            fire on TVL-observable signals.
          </div>
        ) : (
          <div className="space-y-2">
            {current.map((a) => (
              <AlertRow key={a.id} alert={a} />
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium text-zinc-300">
          Trigger history ({history.length})
        </h2>
        {history.length === 0 ? (
          <p className="text-sm text-zinc-600">
            No persisted triggers yet — history accumulates as the scheduler runs.
          </p>
        ) : (
          <div className="space-y-2">
            {history.map((a) => (
              <AlertRow key={a.id} alert={a} />
            ))}
          </div>
        )}
      </section>
    </div>
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
          · {alert.rule}
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
