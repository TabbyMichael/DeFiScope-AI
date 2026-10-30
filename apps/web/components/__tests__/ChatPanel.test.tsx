import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatPanel } from "@/components/chat/chat-panel";

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

    // Answer text + citation source + the offline badge all surface.
    expect(await screen.findByText(/Real yield is fees-backed growth/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/chat",
      expect.objectContaining({ method: "POST" }),
    );
    expect(await screen.findByText("Methodology")).toBeInTheDocument();
    expect(screen.getByText("offline · quoted evidence")).toBeInTheDocument();
  });

  it("streams tokens over the WebSocket and never calls POST", async () => {
    const fetchMock = vi.fn();
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
    expect(screen.getByText("Methodology")).toBeInTheDocument();
    expect(screen.getByText("model: gpt-4o-mini")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
