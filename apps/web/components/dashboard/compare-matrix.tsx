import Link from "next/link";
import type { ReactNode } from "react";

import RiskBadge from "@/components/RiskBadge";
import Sparkline from "@/components/dashboard/sparkline";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { fmtPct, fmtUsd } from "@/lib/api-config";
import { bestIndexOf, type CompareItem } from "@/lib/compare";
import { cn } from "@/lib/utils";

/** Format a 0..1 fraction as a percent string; null reads n/a. */
function fmtFraction(v: number | null | undefined, digits = 1): string {
  if (v == null) return "n/a";
  return `${(v * 100).toFixed(digits)}%`;
}

function toneFor(value: number | null | undefined): "up" | "down" | "flat" {
  if (value == null || value === 0) return "flat";
  return value > 0 ? "up" : "down";
}

/**
 * A single metric row. Values are rendered per column; the best index (from
 * `bestIndexOf`) gets a subtle accent background. `null` values render as n/a
 * and are never silently zeroed, preserving honesty about missing data.
 */
function MetricRow({
  label,
  hint,
  items,
  best,
  render,
}: {
  label: string;
  hint?: string;
  items: CompareItem[];
  best?: number | null;
  render: (item: CompareItem, index: number) => ReactNode;
}) {
  return (
    <tr>
      <th
        scope="row"
        className="sticky left-0 z-10 border-r bg-card px-3 py-2.5 text-left align-middle text-sm font-medium text-muted-foreground"
      >
        <span className="block text-foreground">{label}</span>
        {hint && <span className="block text-[11px] font-normal">{hint}</span>}
      </th>
      {items.map((item, i) => (
        <td
          key={item.slug}
          className={cn(
            "border-r px-3 py-2.5 align-middle text-sm last:border-r-0",
            best === i && "bg-emerald-500/10",
          )}
        >
          {render(item, i)}
        </td>
      ))}
    </tr>
  );
}

export default function CompareMatrix({ items }: { items: CompareItem[] }) {
  const o = (item: CompareItem) => item.data?.overview ?? null;

  // Numeric columns we can rank. A null in any slot means "not comparable".
  const tvlIdx = bestIndexOf(items.map((it) => o(it)?.tvl ?? null), "max");
  const change7Idx = bestIndexOf(items.map((it) => o(it)?.change_7d ?? null), "max");
  const change30Idx = bestIndexOf(items.map((it) => o(it)?.change_30d ?? null), "max");
  const riskIdx = bestIndexOf(items.map((it) => o(it)?.risk_score ?? null), "min");
  const volIdx = bestIndexOf(items.map((it) => o(it)?.volatility_30d ?? null), "min");
  const concIdx = bestIndexOf(items.map((it) => o(it)?.top_chain_share ?? null), "min");
  const staleIdx = bestIndexOf(items.map((it) => o(it)?.stale_days ?? null), "min");
  const feesTvlIdx = bestIndexOf(items.map((it) => o(it)?.fees_tvl ?? null), "max");
  const depegIdx = bestIndexOf(items.map((it) => o(it)?.depeg_worst_bps ?? null), "min");

  const anyUnavailable = items.some((it) => !it.data);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardDescription>
            The best value in each row is tinted green (highest TVL/change, lowest
            risk, volatility, concentration and staleness). An n/a means the
            metric was not available, never assumed safe.
          </CardDescription>
          <CardTitle>Side-by-side metrics</CardTitle>
        </CardHeader>
        <CardContent className="px-0">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr>
                  <th
                    scope="col"
                    className="sticky left-0 z-20 border-r bg-card px-3 py-3 text-left align-bottom"
                  >
                    <span className="text-xs font-normal text-muted-foreground">
                      Metric
                    </span>
                  </th>
                  {items.map((item) => (
                    <th
                      key={item.slug}
                      scope="col"
                      className="min-w-[10rem] border-r px-3 py-3 text-left align-bottom last:border-r-0"
                    >
                      {item.data ? (
                        <Link
                          href={`/protocols/${item.slug}`}
                          className="font-semibold text-foreground underline-offset-2 hover:underline"
                        >
                          {item.data.name}
                        </Link>
                      ) : (
                        <span className="font-semibold text-muted-foreground">
                          Unavailable
                        </span>
                      )}
                      <span className="mt-0.5 block truncate text-[11px] font-normal text-muted-foreground">
                        {item.slug}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y">
                <MetricRow
                  label="Category"
                  items={items}
                  render={(it) => o(it)?.category ?? "n/a"}
                />
                <MetricRow
                  label="TVL"
                  items={items}
                  best={tvlIdx}
                  render={(it) => (
                    <span className="font-medium tabular-nums">
                      {fmtUsd(o(it)?.tvl)}
                    </span>
                  )}
                />
                <MetricRow
                  label="7d change"
                  items={items}
                  best={change7Idx}
                  render={(it) => (
                    <span
                      className={cn(
                        "tabular-nums",
                        (o(it)?.change_7d ?? 0) > 0 && "text-emerald-600 dark:text-emerald-400",
                        (o(it)?.change_7d ?? 0) < 0 && "text-red-600 dark:text-red-400",
                      )}
                    >
                      {fmtPct(o(it)?.change_7d)}
                    </span>
                  )}
                />
                <MetricRow
                  label="30d change"
                  items={items}
                  best={change30Idx}
                  render={(it) => (
                    <span
                      className={cn(
                        "tabular-nums",
                        (o(it)?.change_30d ?? 0) > 0 && "text-emerald-600 dark:text-emerald-400",
                        (o(it)?.change_30d ?? 0) < 0 && "text-red-600 dark:text-red-400",
                      )}
                    >
                      {fmtPct(o(it)?.change_30d)}
                    </span>
                  )}
                />
                <MetricRow
                  label="Volatility (30d)"
                  hint="lower is steadier"
                  items={items}
                  best={volIdx}
                  render={(it) => (
                    <span className="tabular-nums">
                      {fmtFraction(o(it)?.volatility_30d)}
                    </span>
                  )}
                />
                <MetricRow
                  label="Top chain"
                  items={items}
                  render={(it) => {
                    const ov = o(it);
                    if (!ov?.top_chain) return "n/a";
                    return (
                      <span>
                        {ov.top_chain}{" "}
                        <span className="text-xs text-muted-foreground">
                          ({fmtFraction(ov.top_chain_share)})
                        </span>
                      </span>
                    );
                  }}
                />
                <MetricRow
                  label="Chain concentration"
                  hint="lower share = more diversified"
                  items={items}
                  best={concIdx}
                  render={(it) => (
                    <span className="tabular-nums">
                      {fmtFraction(o(it)?.top_chain_share)}
                    </span>
                  )}
                />
                <MetricRow
                  label="Incentive ratio"
                  hint="TVL vs. emissions"
                  items={items}
                  render={(it) => (
                    <span className="tabular-nums">
                      {o(it)?.incentive_ratio != null
                        ? o(it)!.incentive_ratio!.toFixed(2)
                        : "n/a"}
                    </span>
                  )}
                />
                <MetricRow
                  label="Fees (24h)"
                  items={items}
                  render={(it) => (
                    <span className="tabular-nums">{fmtUsd(o(it)?.fees_1d)}</span>
                  )}
                />
                <MetricRow
                  label="Revenue (24h)"
                  items={items}
                  render={(it) => (
                    <span className="tabular-nums">{fmtUsd(o(it)?.revenue_1d)}</span>
                  )}
                />
                <MetricRow
                  label="Volume (24h)"
                  items={items}
                  render={(it) => (
                    <span className="tabular-nums">{fmtUsd(o(it)?.volume_1d)}</span>
                  )}
                />
                <MetricRow
                  label="Fees / TVL (30d)"
                  hint="higher = more real yield"
                  items={items}
                  best={feesTvlIdx}
                  render={(it) => (
                    <span className="tabular-nums">
                      {fmtFraction(o(it)?.fees_tvl, 2)}
                    </span>
                  )}
                />
                <MetricRow
                  label="Peg deviation (30d)"
                  hint="lower = closer to peg; n/a = no tracked stablecoin"
                  items={items}
                  best={depegIdx}
                  render={(it) => {
                    const v = o(it)?.depeg_worst_bps;
                    if (v == null) return "n/a";
                    const asset = o(it)?.depeg_asset;
                    return (
                      <span className="tabular-nums">
                        {v.toFixed(0)} bps
                        {asset && (
                          <span className="text-xs text-muted-foreground">
                            {" "}
                            · {asset}
                          </span>
                        )}
                      </span>
                    );
                  }}
                />
                <MetricRow
                  label="Risk score"
                  hint="lower is safer"
                  items={items}
                  best={riskIdx}
                  render={(it) => {
                    const ov = o(it);
                    if (!ov) return "n/a";
                    return (
                      <RiskBadge score={ov.risk_score} band={ov.risk_band} />
                    );
                  }}
                />
                <MetricRow
                  label="Data freshness"
                  hint="days since last observation"
                  items={items}
                  best={staleIdx}
                  render={(it) => {
                    const days = o(it)?.stale_days;
                    if (days == null) return "n/a";
                    return (
                      <span
                        className={cn(
                          "tabular-nums",
                          days > 1 && "text-yellow-700 dark:text-yellow-400",
                        )}
                      >
                        {days}d
                      </span>
                    );
                  }}
                />
                <MetricRow
                  label="TVL trend (30d)"
                  items={items}
                  render={(it) =>
                    it.data ? (
                      <Sparkline
                        data={it.data.tvl_series ?? []}
                        tone={toneFor(o(it)?.change_30d)}
                      />
                    ) : (
                      "n/a"
                    )
                  }
                />
                <MetricRow
                  label="As of"
                  items={items}
                  render={(it) => (
                    <span className="text-xs text-muted-foreground">
                      {it.data?.as_of ?? "n/a"}
                    </span>
                  )}
                />
              </tbody>
            </table>
          </div>
          {anyUnavailable && (
            <p className="mt-3 px-3 text-xs text-muted-foreground">
              An “Unavailable” column means that protocol could not be loaded (bad
              slug or API temporarily down). Remove it and pick another.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Explainable risk breakdown, the honesty DNA, per protocol. */}
      <div className="grid gap-4 lg:grid-cols-2">
        {items
          .filter((it) => it.data)
          .map((it) => (
            <RiskDetail key={it.slug} item={it} />
          ))}
      </div>
    </div>
  );
}

function RiskDetail({ item }: { item: CompareItem }) {
  const risk = item.data?.risk;
  const gaps = item.data?.data_gaps ?? [];
  const indicators = risk?.indicators ?? [];

  return (
    <Card>
      <CardHeader className="flex-row items-center gap-3 space-y-0">
        <div className="min-w-0">
          <CardTitle className="truncate">
            <Link
              href={`/protocols/${item.slug}`}
              className="underline-offset-2 hover:underline"
            >
              {item.data?.name}
            </Link>
          </CardTitle>
          <CardDescription>Explainable risk indicators</CardDescription>
        </div>
        <div className="ml-auto shrink-0">
          <RiskBadge score={risk?.composite_score ?? null} band={risk?.band ?? "unknown"} />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {indicators.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No risk indicators computed for this protocol.
          </p>
        ) : (
          <ul className="space-y-2">
            {indicators.map((ind) => (
              <li key={ind.key} className="rounded-lg border bg-muted/30 p-2.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{ind.label}</span>
                  <span className="text-xs tabular-nums text-muted-foreground">
                    score {ind.score == null ? "n/a" : ind.score.toFixed(0)} · weight{" "}
                    {(ind.weight * 100).toFixed(0)}%
                  </span>
                </div>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  {ind.evidence}
                </p>
                {ind.limitation && (
                  <p className="mt-1 text-xs italic leading-relaxed text-muted-foreground/80">
                    Limitation: {ind.limitation}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
        {gaps.length > 0 && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {gaps.map((g) => (
              <Badge
                key={g}
                variant="outline"
                className="border-yellow-500/40 bg-yellow-500/10 text-yellow-800 dark:text-yellow-300"
              >
                gap: {g}
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
