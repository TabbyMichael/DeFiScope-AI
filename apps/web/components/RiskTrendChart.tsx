"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { RiskPoint } from "@/lib/types";

// Composite-score band boundaries (see scoring.assess): low <30, moderate <50,
// elevated <70, high >=70. Drawn as reference lines so the trend reads against
// the same thresholds the badge uses.
const BANDS = [
  { at: 30, label: "moderate" },
  { at: 50, label: "elevated" },
  { at: 70, label: "high" },
];

export default function RiskTrendChart({
  data,
  height = 200,
}: {
  data: RiskPoint[];
  height?: number;
}) {
  if (data.length < 2) {
    return (
      <div className="flex h-[200px] flex-col items-center justify-center gap-1 rounded-lg border border-dashed text-center">
        <p className="text-sm font-medium text-foreground">
          Not enough scored history yet
        </p>
        <p className="max-w-sm text-xs leading-relaxed text-muted-foreground">
          The risk-score trend appears after the scheduler has captured at least
          two daily snapshots. Only scored days are plotted — the initial
          DefiLlama backfill carries TVL but no score, so it is not faked here.
        </p>
      </div>
    );
  }

  const chartData = data.map((p) => ({
    ...p,
    score: p.score ?? 0,
    label: p.date.slice(5), // MM-DD
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
          tickLine={false}
          axisLine={{ stroke: "var(--border)" }}
          minTickGap={40}
        />
        <YAxis
          domain={[0, 100]}
          ticks={[0, 25, 50, 75, 100]}
          tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          width={32}
        />
        {BANDS.map((b) => (
          <ReferenceLine
            key={b.at}
            y={b.at}
            stroke="var(--border)"
            strokeDasharray="2 4"
            label={{
              value: b.label,
              position: "insideTopRight",
              fill: "var(--muted-foreground)",
              fontSize: 9,
            }}
          />
        ))}
        <Tooltip
          cursor={{ stroke: "var(--muted-foreground)", strokeOpacity: 0.2 }}
          contentStyle={{
            backgroundColor: "var(--popover)",
            color: "var(--popover-foreground)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
            fontSize: 12,
          }}
          labelStyle={{ color: "var(--muted-foreground)", marginBottom: 2 }}
          formatter={(value, _name, item) => {
            const band = (item?.payload as RiskPoint | undefined)?.band ?? "—";
            return [`${Number(value).toFixed(0)} · ${band}`, "Risk score"];
          }}
        />
        <Line
          type="monotone"
          dataKey="score"
          stroke="var(--color-orange-500)"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
