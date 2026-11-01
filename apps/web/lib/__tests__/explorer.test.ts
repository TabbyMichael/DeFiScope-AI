import { describe, expect, it } from "vitest";

import {
  explorerFetchQuery,
  explorerHref,
  pageNumberWindow,
  parseExplorerState,
  toCatalogQuery,
} from "@/lib/explorer";

describe("parseExplorerState", () => {
  it("returns defaults for an empty query", () => {
    expect(parseExplorerState({})).toEqual({
      page: 1,
      pageSize: 25,
      q: "",
      chain: "",
      category: "",
      band: "",
      sort: "tvl",
      order: "desc",
    });
  });

  it("accepts a valid page size and coerces a numeric page", () => {
    const s = parseExplorerState({ page: "3", page_size: "100", sort: "name", order: "asc" });
    expect(s.page).toBe(3);
    expect(s.pageSize).toBe(100);
    expect(s.sort).toBe("name");
    expect(s.order).toBe("asc");
  });

  it("rejects a page size outside the closed set (never asks the API for a 422)", () => {
    // The whole point: the UI cannot construct an illegal page_size.
    expect(parseExplorerState({ page_size: "7" }).pageSize).toBe(25);
    expect(parseExplorerState({ page_size: "abc" }).pageSize).toBe(25);
  });

  it("clamps a non-positive or garbage page to 1", () => {
    expect(parseExplorerState({ page: "0" }).page).toBe(1);
    expect(parseExplorerState({ page: "-4" }).page).toBe(1);
    expect(parseExplorerState({ page: "nope" }).page).toBe(1);
  });

  it("falls back to the default sort for an unknown key", () => {
    expect(parseExplorerState({ sort: "gross_revenue" }).sort).toBe("tvl");
    expect(parseExplorerState({ sort: "risk" }).sort).toBe("risk");
  });

  it("trims search terms and reads the first value of an array param", () => {
    expect(parseExplorerState({ q: "  aave  " }).q).toBe("aave");
    expect(parseExplorerState({ page: ["2", "5"] }).page).toBe(2);
  });

  it("parses the risk-band filter (preserving the band deep-link)", () => {
    expect(parseExplorerState({ band: "high" }).band).toBe("high");
    expect(parseExplorerState({ band: "  unknown " }).band).toBe("unknown");
    expect(parseExplorerState({}).band).toBe("");
  });
});

describe("toCatalogQuery", () => {
  it("omits empty strings so they are never sent as filters", () => {
    const q = toCatalogQuery(parseExplorerState({ q: "  " }));
    expect(q.q).toBeUndefined();
    expect(q.chain).toBeUndefined();
  });

  it("forwards a real search and filter", () => {
    const q = toCatalogQuery(parseExplorerState({ q: "aave", chain: "Ethereum" }));
    expect(q.q).toBe("aave");
    expect(q.chain).toBe("Ethereum");
  });

  it("forwards the band, and omits it when empty", () => {
    expect(toCatalogQuery(parseExplorerState({ band: "low" })).band).toBe("low");
    expect(toCatalogQuery(parseExplorerState({})).band).toBeUndefined();
  });
});

describe("explorerHref", () => {
  it("is a bare /explore at defaults (short, shareable URL)", () => {
    expect(explorerHref(parseExplorerState({}))).toBe("/explore");
  });

  it("honours a custom basePath and carries the band, so the board can embed it", () => {
    const href = explorerHref(parseExplorerState({ band: "high" }), "/");
    expect(href).toBe("/?band=high");
    expect(explorerHref(parseExplorerState({}), "/")).toBe("/");
  });

  it("round-trips a non-default view through parse", () => {
    const href = explorerHref(
      parseExplorerState({ q: "aave", page: "2", sort: "name", page_size: "50" }),
    );
    expect(href).toContain("q=aave");
    expect(href).toContain("page=2");
    expect(href).toContain("sort=name");
    expect(href).toContain("page_size=50");
    // Reparsing the emitted URL must reproduce the same state.
    const params = new URLSearchParams(href.split("?")[1]);
    expect(parseExplorerState(Object.fromEntries(params))).toEqual(
      parseExplorerState({ q: "aave", page: "2", sort: "name", page_size: "50" }),
    );
  });
});

describe("explorerFetchQuery", () => {
  it("always sends an explicit page and page_size", () => {
    // So the backend's default can never disagree with what the UI asked for.
    const qs = explorerFetchQuery(parseExplorerState({}));
    expect(qs).toContain("page=1");
    expect(qs).toContain("page_size=25");
  });
});

describe("pageNumberWindow", () => {
  it("always includes first and last, with the current page nearby", () => {
    expect(pageNumberWindow(1, 1)).toEqual([1]);
    expect(pageNumberWindow(10, 20)).toEqual([1, null, 9, 10, 11, null, 20]);
  });

  it("returns nothing for an empty result set", () => {
    expect(pageNumberWindow(1, 0)).toEqual([]);
  });
});
