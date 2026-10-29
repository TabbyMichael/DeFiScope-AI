import Link from "next/link";
import { AlertTriangle, ArrowRight, Clock, Info, ShieldAlert } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { Alert } from "@/lib/types";

/**
 * Shared presentational row for a single alert, used by both the dashboard
 * alert feed and the full Monitoring (alerts) page so severity styling lives in
 * one place. Server component: pure rendering, no client state.
 */

export type SeverityStyle = {
  /** left accent bar fill */
  bar: string;
  /** severity icon + its text color */
  icon: string;
  Icon: LucideIcon;
  /** human label */
  label: string;
};

const SEVERITY: Record<string, SeverityStyle> = {
  critical: {
    bar: "bg-red-500",
    icon: "text-red-600 dark:text-red-400",
    Icon: ShieldAlert,
    label: "Critical",
  },
  warning: {
    bar: "bg-yellow-500",
    icon: "text-yellow-600 dark:text-yellow-400",
    Icon: AlertTriangle,
    label: "Warning",
  },
  info: {
    bar: "bg-sky-500",
    icon: "text-sky-600 dark:text-sky-400",
    Icon: Info,
    label: "Info",
  },
};

const FALLBACK: SeverityStyle = SEVERITY.info;

export function severityStyle(severity: string): SeverityStyle {
  return SEVERITY[severity] ?? FALLBACK;
}

/** Compact "3m ago" style relative time; falls back to the raw string if unparseable. */
function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const mins = Math.max(0, Math.floor((Date.now() - then) / 60_000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

/** Turn the evidence object into readable [label, value] pairs. */
function evidencePairs(evidence: Record<string, unknown>): [string, string][] {
  return Object.entries(evidence).map(([key, value]) => [
    key.replace(/_/g, " "),
    typeof value === "number" ? value.toLocaleString() : String(value),
  ]);
}

export default function AlertItem({
  alert,
  showTime = true,
  showCta = true,
}: {
  alert: Alert;
  showTime?: boolean;
  showCta?: boolean;
}) {
  const s = severityStyle(alert.severity);
  const pairs = evidencePairs(alert.evidence ?? {});

  return (
    <div className="group relative overflow-hidden rounded-lg border bg-card py-3 pr-3 pl-4 text-sm shadow-sm transition-colors hover:bg-accent/40">
      <span aria-hidden className={`absolute top-0 left-0 h-full w-1.5 ${s.bar}`} />

      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <s.Icon className={`size-4 shrink-0 ${s.icon}`} />
          <Link
            href={`/protocols/${alert.slug}`}
            className="max-w-full truncate font-medium underline-offset-2 hover:underline"
          >
            {alert.protocol}
          </Link>
          <Badge variant="outline" className="text-[10px] uppercase">
            {alert.rule}
          </Badge>
        </div>

        {showTime && (
          <time
            dateTime={alert.triggered_at}
            title={alert.triggered_at}
            className="inline-flex shrink-0 items-center gap-1 text-xs text-muted-foreground"
          >
            <Clock className="size-3" />
            {formatRelative(alert.triggered_at)}
          </time>
        )}
      </div>

      <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{alert.message}</p>

      {pairs.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {pairs.map(([k, v]) => (
            <span
              key={k}
              className="inline-flex items-center gap-1 rounded-md bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
            >
              <span className="opacity-70">{k}</span>
              <span className="tabular-nums text-foreground">{v}</span>
            </span>
          ))}
        </div>
      )}

      {showCta && (
        <Link
          href={`/protocols/${alert.slug}`}
          className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-primary opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
        >
          View protocol <ArrowRight className="size-3" />
        </Link>
      )}
    </div>
  );
}
