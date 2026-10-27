export default function AboutPage() {
  return (
    <div className="max-w-3xl space-y-6 text-sm leading-relaxed text-zinc-400">
      <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">
        Methodology &amp; limitations
      </h1>
      <p>
        DeFiScope AI scores protocols using only public TVL data from DefiLlama.
        The full methodology — formulas, score anchors, weights and alert
        thresholds — lives in{" "}
        <code className="rounded bg-zinc-900 px-1.5 py-0.5 text-xs text-zinc-300">
          docs/methodology.md
        </code>{" "}
        in the repository.
      </p>
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
        <h2 className="mb-2 text-sm font-medium text-zinc-200">What scores can show</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>How TVL is distributed across chains (shared-infrastructure exposure)</li>
          <li>How unstable or trending TVL has been over 7/30-day windows</li>
          <li>How much reported value sits in staking/incentive buckets when available</li>
          <li>Audit metadata and curated historical security notes</li>
        </ul>
      </div>
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
        <h2 className="mb-2 text-sm font-medium text-zinc-200">What scores cannot show</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            Whether a TVL move is caused by token price changes or real usage —
            USD TVL conflates both
          </li>
          <li>Whether growth is incentive-driven (emissions schedules are not in this data)</li>
          <li>Smart-contract safety — audit counts are a weak proxy, never a guarantee</li>
          <li>Wash trading, sybil activity, or oracle/liquidation risk</li>
        </ul>
      </div>
      <p>
        Indicators with missing data are excluded from the composite score and
        reported as <span className="text-zinc-300">data gaps</span> rather than
        treated as &quot;safe&quot;. A low score means &quot;low risk on the
        dimensions TVL data can observe&quot; — nothing more.
      </p>
    </div>
  );
}
