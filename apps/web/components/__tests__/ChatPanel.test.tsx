import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatPanel, prettyReply } from "@/components/chat/chat-panel";

const CITATIONS = [
  { n: 1, source: "Methodology", location: "Real yield", quote: "fees-backed growth share" },
];

const ANSWER = {
  answer: "Real yield is fees-backed growth [1].",
  citations: CITATIONS,
  grounded: true,
  generated_by: "extractive",
  model: null,
};

function askQuestion() {
  const box = screen.getByPlaceholderText(/Lido/);
  fireEvent.change(box, { target: { value: "what is real yield" } });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ChatPanel", () => {
  it("falls back to the POST proxy when no WebSocket is available", async () => {
    vi.stubGlobal("WebSocket", undefined);
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ANSWER } as unknown as Response);
    vi.stubGlobal("fetch", fetchMock);

    render(<ChatPanel protocols={[]} />);
    askQuestion();

    // Answer text + the offline badge surface; the Sources list is intentionally
    // no longer shown (the reply stands alone).
    expect(await screen.findByText(/Real yield is fees-backed growth/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/chat",
      expect.objectContaining({ method: "POST" }),
    );
    expect(screen.queryByText("Sources")).not.toBeInTheDocument();
    expect(screen.getByText("offline · quoted evidence")).toBeInTheDocument();
  });

  it("streams tokens over the WebSocket and never calls POST", async () => {
    // The ticket mint is the one fetch the WS path is allowed to make; fail it
    // so the socket opens unauthenticated (the `auth_mode=off` shape).
    const fetchMock = vi.fn().mockRejectedValue(new Error("no ticket"));
    vi.stubGlobal("fetch", fetchMock);

    class FakeWS {
      static OPEN = 1;
      readyState = 1;
      onopen?: () => void;
      onmessage?: (ev: { data: string }) => void;
      onclose?: () => void;
      onerror?: () => void;
      constructor() {
        setTimeout(() => this.onopen?.(), 0);
      }
      send() {
        setTimeout(() => {
          this.onmessage?.({ data: JSON.stringify({ type: "citations", citations: CITATIONS }) });
          this.onmessage?.({ data: JSON.stringify({ type: "token", text: "Real " }) });
          this.onmessage?.({ data: JSON.stringify({ type: "token", text: "yield [1]." }) });
          this.onmessage?.({
            data: JSON.stringify({
              type: "done",
              answer: { ...ANSWER, answer: "Real yield [1].", generated_by: "llm", model: "gpt-4o-mini" },
            }),
          });
        }, 0);
      }
      close() {
        this.onclose?.();
      }
    }
    vi.stubGlobal("WebSocket", FakeWS);

    render(<ChatPanel protocols={[]} />);
    askQuestion();

    expect(await screen.findByText(/Real yield \[1\]/)).toBeInTheDocument();
    expect(screen.queryByText("Sources")).not.toBeInTheDocument();
    expect(screen.getByText("model: gpt-4o-mini")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith("/api/chat", expect.anything());
  });

  it("mints a WS ticket and retries once on a 1008 policy violation", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ticket: "tkt-1", expires_in: 60 }),
    } as unknown as Response);
    vi.stubGlobal("fetch", fetchMock);

    const opened: string[] = [];
    class TicketWS {
      static OPEN = 1;
      readyState = 1;
      onopen?: () => void;
      onmessage?: (ev: { data: string }) => void;
      onclose?: (ev: { code: number }) => void;
      onerror?: () => void;
      constructor(url: string) {
        opened.push(url);
        setTimeout(() => {
          if (opened.length === 1) {
            // First attempt: the API rejects the socket as a policy violation.
            this.onclose?.({ code: 1008 });
            return;
          }
          this.onopen?.();
        }, 0);
      }
      send() {
        setTimeout(() => {
          this.onmessage?.({
            data: JSON.stringify({
              type: "done",
              answer: { ...ANSWER, answer: "Real yield [1].", generated_by: "llm", model: "gpt-4o-mini" },
            }),
          });
        }, 0);
      }
      close() {
        this.onclose?.({ code: 1000 });
      }
    }
    vi.stubGlobal("WebSocket", TicketWS);

    render(<ChatPanel protocols={[]} />);
    askQuestion();

    expect(await screen.findByText(/Real yield \[1\]/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/auth/ticket", expect.objectContaining({ method: "POST" }));
    expect(opened[0]).toContain("?ticket=tkt-1");
    // The 1008 close triggered a second connection with a fresh ticket.
    expect(opened).toHaveLength(2);
    expect(fetchMock).not.toHaveBeenCalledWith("/api/chat", expect.anything());
  });
});

describe("prettyReply", () => {
  it("turns hyphen/asterisk bullets into • and strips markdown punctuation", () => {
    const raw = "Lead sentence.\n- first point\n* second point\nSee `scoring.py` for **weights**.";
    const out = prettyReply(raw);
    expect(out).toContain("• first point");
    expect(out).toContain("• second point");
    expect(out).not.toContain("- ");
    expect(out).not.toContain("`");
    expect(out).not.toContain("**");
    expect(out).toContain("weights");
  });
});
