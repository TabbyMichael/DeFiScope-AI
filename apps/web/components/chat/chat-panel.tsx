"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { API_WS_URL } from "@/lib/api";
import type { ChatAnswer, ChatCitation } from "@/lib/types";

type Role = "user" | "assistant";

interface Message {
  id: number;
  role: Role;
  content: string;
  citations?: ChatCitation[];
  grounded?: boolean;
  generatedBy?: string;
  model?: string | null;
  streaming?: boolean;
}

interface Frame {
  type?: string;
  text?: string;
  citations?: ChatCitation[];
  answer?: ChatAnswer;
}

const EXAMPLES = [
  "How is the composite risk score calculated?",
  "What does the stablecoin depeg indicator actually measure?",
  "What can this analysis NOT establish about a protocol?",
];

// If the socket never opens this fast, assume WS is blocked and fall back.
const OPEN_TIMEOUT_MS = 6000;

/**
 * Ask a question, preferring the streaming WS and auto-falling back to the
 * same-origin POST proxy. Returns a cancel function. Kept as a plain helper (not
 * a hook) so the component owns the transcript state and the fallback logic is
 * unit-testable in isolation.
 */
export function streamAsk(
  question: string,
  protocolSlug: string | null,
  cb: {
    onToken: (t: string) => void;
    onCitations: (cs: ChatCitation[]) => void;
    onComplete: (answer: ChatAnswer, replaceContent: boolean) => void;
    onError: (message: string) => void;
  },
): () => void {
  let settled = false;
  let ws: WebSocket | null = null;

  const fallbackToPost = () => {
    if (settled) return;
    settled = true;
    fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, protocol_slug: protocolSlug }),
    })
      .then((r) => (r.ok ? (r.json() as Promise<ChatAnswer>) : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((answer) => cb.onComplete(answer, true))
      .catch((e: unknown) => cb.onError(e instanceof Error ? e.message : String(e)));
  };

  // No WebSocket in the environment (SSR, some locked-down browsers, jsdom):
  // go straight to the POST fallback.
  if (typeof WebSocket === "undefined") {
    fallbackToPost();
    return () => {};
  }

  try {
    ws = new WebSocket(`${API_WS_URL}/ws/chat`);
  } catch {
    fallbackToPost();
    return () => {};
  }

  // If the socket never opens this fast, assume WS is blocked and fall back.
  const openTimer = setTimeout(() => {
    if (!settled && ws && ws.readyState !== WebSocket.OPEN) {
      try {
        ws.close();
      } catch {
        /* ignore */
      }
      fallbackToPost();
    }
  }, OPEN_TIMEOUT_MS);

  ws.onopen = () => ws?.send(JSON.stringify({ question, protocol_slug: protocolSlug }));
  ws.onerror = () => {
    clearTimeout(openTimer);
    if (!settled) fallbackToPost();
  };
  ws.onclose = () => {
    clearTimeout(openTimer);
    // Closed before a `done` frame arrived -> the stream was cut; degrade.
    if (!settled) fallbackToPost();
  };
  ws.onmessage = (ev: MessageEvent) => {
    let frame: Frame;
    try {
      frame = JSON.parse(String(ev.data)) as Frame;
    } catch {
      return;
    }
    if (frame.type === "token" && frame.text) {
      cb.onToken(frame.text);
    } else if (frame.type === "citations" && frame.citations) {
      cb.onCitations(frame.citations);
    } else if (frame.type === "done" && frame.answer) {
      settled = true;
      clearTimeout(openTimer);
      cb.onComplete(frame.answer, false);
      try {
        ws?.close();
      } catch {
        /* ignore */
      }
    } else if (frame.type === "error") {
      if (!settled) fallbackToPost();
    }
    // "ping" frames are liveness noise; ignored.
  };

  return () => {
    settled = true;
    clearTimeout(openTimer);
    try {
      ws?.close();
    } catch {
      /* ignore */
    }
  };
}

function GeneratedBadge({ msg }: { msg: Message }) {
  if (msg.generatedBy === "llm") {
    return <Badge variant="secondary">model: {msg.model ?? "LLM"}</Badge>;
  }
  if (msg.generatedBy === "extractive") {
    return (
      <Badge variant="secondary" className="bg-amber-500/15 text-amber-600 dark:text-amber-400">
        offline · quoted evidence
      </Badge>
    );
  }
  if (msg.generatedBy === "none") {
    return <Badge variant="outline">no supporting evidence</Badge>;
  }
  return null;
}

function CitationList({ citations }: { citations: ChatCitation[] }) {
  if (!citations.length) return null;
  return (
    <div className="mt-3 space-y-1.5 border-t pt-3">
      <p className="text-xs font-medium text-muted-foreground">Sources</p>
      {citations.map((c) => (
        <div key={c.n} className="text-xs leading-relaxed">
          <span className="mr-1 font-semibold text-emerald-600 dark:text-emerald-400">[{c.n}]</span>
          <span className="font-medium">{c.source}</span>
          {c.location ? <span className="text-muted-foreground"> · {c.location}</span> : null}
          <p className="mt-0.5 pl-5 text-muted-foreground">{c.quote}</p>
        </div>
      ))}
    </div>
  );
}

export function ChatPanel({
  protocols,
  initialProtocol,
}: {
  protocols: { slug: string; name: string }[];
  initialProtocol?: string | null;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [slug, setSlug] = useState<string>(initialProtocol ?? "");
  const [busy, setBusy] = useState(false);
  const idRef = useRef(0);
  const cancelRef = useRef<(() => void) | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // jsdom (tests) and some environments lack Element.scrollTo — guard it.
    scrollRef.current?.scrollTo?.({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const update = useCallback((id: number, patch: (m: Message) => Message) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? patch(m) : m)));
  }, []);

  const ask = useCallback(
    (raw: string) => {
      const question = raw.trim();
      if (!question || busy) return;
      const userId = ++idRef.current;
      const aid = ++idRef.current;
      setMessages((prev) => [
        ...prev,
        { id: userId, role: "user", content: question },
        { id: aid, role: "assistant", content: "", streaming: true },
      ]);
      setInput("");
      setBusy(true);
      cancelRef.current = streamAsk(question, slug || null, {
        onToken: (t) => update(aid, (m) => ({ ...m, content: m.content + t })),
        onCitations: (cs) => update(aid, (m) => ({ ...m, citations: cs })),
        onComplete: (answer, replace) =>
          update(aid, (m) => ({
            ...m,
            content: replace ? answer.answer : m.content || answer.answer,
            grounded: answer.grounded,
            generatedBy: answer.generated_by,
            model: answer.model,
            citations: m.citations?.length ? m.citations : answer.citations,
            streaming: false,
          })),
        onError: (msg) =>
          update(aid, (m) => ({
            ...m,
            content: `I could not reach the analyst (${msg}). The monitoring data is unaffected - try again shortly.`,
            streaming: false,
          })),
      });
      setBusy(false);
    },
    [busy, slug, update],
  );

  return (
    <div className="flex h-full flex-col gap-4">
      <Card>
        <CardContent className="flex items-start gap-3 pt-6 text-sm text-muted-foreground">
          <span className="mt-0.5 inline-block size-2 shrink-0 rounded-full bg-emerald-500" />
          <p>
            Answers are grounded in DeFiScope&apos;s own evidence — methodology docs and each
            protocol&apos;s indicators, data gaps and alerts. Every claim cites a numbered source, and
            when the data can&apos;t establish something, it says so rather than guessing.
          </p>
        </CardContent>
      </Card>

      <div
        ref={scrollRef}
        className="min-h-[240px] flex-1 space-y-4 overflow-y-auto rounded-lg border bg-card p-4"
      >
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <p className="text-sm text-muted-foreground">Ask about a protocol or how the scores work.</p>
            <div className="flex flex-wrap justify-center gap-2">
              {EXAMPLES.map((ex) => (
                <Button key={ex} variant="outline" size="sm" onClick={() => ask(ex)}>
                  {ex}
                </Button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={m.role === "user" ? "flex justify-end" : "flex"}>
            <div
              className={
                m.role === "user"
                  ? "max-w-[85%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground"
                  : "max-w-[92%] rounded-lg border bg-muted/40 px-3 py-2 text-sm"
              }
            >
              {m.role === "assistant" && (m.generatedBy || m.grounded === false) && (
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <GeneratedBadge msg={m} />
                  {m.streaming && <span className="text-xs text-muted-foreground">thinking…</span>}
                </div>
              )}
              <p className="whitespace-pre-wrap leading-relaxed">
                {m.content}
                {m.streaming && !m.content ? (
                  <span className="text-muted-foreground">retrieving evidence…</span>
                ) : null}
              </p>
              {m.citations && m.citations.length > 0 && <CitationList citations={m.citations} />}
            </div>
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-2">
        {protocols.length > 0 && (
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            Scope to a protocol
            <select
              className="rounded-md border bg-background px-2 py-1 text-xs text-foreground"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
            >
              <option value="">General (methodology + all tracked)</option>
              {protocols.map((p) => (
                <option key={p.slug} value={p.slug}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                ask(input);
              }
            }}
            rows={2}
            placeholder="e.g. Why is Lido flagged for chain concentration?"
            className="flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus:ring-1 focus:ring-ring"
          />
          <Button onClick={() => ask(input)} disabled={busy || !input.trim()} className="self-stretch">
            Ask
          </Button>
        </div>
      </div>
    </div>
  );
}
