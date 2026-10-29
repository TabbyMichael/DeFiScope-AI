import { describe, expect, it } from "vitest";

import { MAX_COMPARE, bestIndexOf, parseSlugs } from "@/lib/compare";

describe("parseSlugs", () => {
  it("splits, trims and lowercases a comma-separated string", () => {
    expect(parseSlugs(" Aave-v3 , uniswap-v3 ")).toEqual({
      slugs: ["aave-v3", "uniswap-v3"],
      truncated: false,
    });
  });

  it("accepts the Next.js string[] searchParams shape", () => {
    expect(parseSlugs(["aave-v3,layerzero", "lido"]).slugs).toEqual([
      "aave-v3",
      "layerzero",
      "lido",
    ]);
  });

  it("deduplicates case-insensitively while preserving order", () => {
    expect(parseSlugs("aave,Aave,aave-v3,uniswap-v3").slugs).toEqual([
      "aave",
      "aave-v3",
      "uniswap-v3",
    ]);
  });

  it("drops empty segments", () => {
    expect(parseSlugs("aave,,  ,uniswap").slugs).toEqual(["aave", "uniswap"]);
  });

  it("handles undefined / empty input", () => {
    expect(parseSlugs(undefined)).toEqual({ slugs: [], truncated: false });
    expect(parseSlugs("")).toEqual({ slugs: [], truncated: false });
  });

  it(`caps at MAX_COMPARE (${MAX_COMPARE}) and flags truncation`, () => {
    const result = parseSlugs("a,b,c,d,e");
    expect(result.slugs).toEqual(["a", "b", "c"]);
    expect(result.truncated).toBe(true);
  });

  it("does not flag truncation when exactly at the cap", () => {
    const exact = parseSlugs("a,b,c");
    expect(exact.slugs).toHaveLength(MAX_COMPARE);
    expect(exact.truncated).toBe(false);
  });
});

describe("bestIndexOf", () => {
  it("finds the max index (TVL-style)", () => {
    expect(bestIndexOf([100, 300, 200], "max")).toBe(1);
  });

  it("finds the min index (risk-style)", () => {
    expect(bestIndexOf([40, 10, 25], "min")).toBe(1);
  });

  it("returns null when fewer than two comparable values exist", () => {
    expect(bestIndexOf([null, 5, null], "max")).toBeNull();
    expect(bestIndexOf([], "min")).toBeNull();
    expect(bestIndexOf([7], "max")).toBeNull();
  });

  it("ignores nulls and NaN when ranking", () => {
    expect(bestIndexOf([null, 50, NaN, 80], "max")).toBe(3);
    expect(bestIndexOf([90, null, 20], "min")).toBe(2);
  });

  it("returns the first index on ties", () => {
    expect(bestIndexOf([50, 50, 50], "max")).toBe(0);
  });
});
