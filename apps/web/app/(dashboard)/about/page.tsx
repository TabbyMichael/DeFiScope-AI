import { Bell, Check, Gauge, Info, Layers, Scale, X } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

// Grounded in the backend implementation (services/api/app):
//   - indicator weights: analysis/scoring.py (weight= on each indicator)
//   - band thresholds:   analysis/scoring.py assess() (<30/<50/<70/else)
//   - alert rules:       config.py alert_* defaults + services/alerts.py
const INDICATORS = [
  {
    label: "Stablecoin peg integrity",
    weight: 0.2,
    desc: "Worst 30-day deviation of any stablecoin the protocol mints. A depeg is the most direct solvency event, so this carries the highest weight — but only issuers in the curated map are scored; everyone else is a gap, never read as on-peg.",
  },
  {
    label: "Chain / liquidity concentration",
    weight: 0.16,
    desc: "TVL spread across chains (Herfindahl index) — a proxy for shared-infrastructure failure exposure.",
  },
  {
    label: "TVL volatility (30d)",
    weight: 0.16,
    desc: "Std-dev of daily TVL changes over the trailing 30 days, plus the worst peak-to-trough drawdown.",
  },
  {
    label: "Security posture (audits & history)",
    weight: 0.14,
    desc: "Audit count plus curated incident notes — a prompt for manual review, never a guarantee.",
  },
  {
    label: "Real-yield dependence (fees ÷ TVL)",
    weight: 0.14,
    desc: "Trailing-30d fee revenue relative to TVL — value backed by real fees scores safer. Missing fee data is a gap, never counted as safe.",
  },
  {
    label: "TVL trend (7d / 30d)",
    weight: 0.1,
    desc: "Sustained contraction scores as risk; growth alone is not treated as safe.",
  },
  {
    label: "Incentive / staking dependence",
    weight: 0.1,
    desc: "Share of reported value parked in staking / LP-reward buckets, when DefiLlama provides it.",
  },
];

const BANDS = [
  { band: "Low", range: "0–29", color: "bg-emerald-500" },
  { band: "Moderate", range: "30–49", color: "bg-yellow-500" },
  { band: "Elevated", range: "50–69", color: "bg-orange-500" },
  { band: "High", range: "70–100", color: "bg-red-500" },
];

const RULES = [
  { name: "TVL drop", trigger: "7d TVL change at or below (critical at −30%)", value: "−15%" },
  { name: "Daily shock", trigger: "24h TVL change at or below", value: "−10%" },
  { name: "TVL surge", trigger: "7d TVL change at or above", value: "+30%" },
  { name: "Incentive dependence", trigger: "staking ÷ core TVL at or above", value: "0.60" },
  { name: "Stale data", trigger: "latest observation older than", value: "2 days" },
  {
    name: "Depeg",
    trigger: "minted stablecoin off $1 peg over 30d (critical at 100 bps)",
    value: "50 bps",
  },
];

const CAN_SHOW = [
  "How TVL is distributed across chains (shared-infrastructure exposure)",
  "How unstable or trending TVL has been over 7/30-day windows",
  "How much reported value sits in staking/incentive buckets when available",
  "Audit metadata and curated historical security notes",
];

const CANNOT_SHOW = [
  "Whether a TVL move is price-driven or real usage — USD TVL conflates both",
  "Whether growth is incentive-driven (emissions schedules are not in this data)",
  "Smart-contract safety — audit counts are a weak proxy, never a guarantee",
  "Wash trading, sybil activity, or oracle/liquidation risk",
];

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header className="flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-muted">
          <Scale className="size-5" />
        </span>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
            Methodology &amp; limitations
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            DeFiScope AI scores protocols using only public TVL data from
            DefiLlama. Every number is traceable to a documented formula — and
            every score states what it cannot establish.
          </p>
        </div>
      </header>

      <Card>
        <CardHeader>
          <CardDescription className="flex items-center gap-1.5">
            <Layers className="size-3.5" /> Explainable, weighted indicators
          </CardDescription>
          <CardTitle>How the composite score is built</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            The composite (0–100, where higher is riskier) is a weighted mean of
            the indicators below. Indicators with missing data are excluded from
            the average and surfaced as data gaps — unknown is never counted as safe.
          </p>
          <ul className="space-y-3">
            {INDICATORS.map((i) => (
              <li key={i.label}>
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-sm font-medium">{i.label}</span>
                  <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                    weight {(i.weight * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary/70"
                    style={{ width: `${i.weight * 100 * 2}%` }}
                  />
                </div>
                <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{i.desc}</p>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardDescription className="flex items-center gap-1.5">
              <Gauge className="size-3.5" /> Composite score
            </CardDescription>
            <CardTitle>Risk bands</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {BANDS.map((b) => (
              <div key={b.band} className="flex items-center justify-between gap-3 text-sm">
                <span className="inline-flex items-center gap-2">
                  <span className={`size-2.5 rounded-full ${b.color}`} />
                  {b.band}
                </span>
                <span className="tabular-nums text-muted-foreground">{b.range}</span>
              </div>
            ))}
            <p className="pt-1 text-xs text-muted-foreground">
              A low score means &ldquo;low risk on the dimensions TVL data can
              observe&rdquo; — nothing more.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardDescription className="flex items-center gap-1.5">
              <Bell className="size-3.5" /> Evaluated every 30 minutes
            </CardDescription>
            <CardTitle>Alert rules &amp; thresholds</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {RULES.map((r) => (
              <div key={r.name} className="text-sm">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-medium">{r.name}</span>
                  <span className="shrink-0 tabular-nums">{r.value}</span>
                </div>
                <p className="text-xs text-muted-foreground">{r.trigger}</p>
              </div>
            ))}
            <p className="pt-1 text-xs text-muted-foreground">
              Thresholds are configurable via <code className="rounded bg-muted px-1 py-0.5">DEFISCOPE_ALERT_*</code> env vars.
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card className="border-emerald-500/30">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Check className="size-4 text-emerald-600 dark:text-emerald-400" />
              What scores can show
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm text-muted-foreground">
              {CAN_SHOW.map((t) => (
                <li key={t} className="flex gap-2">
                  <Check className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                  <span>{t}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card className="border-red-500/30">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <X className="size-4 text-red-600 dark:text-red-400" />
              What scores cannot show
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm text-muted-foreground">
              {CANNOT_SHOW.map((t) => (
                <li key={t} className="flex gap-2">
                  <X className="mt-0.5 size-4 shrink-0 text-red-600 dark:text-red-400" />
                  <span>{t}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      <div className="flex gap-3 rounded-lg border bg-muted/40 p-4 text-sm">
        <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        <p className="text-muted-foreground">
          The full formulas, score anchors, weights and thresholds live in{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs text-foreground">
            docs/methodology.md
          </code>{" "}
          in the repository, alongside the architecture and mechanics docs.
        </p>
      </div>
    </div>
  );
}
