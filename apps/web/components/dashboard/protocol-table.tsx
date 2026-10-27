"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

import RiskBadge from "@/components/RiskBadge";
import Sparkline from "@/components/dashboard/sparkline";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fmtPct, fmtUsd } from "@/lib/api";
import type { ProtocolOverview } from "@/lib/types";

type SortKey = "name" | "tvl" | "change_7d" | "change_30d" | "risk_score";
const ALL = "all";

function ChangeCell({ value }: { value: number | null }) {
  if (value == null) return <span className="text-muted-foreground">—</span>;
  const tone =
    value > 1
      ? "text-emerald-600 dark:text-emerald-400"
      : value < -1
        ? "text-red-600 dark:text-red-400"
        : "text-muted-foreground";
  return <span className={`tabular-nums ${tone}`}>{fmtPct(value)}</span>;
}

// Defined at module scope so it keeps a stable component identity across
// re-renders (defining it inside ProtocolTable would remount the header buttons
// and drop their focus/transition state on every sort/filter change).
function SortHead({
  label,
  columnKey,
  sortKey,
  dir,
  onSort,
  className,
}: {
  label: string;
  columnKey: SortKey;
  sortKey: SortKey;
  dir: "asc" | "desc";
  onSort: (key: SortKey) => void;
  className?: string;
}) {
  const active = sortKey === columnKey;
  return (
    <TableHead className={className}>
      <Button
        variant="ghost"
        size="sm"
        className="-ml-2 h-7 px-2 text-xs font-medium"
        onClick={() => onSort(columnKey)}
      >
        {label}
        {active ? (
          dir === "asc" ? <ArrowUp className="ml-1 size-3" /> : <ArrowDown className="ml-1 size-3" />
        ) : (
          <ArrowUpDown className="ml-1 size-3 opacity-40" />
        )}
      </Button>
    </TableHead>
  );
}

export default function ProtocolTable({
  protocols,
}: {
  protocols: ProtocolOverview[];
}) {
  const [sortKey, setSortKey] = useState<SortKey>("tvl");
  const [dir, setDir] = useState<"asc" | "desc">("desc");
  const [band, setBand] = useState<string>(ALL);
  const [category, setCategory] = useState<string>(ALL);

  const categories = useMemo(
    () =>
      Array.from(
        new Set(protocols.map((p) => p.category).filter((c): c is string => !!c)),
      ).sort(),
    [protocols],
  );

  const rows = useMemo(() => {
    const filtered = protocols.filter(
      (p) =>
        (band === ALL || p.risk_band === band) &&
        (category === ALL || p.category === category),
    );
    const factor = dir === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      if (sortKey === "name") return a.name.localeCompare(b.name) * factor;
      const av = a[sortKey] ?? -Infinity;
      const bv = b[sortKey] ?? -Infinity;
      return (Number(av) - Number(bv)) * factor;
    });
  }, [protocols, band, category, sortKey, dir]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setDir(key === "name" ? "asc" : "desc");
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center gap-3 space-y-0">
        <CardTitle>Protocols</CardTitle>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Select value={category} onValueChange={setCategory}>
            <SelectTrigger size="sm" className="w-[150px]">
              <SelectValue placeholder="Category" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All categories</SelectItem>
              {categories.map((c) => (
                <SelectItem key={c} value={c}>{c}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={band} onValueChange={setBand}>
            <SelectTrigger size="sm" className="w-[140px]">
              <SelectValue placeholder="Risk band" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All risk bands</SelectItem>
              {["low", "moderate", "elevated", "high", "unknown"].map((b) => (
                <SelectItem key={b} value={b}>{b}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <SortHead label="Protocol" columnKey="name" sortKey={sortKey} dir={dir} onSort={toggleSort} />
              <TableHead className="hidden md:table-cell">Category</TableHead>
              <SortHead label="TVL" columnKey="tvl" sortKey={sortKey} dir={dir} onSort={toggleSort} className="text-right" />
              <SortHead label="7d" columnKey="change_7d" sortKey={sortKey} dir={dir} onSort={toggleSort} className="text-right" />
              <SortHead label="30d" columnKey="change_30d" sortKey={sortKey} dir={dir} onSort={toggleSort} className="hidden text-right lg:table-cell" />
              <TableHead className="hidden sm:table-cell">Trend 30d</TableHead>
              <SortHead label="Risk" columnKey="risk_score" sortKey={sortKey} dir={dir} onSort={toggleSort} />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((p) => (
              <TableRow key={p.slug}>
                <TableCell className="font-medium">
                  <Link href={`/protocols/${p.slug}`} className="text-emerald-600 hover:underline dark:text-emerald-400">
                    {p.name}
                  </Link>
                  {p.stale_days != null && p.stale_days > 1 && (
                    <span className="ml-2 rounded bg-yellow-500/15 px-1.5 py-0.5 text-[10px] text-yellow-700 dark:text-yellow-400">
                      stale {p.stale_days}d
                    </span>
                  )}
                </TableCell>
                <TableCell className="hidden text-muted-foreground md:table-cell">{p.category ?? "—"}</TableCell>
                <TableCell className="text-right tabular-nums">{fmtUsd(p.tvl)}</TableCell>
                <TableCell className="text-right"><ChangeCell value={p.change_7d} /></TableCell>
                <TableCell className="hidden text-right lg:table-cell"><ChangeCell value={p.change_30d} /></TableCell>
                <TableCell className="hidden sm:table-cell">
                  <Sparkline
                    data={p.sparkline}
                    tone={p.change_30d == null ? "flat" : p.change_30d < -1 ? "down" : p.change_30d > 1 ? "up" : "flat"}
                  />
                </TableCell>
                <TableCell>
                  <RiskBadge score={p.risk_score} band={p.risk_band} />
                </TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="h-20 text-center text-muted-foreground">
                  No protocols match the current filters.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
