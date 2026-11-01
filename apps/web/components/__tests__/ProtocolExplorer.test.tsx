import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ProtocolExplorer from "@/components/dashboard/protocol-explorer";
import { parseExplorerState } from "@/lib/explorer";
import type { CatalogFacets, ProtocolCatalogItem, ProtocolCatalogPage } from "@/lib/types";

const FACETS: CatalogFacets = { categories: ["Lending"], chains: ["Ethereum"] };

function makeItem(over: Partial<ProtocolCatalogItem> = {}): ProtocolCatalogItem {
  return {
    slug: "aave-v3",
    name: "Aave v3",
    category: "Lending",
    symbol: "AAVE",
    chains: ["Ethereum"],
    tvl: 12_000_000_000,
    change_1d: 1.5,
    change_7d: 2.5,
    change_1m: -3.5,
    audits: "2",
    url: "https://aave.example",
    risk_score: 42,
    risk_band: "moderate",
    monitored: true,
    listing_timestamp: 1_600_000_000,
    updated_at: "2026-01-01T00:00:00+00:00",
    ...over,
  };
}

function makePage(over: Partial<ProtocolCatalogPage> = {}): ProtocolCatalogPage {
  return {
    items: [makeItem()],
    total: 1,
    page: 1,
    page_size: 25,
    pages: 1,
    sort: "tvl",
    order: "desc",
    q: null,
    chain: null,
    category: null,
    band: null,
    ...over,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ProtocolExplorer", () => {
  it("renders a monitored protocol with its score and detail link", () => {
    render(
      <ProtocolExplorer
        initialState={parseExplorerState({})}
        initialPage={makePage()}
        facets={FACETS}
        initialError={null}
      />,
    );
    const link = screen.getByRole("link", { name: "Aave v3" });
    expect(link).toHaveAttribute("href", "/protocols/aave-v3");
    expect(screen.getByText("monitored")).toBeInTheDocument();
    expect(screen.getByText(/1 protocols/)).toBeInTheDocument();
    // The board relies on the risk-band filter surviving the band deep-link.
    expect(
      screen.getByRole("combobox", { name: "Filter by risk band" }),
    ).toBeInTheDocument();
  });

  it("shows an unscored protocol as an explicit gap, never as safe", () => {
    render(
      <ProtocolExplorer
        initialState={parseExplorerState({})}
        initialPage={makePage({
          items: [makeItem({ slug: "x", name: "X", risk_score: null, risk_band: "unknown", monitored: false })],
        })}
        facets={FACETS}
        initialError={null}
      />,
    );
    expect(screen.getByText("not scored")).toBeInTheDocument();
    expect(screen.queryByText("monitored")).not.toBeInTheDocument();
  });

  it("does not refetch on mount (the RSC already served the first page)", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(
      <ProtocolExplorer
        initialState={parseExplorerState({})}
        initialPage={makePage()}
        facets={FACETS}
        initialError={null}
      />,
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("fetches the next page server-side when paging", async () => {
    const next = makePage({
      items: [makeItem({ slug: "next-1", name: "Next One" })],
      total: 60,
      page: 2,
      pages: 3,
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => next } as unknown as Response);
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ProtocolExplorer
        initialState={parseExplorerState({})}
        initialPage={makePage({ total: 60, pages: 3 })}
        facets={FACETS}
        initialError={null}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toContain("/api/catalog?");
    expect(fetchMock.mock.calls[0][0]).toContain("page=2");
    expect(await screen.findByText("Next One")).toBeInTheDocument();
  });

  it("surfaces an upstream error instead of an empty table", () => {
    render(
      <ProtocolExplorer
        initialState={parseExplorerState({})}
        initialPage={null}
        facets={FACETS}
        initialError="boom"
      />,
    );
    expect(screen.getByText("Could not load protocols")).toBeInTheDocument();
    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("renders an honest empty state when a filter matches nothing", () => {
    render(
      <ProtocolExplorer
        initialState={parseExplorerState({ q: "zzz" })}
        initialPage={makePage({ items: [], total: 0, pages: 0 })}
        facets={FACETS}
        initialError={null}
      />,
    );
    expect(screen.getByText(/No protocols match/)).toBeInTheDocument();
  });
});
