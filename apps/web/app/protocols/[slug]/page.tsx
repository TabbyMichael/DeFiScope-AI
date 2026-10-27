import Link from "next/link";
import { notFound } from "next/navigation";

import IndicatorCard from "@/components/IndicatorCard";
import RiskBadge from "@/components/RiskBadge";
import TvlChart from "@/components/TvlChart";
import { api, fmtPct, fmtUsd } from "@/lib/api";
import type { ProtocolResearch, ResearchBrief } from "@/lib/types";

export default async function ProtocolPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  let data: ProtocolResearch;
  let brief: ResearchBrief | null = null;
  try {
    data = await api.protocol(slug);
    try {
      brief = await api.brief(slug);
    } catch {
      brief = null; // brief generation failure must not break the research page
    }
  } catch (e) {
    console.error("protocol page error", e);
    notFound();
  }

  const o = data.overview;
  return (
    <div className="space-y-8">
      <nav className="text-xs text-zinc-500">
        <Link href="/" className="hover:text-zinc-300">
          ← Dashboard
        </Link>
      </nav>

      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{data.name}</h1>
          <p className="mt-1 text-sm text-zinc-500">
            {data.category ?? "Uncategorized"} · source:{" "}
            {data.url ? (
              <a href={data.url} target="_blank" rel="noreferrer" className="underline hover:text-zinc-300">
                DefiLlama/{data.slug}
              </a>
            ) : (
              "DefiLlama"
            )}
          </p>
        </div>
        <div className="text-right">
          <div className="text-3xl font-semibold tabular-nums">{fmtUsd(o.tvl)}</div>
          <div className="mt-1 flex items-center justify-end gap-2 text-xs text-zinc-500">
            <span>7d {fmtPct(o.change_7d)}</span>
            <span>·</span>
            <span>30d {fmtPct(o.change_30d)}</span>
            <span>·</span>
            <span>as of {data.as_of}</span>
          </div>
        </div>
      </header>

      {o.stale_days != null && o.stale_days > 1 && (
        <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-3 text-sm text-yellow-300">
          ⚠ Data freshness: the latest DefiLlama observation is {o.stale_days} days
          old. Treat conclusions as provisional.
        </div>
      )}

      <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
        <h2 className="mb-3 text-sm font-medium text-zinc-300">TVL history (180d)</h2>
        <TvlChart data={data.tvl_series} />
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-zinc-300">
            Explainable risk assessment
          </h2>
          <RiskBadge score={data.risk.composite_score} band={data.risk.band} />
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {data.risk.indicators?.map((i) => (
            <IndicatorCard key={i.key} indicator={i} />
          ))}
        </div>
        {data.data_gaps.length > 0 && (
          <p className="mt-3 text-xs text-zinc-500">
            <span className="font-medium text-zinc-400">Data gaps: </span>
            {data.data_gaps.join(", ")} — excluded from the composite rather than
            treated as &quot;safe&quot;.
          </p>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium text-zinc-300">TVL by chain</h2>
        <div className="space-y-1.5">
          {data.chains.map((c) => (
            <div key={c.chain} className="flex items-center gap-3 text-sm">
              <span className="w-32 shrink-0 text-zinc-400">{c.chain}</span>
              <div className="h-2 flex-1 overflow-hidden rounded bg-zinc-800">
                <div
                  className="h-full rounded bg-sky-500/70"
                  style={{ width: `${Math.max(0.5, c.share * 100)}%` }}
                />
              </div>
              <span className="w-24 text-right tabular-nums text-xs text-zinc-500">
                {fmtUsd(c.tvl)} · {(c.share * 100).toFixed(1)}%
              </span>
            </div>
          ))}
        </div>
      </section>

      {brief && (
        <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-medium text-zinc-300">Generated research brief</h2>
            <span className="rounded-full border border-zinc-700 px-2 py-0.5 text-[10px] uppercase tracking-wide text-zinc-500">
              {brief.generated_by === "llm" ? "LLM-generated" : "template engine · no LLM key"}
            </span>
          </div>
          <p className="text-sm leading-relaxed text-zinc-300">
            {brief.sections.executive_summary}
          </p>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <BriefList title="Growth drivers" items={brief.sections.growth_drivers} />
            <BriefList title="Risks" items={brief.sections.risks} />
            <BriefList title="Cannot establish" items={brief.sections.data_gaps} />
            <BriefList title="Next steps" items={brief.sections.recommendations} />
          </div>
          <p className="mt-4 border-t border-zinc-800 pt-3 text-xs text-zinc-500">
            Confidence: {brief.sections.confidence} · as of {brief.as_of} · sources:{" "}
            {brief.sources.map((s, i) => (
              <a key={s} href={s} target="_blank" rel="noreferrer" className="underline hover:text-zinc-300">
                {i > 0 && " · "}
                {s.replace("https://", "")}
              </a>
            ))}
          </p>
        </section>
      )}
    </div>
  );
}

function BriefList({ title, items }: { title: string; items: string[] }) {
  if (!items?.length) return null;
  return (
    <div>
      <h3 className="mb-1.5 text-xs font-medium uppercase tracking-wide text-zinc-500">
        {title}
      </h3>
      <ul className="space-y-1.5">
        {items.map((item, i) => (
          <li key={i} className="text-xs leading-relaxed text-zinc-400">
            • {item}
          </li>
        ))}
      </ul>
    </div>
  );
}
