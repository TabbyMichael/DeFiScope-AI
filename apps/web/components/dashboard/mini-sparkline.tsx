import type { TvlPoint } from "@/lib/types";

/**
 * A tiny, dependency-free TVL sparkline drawn as an inline SVG polyline.
 *
 * Deliberately separate from the interactive recharts `<Sparkline>`: the
 * watchlist board renders one of these per protocol row, and a handful of SVG
 * paths is far cheaper than spinning up a charting instance per row. It is a
 * plain (server-renderable) component, so the board's first paint is complete.
 * A series with no usable points degrades to a faint dashed baseline rather than
 * vanishing - "tracked, no shape yet" - consistent with the honesty contract.
 */
export default function MiniSparkline({
  points,
  width = 84,
  height = 24,
  stroke = "currentColor",
  className,
}: {
  points: TvlPoint[];
  width?: number;
  height?: number;
  stroke?: string;
  className?: string;
}) {
  const values = points.map((p) => p.tvl).filter((v) => Number.isFinite(v));

  let d = "";
  if (values.length >= 2) {
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const step = width / (values.length - 1);
    d = values
      .map((v, i) => {
        const x = i * step;
        const y = height - ((v - min) / span) * (height - 4) - 2;
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      fill="none"
      className={className}
      aria-hidden="true"
      preserveAspectRatio="none"
    >
      {values.length >= 2 ? (
        <path
          d={d}
          stroke={stroke}
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ) : (
        <line
          x1={0}
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke={stroke}
          strokeWidth={1.5}
          strokeDasharray="2 3"
          opacity={0.4}
        />
      )}
    </svg>
  );
}
