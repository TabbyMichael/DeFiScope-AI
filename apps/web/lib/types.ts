// Mirrors services/api/app/schemas.py — keep in sync.

export interface TvlPoint {
  date: string;
  tvl: number;
}

export interface ProtocolOverview {
  slug: string;
  name: string;
  category: string | null;
  tvl: number | null;
  change_7d: number | null;
  change_30d: number | null;
  volatility_30d: number | null;
  top_chain: string | null;
  top_chain_share: number | null;
  incentive_ratio: number | null;
  risk_score: number | null;
  risk_band: "low" | "moderate" | "elevated" | "high" | "unknown";
  stale_days: number | null;
  source: string;
  as_of: string | null;
  sparkline: TvlPoint[];
}

export interface ChainShare {
  chain: string;
  tvl: number;
  share: number;
}

export interface RiskIndicator {
  key: string;
  label: string;
  value: number | null;
  score: number | null;
  weight: number;
  evidence: string;
  limitation: string;
}

export interface RiskAssessment {
  slug: string;
  composite_score: number | null;
  band: string;
  indicators: RiskIndicator[];
  data_gaps: string[];
}

export interface ProtocolResearch {
  slug: string;
  name: string;
  category: string | null;
  url: string | null;
  overview: ProtocolOverview;
  tvl_series: TvlPoint[];
  chains: ChainShare[];
  risk: RiskAssessment;
  data_gaps: string[];
  as_of: string;
  sources: string[];
}

export interface Alert {
  id: string;
  slug: string;
  protocol: string;
  rule: string;
  severity: "info" | "warning" | "critical";
  message: string;
  evidence: Record<string, unknown>;
  triggered_at: string;
}

export interface BriefSections {
  executive_summary: string;
  growth_drivers: string[];
  risks: string[];
  data_gaps: string[];
  confidence: string;
  recommendations: string[];
}

export interface ResearchBrief {
  slug: string;
  protocol: string;
  generated_by: "llm" | "template";
  markdown: string;
  sections: BriefSections;
  as_of: string;
  sources: string[];
}

export interface Mover {
  slug: string;
  name: string;
  change_7d: number;
}

export interface DashboardStats {
  total_tvl: number;
  protocol_count: number;
  by_band: Record<string, number>;
  active_critical: number;
  active_warning: number;
  top_gainer: Mover | null;
  top_loser: Mover | null;
}

export interface DashboardResponse {
  stats: DashboardStats;
  protocols: ProtocolOverview[];
  alerts: Alert[];
  aggregate_history: TvlPoint[];
  as_of: string | null;
}
