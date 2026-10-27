import type {
  Alert,
  ProtocolOverview,
  ProtocolResearch,
  ResearchBrief,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function get<T>(path: string, revalidate = 300): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    next: { revalidate },
  });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status} ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  protocols: () => get<ProtocolOverview[]>("/api/protocols"),
  protocol: (slug: string) => get<ProtocolResearch>(`/api/protocols/${slug}`),
  brief: (slug: string) => get<ResearchBrief>(`/api/briefs/${slug}`, 3600),
  alerts: () => get<Alert[]>("/api/alerts"),
  alertHistory: () => get<Alert[]>("/api/alerts/history"),
};

export function fmtUsd(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
  if (value >= 1e3) return `$${(value / 1e3).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
}

export function fmtPct(value: number | null | undefined, digits = 1): string {
  if (value == null) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
}
