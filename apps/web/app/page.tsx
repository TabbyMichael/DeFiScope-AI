import Link from "next/link";

import RiskBadge from "@/components/RiskBadge";
import { api, fmtPct, fmtUsd } from "@/lib/api";
import type { Alert, ProtocolOverview } from "@/lib/types";

function ChangeCell({ value }: { value: number | null }) {
  if (value == null) return <td className="px-3 py-2.5 text-zinc-600">—</td>;
  const tone =
    value > 1 ? "text-emerald-400" : value < -1 ? "text-red-400" : "text-zinc-400";
  return <td className={`px-3 py-2.5 tabular-nums ${tone}`}>{fmtPct(value)}</td>;
}

export default async function DashboardPage() {
  let protocols: ProtocolOverview[] = [];
  let alerts: Alert[] = [];
  let error: string | null = null;
  try {
    [protocols, alerts] = await Promise.all([api.protocols(), api.alerts()]);
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-900/50 bg-red-950/30 p-6 text-sm">
        <h2 className="mb-1 font-semibold text-red-300">API unavailable</h2>
        <p className="text-red-200/80">
          Could not reach the DeFiScope API. Start the backend with{" "}
          <code className="rounded bg-black/40 px-1.5 py-0.5 text-xs">
            cd services/api && uv run uvicorn app.main:app --port 8000
          </code>
        </p>
        <p className="mt-2 text-xs text-red-400/60">{error}</p>
      </div>
    );
  }

  const critical = alerts.filter((a) => a.severity === "critical");
  const warnings = alerts.filter((a) => a.severity === "warning");

  return (
    <div className="space-y-8">
      <section>
        <div className="flex items-baseline justify-between">
          <h1 className="text-2xl font-semibold tracking-tight">
            Protocol research board
          </h1>
          {protocols[0]?.as_of && (
            <span className="text-xs text-zinc-500">data as of {protocols[0].as_of}</span>
          )}
        </div>
        <p className="mt-1 text-sm text-zinc-500">
          TVL trends only — rising or falling TVL alone does not prove sustainable
          growth or risk. Open a protocol for evidence and limitations.
        </p>
      </section>

      {(critical.length > 0 || warnings.length > 0) && (
        <section className="grid gap-3 sm:grid-cols-2">
          {critical.slice(0, 2).map((a) => (
            <Link
              key={a.id}
              href="/alerts"
              className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300 hover:bg-red-500/15"
            >
              ⛔ {a.message}
            </Link>
          ))}
          {warnings.slice(0, 2).map((a) => (
            <Link
              key={a.id}
              href="/alerts"
              className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-3 text-sm text-yellow-300 hover:bg-yellow-500/15"
            >
              ⚠ {a.message}
            </Link>
          ))}
        </section>
      )}

      <section className="overflow-x-auto rounded-xl border border-zinc-800">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-zinc-800 bg-zinc-900/60 text-xs uppercase tracking-wide text-zinc-500">
            <tr>
              <th className="px-3 py-2.5">Protocol</th>
              <th className="px-3 py-2.5">Category</th>
              <th className="px-3 py-2.5 text-right">TVL</th>
              <th className="px-3 py-2.5 text-right">7d</th>
              <th className="px-3 py-2.5 text-right">30d</th>
              <th className="px-3 py-2.5 text-right">Vol 30d</th>
              <th className="px-3 py-2.5">Top chain</th>
              <th className="px-3 py-2.5">Risk</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60">
            {protocols.map((p) => (
              <tr key={p.slug} className="hover:bg-zinc-900/50">
                <td className="px-3 py-2.5 font-medium">
                  <Link href={`/protocols/${p.slug}`} className="text-emerald-400 hover:underline">
                    {p.name}
                  </Link>
                  {p.stale_days != null && p.stale_days > 1 && (
                    <span className="ml-2 rounded bg-yellow-500/15 px-1.5 py-0.5 text-[10px] text-yellow-400">
                      stale {p.stale_days}d
                    </span>
                  )}
                </td>
                <td className="px-3 py-2.5 text-zinc-400">{p.category ?? "—"}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{fmtUsd(p.tvl)}</td>
                <ChangeCell value={p.change_7d} />
                <ChangeCell value={p.change_30d} />
                <td className="px-3 py-2.5 text-right tabular-nums text-zinc-400">
                  {p.volatility_30d != null ? `${(p.volatility_30d * 100).toFixed(2)}%` : "—"}
                </td>
                <td className="px-3 py-2.5 text-zinc-400">
                  {p.top_chain ?? "—"}
                  {p.top_chain_share != null && (
                    <span className="ml-1 text-xs text-zinc-600">
                      {(p.top_chain_share * 100).toFixed(0)}%
                    </span>
                  )}
                </td>
                <td className="px-3 py-2.5">
                  <RiskBadge score={p.risk_score} band={p.risk_band} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="grid gap-4 sm:grid-cols-3">
        {protocols.slice(0, 3).map((p) => (
          <Link
            key={p.slug}
            href={`/protocols/${p.slug}`}
            className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 hover:border-zinc-700"
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">{p.name}</span>
              <RiskBadge score={p.risk_score} band={p.risk_band} />
            </div>
            <div className="mt-2 text-xs text-zinc-500">
              {fmtUsd(p.tvl)} · 30d {fmtPct(p.change_30d)} — view evidence →
            </div>
          </Link>
        ))}
      </section>
    </div>
  );
}
