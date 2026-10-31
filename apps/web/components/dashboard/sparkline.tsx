"use client";

import { Line, LineChart, ResponsiveContainer, YAxis } from "recharts";

import type { TvlPoint } from "@/lib/types";

export default function Sparkline({
  data,
  tone = "flat",
}: {
  data: TvlPoint[];
  tone?: "up" | "down" | "flat";
}) {
  const color =
    tone === "down"
      ? "var(--color-red-500)"
      : tone === "up"
        ? "var(--color-emerald-500)"
        : "var(--color-zinc-500)";

  if (!data || data.length < 2) {
    return <div className="h-8 w-24 text-xs text-muted-foreground">n/a</div>;
  }

  return (
    <div className="h-8 w-24">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 2, bottom: 2, left: 0, right: 0 }}>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Line
            type="monotone"
            dataKey="tvl"
            stroke={color}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
