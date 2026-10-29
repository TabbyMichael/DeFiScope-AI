import type { ProtocolResearch } from "./types";

/** Maximum protocols that can be compared side by side. */
export const MAX_COMPARE = 3;

/** A minimal, client-safe option for the comparison picker. */
export type CompareOption = {
  slug: string;
  name: string;
  category: string | null;
};

export type Selection = {
  slugs: string[];
  /** true when more than MAX_COMPARE unique slugs were requested. */
  truncated: boolean;
};

/**
 * Parse the `?slugs=a,b,c` search param into a deduped, ordered, capped list.
 * Accepts the Next.js searchParams shape (string | string[] | undefined).
 */
export function parseSlugs(raw: string | string[] | undefined): Selection {
  const joined = Array.isArray(raw) ? raw.join(",") : (raw ?? "");
  const cleaned = Array.from(
    new Set(
      joined
        .split(",")
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean),
    ),
  );
  return {
    slugs: cleaned.slice(0, MAX_COMPARE),
    truncated: cleaned.length > MAX_COMPARE,
  };
}

/**
 * Index of the "best" value in a column of numbers, for highlighting.
 * Returns null when fewer than two comparable values exist (nothing to rank)
 * or on NaN/null. `better: "min"` is for risk/volatility/staleness,
 * `"max"` is for TVL.
 */
export function bestIndexOf(values: (number | null)[], better: "min" | "max"): number | null {
  const valid = values
    .map((v, i) => ({ v, i }))
    .filter((x): x is { v: number; i: number } => x.v != null && !Number.isNaN(x.v));
  if (valid.length < 2) return null;
  return valid.reduce((a, b) =>
    better === "min" ? (b.v < a.v ? b : a) : b.v > a.v ? b : a,
  ).i;
}

/** A single column of the comparison, resolved from a fetch attempt. */
export type CompareItem = {
  slug: string;
  /** null when the protocol could not be loaded (bad slug / API down). */
  data: ProtocolResearch | null;
};
