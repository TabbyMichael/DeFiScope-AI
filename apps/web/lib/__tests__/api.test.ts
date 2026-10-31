import { afterEach, describe, expect, it, vi } from "vitest";

import { api, fmtPct, fmtUsd, resolveApiPublicUrl } from "@/lib/api";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("resolveApiPublicUrl", () => {
  it("prefers the browser-facing public URL when set (Docker)", () => {
    expect(
      resolveApiPublicUrl("http://localhost:3646", "http://api:8000"),
    ).toBe("http://localhost:3646");
  });

  it("falls back to the internal server URL for local dev", () => {
    expect(resolveApiPublicUrl(undefined, "http://localhost:8000")).toBe(
      "http://localhost:8000",
    );
  });

  it("falls back to localhost when nothing is configured", () => {
    expect(resolveApiPublicUrl(undefined, undefined)).toBe(
      "http://localhost:8000",
    );
  });

  it("never points the browser at the unresolvable compose host", () => {
    // Regression guard: the docs link must not use the internal `api:8000`.
    const url = resolveApiPublicUrl("http://localhost:3646", "http://api:8000");
    expect(url).not.toContain("api:8000");
  });
});

describe("fmtUsd", () => {
  it("formats billions, millions and thousands with compact suffixes", () => {
    expect(fmtUsd(1_500_000_000)).toBe("$1.50B");
    expect(fmtUsd(2_340_000)).toBe("$2.34M");
    expect(fmtUsd(12_500)).toBe("$12.5K");
    expect(fmtUsd(950)).toBe("$950");
  });

  it("renders n/a for missing values", () => {
    expect(fmtUsd(null)).toBe("n/a");
    expect(fmtUsd(undefined)).toBe("n/a");
  });
});

describe("fmtPct", () => {
  it("prefixes positive changes with a plus sign", () => {
    expect(fmtPct(12.345)).toBe("+12.3%");
    expect(fmtPct(-8.2, 2)).toBe("-8.20%");
  });

  it("renders n/a for missing values", () => {
    expect(fmtPct(null)).toBe("n/a");
  });
});

describe("api fetch timeout", () => {
  it("rejects when a request exceeds its AbortSignal.timeout", async () => {
    // A fetch that never resolves on its own and only settles when aborted.
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init?: { signal?: AbortSignal }) =>
          new Promise((_res, rej) => {
            init?.signal?.addEventListener("abort", () => rej(init.signal!.reason));
          }),
      ),
    );

    vi.useFakeTimers();
    const pending = api.protocolHistory("aave-v3"); // default 30s budget
    // Attach the rejection assertion before advancing so the abort is never
    // observed as an unhandled rejection.
    const expectReject = expect(pending).rejects.toThrow();
    await vi.advanceTimersByTimeAsync(30_000);
    await expectReject;
  });
});

describe("api.runAlerts", () => {
  type FetchFn = (
    url: string,
    init?: RequestInit,
  ) => Promise<{
    ok: boolean;
    status: number;
    json: () => Promise<unknown>;
    text: () => Promise<string>;
  }>;

  it("POSTs to the backend /api/alerts/run and returns the fired alerts", async () => {
    const fired = [{ id: "a1" }, { id: "a2" }];
    const fetchMock = vi.fn<FetchFn>(async () => ({
      ok: true,
      status: 200,
      json: async () => fired,
      text: async () => "",
    }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.runAlerts();

    expect(result).toEqual(fired);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/alerts/run");
    expect(init?.method).toBe("POST");
  });

  it("rejects with a helpful message on a non-2xx response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<FetchFn>(async () => ({
        ok: false,
        status: 502,
        json: async () => ({}),
        text: async () => "bad gateway",
      })),
    );
    await expect(api.runAlerts()).rejects.toThrow(/502/);
  });
});
