import type { RiskIndicator } from "@/lib/types";

function scoreColor(score: number | null): string {
  if (score == null) return "text-zinc-500";
  if (score < 30) return "text-emerald-400";
  if (score < 50) return "text-yellow-400";
  if (score < 70) return "text-orange-400";
  return "text-red-400";
}

export default function IndicatorCard({ indicator }: { indicator: RiskIndicator }) {
  const { label, score, evidence, limitation, weight } = indicator;
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-sm font-medium text-zinc-200">{label}</h3>
        <div className="text-right">
          <span className={`text-lg font-semibold tabular-nums ${scoreColor(score)}`}>
            {score == null ? "n/a" : score.toFixed(0)}
          </span>
          <span className="block text-[10px] text-zinc-500">
            risk 0–100 · w={weight}
          </span>
        </div>
      </div>
      {score != null && (
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded bg-zinc-800">
          <div
            className={`h-full rounded ${
              score < 30
                ? "bg-emerald-500"
                : score < 50
                  ? "bg-yellow-500"
                  : score < 70
                    ? "bg-orange-500"
                    : "bg-red-500"
            }`}
            style={{ width: `${score}%` }}
          />
        </div>
      )}
      <p className="mt-3 text-xs leading-relaxed text-zinc-400">{evidence}</p>
      <p className="mt-2 border-t border-zinc-800 pt-2 text-xs leading-relaxed text-zinc-500">
        <span className="font-medium text-zinc-400">Limitation: </span>
        {limitation}
      </p>
    </div>
  );
}
