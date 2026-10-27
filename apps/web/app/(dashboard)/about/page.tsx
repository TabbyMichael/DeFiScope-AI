import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function AboutPage() {
  return (
    <div className="max-w-3xl space-y-6 text-sm leading-relaxed text-muted-foreground">
      <h1 className="text-2xl font-semibold tracking-tight text-foreground">
        Methodology &amp; limitations
      </h1>
      <p>
        DeFiScope AI scores protocols using only public TVL data from DefiLlama.
        The full methodology — formulas, score anchors, weights and alert
        thresholds — lives in{" "}
        <code className="rounded bg-muted px-1.5 py-0.5 text-xs text-foreground">
          docs/methodology.md
        </code>{" "}
        in the repository.
      </p>
      <Card>
        <CardHeader>
          <CardTitle>What scores can show</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="list-disc space-y-1 pl-5">
            <li>How TVL is distributed across chains (shared-infrastructure exposure)</li>
            <li>How unstable or trending TVL has been over 7/30-day windows</li>
            <li>How much reported value sits in staking/incentive buckets when available</li>
            <li>Audit metadata and curated historical security notes</li>
          </ul>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>What scores cannot show</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="list-disc space-y-1 pl-5">
            <li>
              Whether a TVL move is caused by token price changes or real usage —
              USD TVL conflates both
            </li>
            <li>Whether growth is incentive-driven (emissions schedules are not in this data)</li>
            <li>Smart-contract safety — audit counts are a weak proxy, never a guarantee</li>
            <li>Wash trading, sybil activity, or oracle/liquidation risk</li>
          </ul>
        </CardContent>
      </Card>
      <p>
        Indicators with missing data are excluded from the composite score and
        reported as <span className="text-foreground">data gaps</span> rather than
        treated as &quot;safe&quot;. A low score means &quot;low risk on the
        dimensions TVL data can observe&quot; — nothing more.
      </p>
    </div>
  );
}
