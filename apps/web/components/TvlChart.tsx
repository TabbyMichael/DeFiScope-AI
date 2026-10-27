"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { TvlPoint } from "@/lib/types";

function shortUsd(v: number): string {
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return `${v.toFixed(0)}`;
}

export default function TvlChart({
  data,
  height = 280,
}: {
  data: TvlPoint[];
  height?: number;
}) {
  const chartData = data.map((p) => ({
    ...p,
    label: p.date.slice(5), // MM-DD
  }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
        <defs>
          <linearGradient id="tvlFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-emerald-500)" stopOpacity={0.35} />
            <stop offset="100%" stopColor="var(--color-emerald-500)" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
          tickLine={false}
          axisLine={{ stroke: "var(--border)" }}
          minTickGap={40}
        />
        <YAxis
          tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          width={56}
          tickFormatter={(v: number) => shortUsd(v)}
        />
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
          formatter={(value) => [`$${shortUsd(Number(value))}`, "TVL"]}
        />
        <Area
          type="monotone"
          dataKey="tvl"
          stroke="var(--color-emerald-500)"
          strokeWidth={2}
          fill="url(#tvlFill)"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
