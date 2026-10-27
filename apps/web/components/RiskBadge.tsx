const BAND_STYLES: Record<string, string> = {
  low: "bg-emerald-500/15 text-emerald-600 border-emerald-500/30 dark:text-emerald-400",
  moderate: "bg-yellow-500/15 text-yellow-700 border-yellow-500/30 dark:text-yellow-400",
  elevated: "bg-orange-500/15 text-orange-600 border-orange-500/30 dark:text-orange-400",
  high: "bg-red-500/15 text-red-600 border-red-500/30 dark:text-red-400",
  unknown: "bg-zinc-500/15 text-zinc-600 border-zinc-500/30 dark:text-zinc-400",
};

export default function RiskBadge({
  score,
  band,
}: {
  score: number | null;
  band: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${BAND_STYLES[band] ?? BAND_STYLES.unknown}`}
    >
      {band}
      {score != null && <span className="tabular-nums opacity-80">{score.toFixed(0)}</span>}
    </span>
  );
}
