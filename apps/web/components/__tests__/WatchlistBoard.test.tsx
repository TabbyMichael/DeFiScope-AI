import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WatchlistBoard from "@/components/dashboard/watchlist-board";
import type {
  DashboardStats,
  ProtocolOverview,
  WatchlistPage,
} from "@/lib/types";

// Route the board's URL-driven controls through a spy we can assert against.
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/watchlist",
}));

// AnimatedNumber counts up via rAF unless `prefers-reduced-motion` is set; force
// the reduced path so the first paint already shows the final (server) value,
// which is exactly what we assert (hero must read server totals, not page len).
beforeEach(() => {
  push.mockClear();
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: true,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

// Every ProtocolOverview field is required by DeepRequired (nullable ones stay
// `T | null`), so the fixture is exhaustive and only the fields the board reads
// vary per test.
function makeOverview(over: Partial<ProtocolOverview> = {}): ProtocolOverview {
  return {
    as_of: "2026-02-01",
    category: "Lending",
    change_30d: 5,
    change_7d: 2.5,
    depeg_asset: null,
    depeg_worst_bps: null,
    fees_1d: null,
    fees_30d: null,
    fees_tvl: null,
    incentive_ratio: null,
    name: "Aave v3",
    revenue_1d: null,
    risk_band: "moderate",
    risk_score: 42,
    slug: "aave-v3",
    source: "defillama",
    sparkline: [],
    stale_days: null,
    top_chain: "Ethereum",
    top_chain_share: 60,
    tvl: 1_000_000,
    volatility_30d: null,
    volume_1d: null,
    volume_tvl: null,
    ...over,
  };
}

function makeStats(over: Partial<DashboardStats> = {}): DashboardStats {
  return {
    active_critical: 2,
    active_warning: 3,
    by_band: { low: 137, moderate: 249, elevated: 51, high: 33, unknown: 4530 },
    protocol_count: 5000,
    top_gainer: { slug: "uniswap", name: "Uniswap", change_7d: 12.3 },
    top_loser: { slug: "lido", name: "Lido", change_7d: -8.4 },
    total_tvl: 5_000_000_000,
    ...over,
  };
}

// Counts chosen to never collide with the page-size options (50/100/200) or the
// page total, so `getByText` on a tile number stays unambiguous.
function makePage(over: Partial<WatchlistPage> = {}): WatchlistPage {
  return {
    as_of: "2026-02-01",
    band: null,
    band_counts: { low: 137, moderate: 249, elevated: 51, high: 33, unknown: 4530 },
    dir: "desc",
    items: [makeOverview(), makeOverview({ slug: "lido", name: "Lido", risk_band: "high", risk_score: 88 })],
    page: 1,
    pages: 50,
    q: null,
    size: 100,
    sort: "risk",
    stats: makeStats(),
    total: 5000,
    withheld: 0,
    ...over,
  };
}

describe("WatchlistBoard · page variant (server-paginated)", () => {
  it("drives the hero from the server summary, not the page length", () => {
    render(<WatchlistBoard variant="page" data={makePage()} stats={makeStats()} />);

    // 2 rows are on this page, but the market total (5,000) and scored count
    // (137+249+51+33 = 470) come from the server summary.
    expect(screen.getByText("Tracked protocols")).toBeInTheDocument();
    expect(screen.getByText("5,000")).toBeInTheDocument();
    expect(screen.getByText("470 scored")).toBeInTheDocument();
    expect(screen.getByText("$5.00B")).toBeInTheDocument();
    // The top mover is the server's, echoed by name.
    expect(within(screen.getByText("Top 7d mover").parentElement as HTMLElement).getByText(/Uniswap/)).toBeInTheDocument();
  });

  it("renders band tiles straight from band_counts", () => {
    render(<WatchlistBoard variant="page" data={makePage()} stats={makeStats()} />);
    // Low + high tile counts (unique, never equal to page-size options).
    expect(screen.getByText("137")).toBeInTheDocument();
    expect(screen.getByText("33")).toBeInTheDocument();
  });

  it("shows a truthful pagination window over the whole market", () => {
    render(<WatchlistBoard variant="page" data={makePage()} stats={makeStats()} />);
    expect(screen.getByText(/Showing 1–2 of 5,000/)).toBeInTheDocument();
    expect(screen.getByText(/Page 1 \/ 50/)).toBeInTheDocument();
  });

  it("disables Prev on the first page and pushes page=2 on Next", () => {
    render(<WatchlistBoard variant="page" data={makePage()} stats={makeStats()} />);
    expect(screen.getByRole("button", { name: /Prev/ })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /Next/ }));
    expect(push).toHaveBeenCalledTimes(1);
    const url = push.mock.calls[0][0] as string;
    expect(url).toContain("/watchlist?");
    expect(url).toContain("page=2");
  });

  it("pushes the active window when moving off the first page", () => {
    render(
      <WatchlistBoard
        variant="page"
        data={makePage({ page: 3 })}
        stats={makeStats()}
      />,
    );
    // offset = (3-1)*100 = 200 → "Showing 201–202 of 5,000".
    expect(screen.getByText(/Showing 201–202 of 5,000/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Prev/ })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: /Prev/ }));
    expect(push.mock.calls[0][0]).toContain("page=2");
  });

  it("updates the URL when a sort control is chosen", () => {
    render(<WatchlistBoard variant="page" data={makePage()} stats={makeStats()} />);
    fireEvent.click(screen.getByRole("button", { name: /Largest TVL/ }));
    const url = push.mock.calls[0][0] as string;
    expect(url).toContain("sort=tvl");
    // Changing sort resets to page 1 (no page=2 left behind).
    expect(url).not.toContain("page=2");
  });

  it("filters by band through the chip, keeping the market-wide totals", () => {
    render(<WatchlistBoard variant="page" data={makePage()} stats={makeStats()} />);
    // High band chip (band tiles + chips both render the label, so scope to the
    // chip button that carries the band name as its accessible label).
    const chips = screen.getAllByRole("button", { name: "high" });
    fireEvent.click(chips[chips.length - 1]);
    const url = push.mock.calls[0][0] as string;
    expect(url).toContain("band=high");
    // Hero total is still the server summary (5,000), never the filtered page.
    expect(screen.getByText("5,000")).toBeInTheDocument();
  });

  it("renders the honest empty state when a page has no rows", () => {
    render(
      <WatchlistBoard
        variant="page"
        data={makePage({ items: [], total: 0, pages: 0, page: 1 })}
        stats={makeStats()}
      />,
    );
    expect(screen.getByText(/No scored protocols in this view yet/)).toBeInTheDocument();
    expect(screen.getByText(/No matching protocols/)).toBeInTheDocument();
  });

  it("returns null for the page variant when no data is supplied", () => {
    const { container } = render(
      <WatchlistBoard variant="page" stats={makeStats()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("WatchlistBoard · section variant (Overview compact board)", () => {
  const protocols = [
    makeOverview({ slug: "p1", name: "P1", risk_score: 10 }),
    makeOverview({ slug: "p2", name: "P2", risk_score: 90 }),
    makeOverview({ slug: "p3", name: "P3", risk_score: 50 }),
  ];

  it("shows the highest-risk rows first and cites the full market count", () => {
    render(<WatchlistBoard variant="section" protocols={protocols} stats={makeStats()} />);
    // Compact board ranks by risk desc: P2 (90) leads.
    // Section board interpolates the raw count (no locale grouping, unlike the
    // page hero's AnimatedNumber), so it reads "of 5000".
    expect(screen.getByText(/showing 3 of 5000/)).toBeInTheDocument();
    expect(screen.getByText("Open watchlist →")).toBeInTheDocument();
    const rows = screen.getAllByRole("link").filter((a) => a.getAttribute("href")?.startsWith("/protocols/"));
    expect(rows[0]).toHaveTextContent("P2");
  });

  it("renders the data-gap empty state when there are no rows", () => {
    render(<WatchlistBoard variant="section" protocols={[]} stats={makeStats()} />);
    expect(screen.getByText(/No scored protocols in this view yet/)).toBeInTheDocument();
  });
});
