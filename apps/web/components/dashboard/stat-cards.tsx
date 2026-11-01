"use client";

import { useMemo } from "react";
import Link from "next/link";
import { Bell, TrendingDown, TrendingUp, Wallet } from "lucide-react";

import AnimatedNumber from "@/components/dashboard/animated-number";
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
// Meter gradients for the distribution bar, in lockstep with <RiskBadge> tones
// and the watchlist board's row meters.
const BAND_GRADIENT: Record<string, string> = {
  low: "from-emerald-400 to-emerald-500",
  moderate: "from-yellow-400 to-yellow-500",
  elevated: "from-orange-400 to-orange-500",
  high: "from-red-400 to-red-500",
  unknown: "from-zinc-300 to-zinc-400 dark:from-zinc-600 dark:to-zinc-500",
};

// Shared affordance for the two whole-card links (Total TVL, Active alerts):
// lift the card on hover so it reads as clickable without a nested-link problem.
const CARD_HOVER =
  "h-full transition-[box-shadow,border-color] group-hover:border-emerald-500/40 group-hover:shadow-md";
const HINT =
  "text-xs text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100";
// Entrance stagger: each card fades up a beat after the previous one.
const CARD_ENTER = "animate-in fade-in slide-in-from-bottom-3 fill-backward";
const cardDelay = (i: number) => ({ animationDelay: `${i * 90}ms` });

export default function StatCards({ stats }: { stats: DashboardStats }) {
  const movers = [stats.top_gainer, stats.top_loser].filter(Boolean).length;

  // Bands actually observed (low -> unknown). The stacked bar and the chips
  // render from this one list, so the two views can never disagree.
  const bands = useMemo(
    () =>
      BAND_ORDER.map((b) => ({ band: b, count: stats.by_band[b] ?? 0 })).filter(
        (x) => x.count > 0,
      ),
    [stats.by_band],
  );
  const bandTotal = bands.reduce((s, x) => s + x.count, 0);

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Link
        href="/watchlist"
        className="group block h-full"
        aria-label="Open the risk watchlist"
        style={cardDelay(0)}
      >
        <Card className={`${CARD_HOVER} ${CARD_ENTER}`}>
          <CardHeader>
            <CardDescription className="flex items-center gap-1.5">
              <Wallet className="size-3.5" /> Total TVL
            </CardDescription>
            <CardTitle className="text-2xl tabular-nums">
              <AnimatedNumber value={stats.total_tvl} format={fmtUsd} />
            </CardTitle>
          </CardHeader>
          <CardContent className="flex items-center justify-between text-xs text-muted-foreground">
            <span>
              across{" "}
              <AnimatedNumber value={stats.protocol_count} className="text-foreground" />
              {" "}tracked protocols
            </span>
            <span className={HINT}>Open watchlist →</span>
          </CardContent>
        </Card>
      </Link>

      <Link
        href="/alerts"
        className="group block h-full"
        aria-label="View alerts"
        style={cardDelay(1)}
      >
        <Card className={`${CARD_HOVER} ${CARD_ENTER}`}>
          <CardHeader>
            <CardDescription className="flex items-center gap-1.5">
              <Bell className="size-3.5" /> Active alerts
            </CardDescription>
            <CardTitle className="text-2xl tabular-nums">
              <AnimatedNumber value={stats.active_critical + stats.active_warning} />
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

      <Card className={`h-full ${CARD_ENTER}`} style={cardDelay(2)}>
        <CardHeader>
          <CardDescription className="flex items-center justify-between gap-2">
            <span>Risk band distribution</span>
            <Link
              href="/watchlist"
              className="font-normal text-muted-foreground underline-offset-2 hover:text-emerald-600 hover:underline dark:hover:text-emerald-400"
            >
              Watchlist →
            </Link>
          </CardDescription>
          <CardTitle className="text-sm font-normal">by composite score</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2.5">
          {bandTotal > 0 && (
            <div
              className="flex h-2 w-full overflow-hidden rounded-full bg-muted"
              role="img"
              aria-label={`Risk bands across ${bandTotal} tracked protocols`}
            >
              {bands.map(({ band, count }) => (
                <div
                  key={band}
                  className={`wl-meter h-full bg-gradient-to-r ${BAND_GRADIENT[band]}`}
                  style={{ width: `${(count / bandTotal) * 100}%` }}
                  title={`${band}: ${count}`}
                />
              ))}
            </div>
          )}
          <div className="flex flex-wrap gap-x-2 gap-y-1 text-xs">
            {bands.map(({ band, count }) => (
              <Link
                key={band}
                href={`/?band=${band}#protocols`}
                title={`Filter the board by ${band} risk`}
                className="inline-flex items-center gap-1.5 rounded-full border border-transparent px-1.5 py-0.5 transition-colors hover:border-border hover:bg-accent"
              >
                <span className={`size-2 rounded-full ${BAND_COLOR[band]}`} />
                {band}{" "}
                <span className="tabular-nums text-muted-foreground">{count}</span>
              </Link>
            ))}
            {bands.length === 0 && (
              <span className="text-muted-foreground">no data yet</span>
            )}
          </div>
        </CardContent>
      </Card>

      <Card className={`h-full ${CARD_ENTER}`} style={cardDelay(3)}>
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
