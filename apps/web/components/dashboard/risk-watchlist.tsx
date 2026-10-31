import Link from "next/link";
import { ShieldAlert } from "lucide-react";

import RiskBadge from "@/components/RiskBadge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { fmtPct, fmtUsd } from "@/lib/api-config";
import type { ProtocolOverview } from "@/lib/types";

export default function RiskWatchlist({
  protocols,
  limit = 5,
}: {
  protocols: ProtocolOverview[];
  limit?: number;
}) {
  const ranked = [...protocols]
    .filter((p) => p.risk_score != null && p.risk_band !== "unknown")
    .sort((a, b) => (b.risk_score ?? 0) - (a.risk_score ?? 0))
    .slice(0, limit);

  return (
    <Card>
      <CardHeader>
        <CardDescription className="flex items-center gap-1.5">
          <ShieldAlert className="size-3.5" /> Highest risk
        </CardDescription>
        <CardTitle>Risk watchlist</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        {ranked.length === 0 && (
          <p className="text-sm text-muted-foreground">No scored protocols yet.</p>
        )}
        {ranked.map((p) => (
          <Link
            key={p.slug}
            href={`/protocols/${p.slug}`}
            className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted/60"
          >
            <div className="min-w-0">
              <div className="truncate font-medium">{p.name}</div>
              <div className="text-xs text-muted-foreground">
                {fmtUsd(p.tvl)} · 30d {fmtPct(p.change_30d)}
              </div>
            </div>
            <RiskBadge score={p.risk_score} band={p.risk_band} />
          </Link>
        ))}
      </CardContent>
    </Card>
  );
}
