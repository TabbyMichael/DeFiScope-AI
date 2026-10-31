import Link from "next/link";
import { Bell, TrendingDown, TrendingUp, Wallet } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { fmtPct, fmtUsd } from "@/lib/api-config";
import type { DashboardStats } from "@/lib/types";

const BAND_ORDER = ["low", "moderate", "elevated", "high", "unknown"] as const;
const BAND_COLOR: Record<string, string> = {
  low: "bg-emerald-500",
  moderate: "bg-yellow-500",
  elevated: "bg-orange-500",
  high: "bg-red-500",
  unknown: "bg-zinc-500",
};

// Shared affordance for the two whole-card links (Total TVL, Active alerts):
// lift the card on hover so it reads as clickable without a nested-link problem.
const CARD_HOVER =
  "h-full transition-[box-shadow,border-color] group-hover:border-emerald-500/40 group-hover:shadow-md";
const HINT =
  "text-xs text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100";

export default function StatCards({ stats }: { stats: DashboardStats }) {
  const movers = [stats.top_gainer, stats.top_loser].filter(Boolean).length;

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Link
        href="#protocols"
        className="group block h-full"
        aria-label="View the protocol board"
      >
        <Card className={CARD_HOVER}>
          <CardHeader>
            <CardDescription className="flex items-center gap-1.5">
              <Wallet className="size-3.5" /> Total TVL
            </CardDescription>
            <CardTitle className="text-2xl tabular-nums">
              {fmtUsd(stats.total_tvl)}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex items-center justify-between text-xs text-muted-foreground">
            <span>across {stats.protocol_count} tracked protocols</span>
            <span className={HINT}>View board →</span>
          </CardContent>
        </Card>
      </Link>

      <Link href="/alerts" className="group block h-full" aria-label="View alerts">
        <Card className={CARD_HOVER}>
          <CardHeader>
            <CardDescription className="flex items-center gap-1.5">
              <Bell className="size-3.5" /> Active alerts
            </CardDescription>
            <CardTitle className="text-2xl tabular-nums">
              {stats.active_critical + stats.active_warning}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex items-center justify-between text-xs">
            <span className="flex gap-3">
              <span className="text-red-600 dark:text-red-400">
                {stats.active_critical} critical
              </span>
              <span className="text-yellow-700 dark:text-yellow-400">
                {stats.active_warning} warning
              </span>
            </span>
            <span className={HINT}>Open alerts →</span>
          </CardContent>
        </Card>
      </Link>

      <Card className="h-full">
        <CardHeader>
          <CardDescription>Risk band distribution</CardDescription>
          <CardTitle className="text-sm font-normal">by composite score</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-x-2 gap-y-1 text-xs">
          {BAND_ORDER.filter((b) => (stats.by_band[b] ?? 0) > 0).map((b) => (
            <Link
              key={b}
              href={`/?band=${b}#protocols`}
              title={`Filter the board by ${b} risk`}
              className="inline-flex items-center gap-1.5 rounded-full border border-transparent px-1.5 py-0.5 transition-colors hover:border-border hover:bg-accent"
            >
              <span className={`size-2 rounded-full ${BAND_COLOR[b]}`} />
              {b}{" "}
              <span className="tabular-nums text-muted-foreground">
                {stats.by_band[b]}
              </span>
            </Link>
          ))}
          {stats.protocol_count === 0 && (
            <span className="text-muted-foreground">no data yet</span>
          )}
        </CardContent>
      </Card>

      <Card className="h-full">
        <CardHeader>
          <CardDescription>Top 7d movers</CardDescription>
          <CardTitle className="text-sm font-normal">TVL change, 7d</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-xs">
          {movers === 0 && <span className="text-muted-foreground">n/a</span>}
          {stats.top_gainer && (
            <Link
              href={`/protocols/${stats.top_gainer.slug}`}
              className="flex items-center justify-between rounded-md px-1.5 py-1 transition-colors hover:bg-accent"
            >
              <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                <TrendingUp className="size-3.5" /> {stats.top_gainer.name}
              </span>
              <span className="tabular-nums">
                {fmtPct(stats.top_gainer.change_7d)}
              </span>
            </Link>
          )}
          {stats.top_loser && (
            <Link
              href={`/protocols/${stats.top_loser.slug}`}
              className="flex items-center justify-between rounded-md px-1.5 py-1 transition-colors hover:bg-accent"
            >
              <span className="inline-flex items-center gap-1 text-red-600 dark:text-red-400">
                <TrendingDown className="size-3.5" /> {stats.top_loser.name}
              </span>
              <span className="tabular-nums">
                {fmtPct(stats.top_loser.change_7d)}
              </span>
            </Link>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
