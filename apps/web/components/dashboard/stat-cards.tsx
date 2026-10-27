import { Bell, TrendingDown, TrendingUp, Wallet } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { fmtPct, fmtUsd } from "@/lib/api";
import type { DashboardStats } from "@/lib/types";

const BAND_ORDER = ["low", "moderate", "elevated", "high", "unknown"] as const;
const BAND_COLOR: Record<string, string> = {
  low: "bg-emerald-500",
  moderate: "bg-yellow-500",
  elevated: "bg-orange-500",
  high: "bg-red-500",
  unknown: "bg-zinc-500",
};

export default function StatCards({ stats }: { stats: DashboardStats }) {
  const movers = [stats.top_gainer, stats.top_loser].filter(Boolean).length;

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardHeader>
          <CardDescription className="flex items-center gap-1.5">
            <Wallet className="size-3.5" /> Total TVL
          </CardDescription>
          <CardTitle className="text-2xl tabular-nums">
            {fmtUsd(stats.total_tvl)}
          </CardTitle>
        </CardHeader>
        <CardContent className="text-xs text-muted-foreground">
          across {stats.protocol_count} tracked protocols
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardDescription className="flex items-center gap-1.5">
            <Bell className="size-3.5" /> Active alerts
          </CardDescription>
          <CardTitle className="text-2xl tabular-nums">
            {stats.active_critical + stats.active_warning}
          </CardTitle>
        </CardHeader>
        <CardContent className="flex gap-3 text-xs">
          <span className="text-red-600 dark:text-red-400">{stats.active_critical} critical</span>
          <span className="text-yellow-700 dark:text-yellow-400">{stats.active_warning} warning</span>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardDescription>Risk band distribution</CardDescription>
          <CardTitle className="text-sm font-normal">by composite score</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
          {BAND_ORDER.filter((b) => (stats.by_band[b] ?? 0) > 0).map((b) => (
            <span key={b} className="inline-flex items-center gap-1.5">
              <span className={`size-2 rounded-full ${BAND_COLOR[b]}`} />
              {b} <span className="tabular-nums text-muted-foreground">{stats.by_band[b]}</span>
            </span>
          ))}
          {stats.protocol_count === 0 && (
            <span className="text-muted-foreground">no data yet</span>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardDescription>Top 7d movers</CardDescription>
          <CardTitle className="text-sm font-normal">TVL change, 7d</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1.5 text-xs">
          {movers === 0 && <span className="text-muted-foreground">—</span>}
          {stats.top_gainer && (
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                <TrendingUp className="size-3.5" /> {stats.top_gainer.name}
              </span>
              <span className="tabular-nums">{fmtPct(stats.top_gainer.change_7d)}</span>
            </div>
          )}
          {stats.top_loser && (
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-1 text-red-600 dark:text-red-400">
                <TrendingDown className="size-3.5" /> {stats.top_loser.name}
              </span>
              <span className="tabular-nums">{fmtPct(stats.top_loser.change_7d)}</span>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
