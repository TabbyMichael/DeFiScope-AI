const BAND_STYLES: Record<string, string> = {
  low: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  moderate: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  elevated: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  high: "bg-red-500/15 text-red-400 border-red-500/30",
  unknown: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
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
