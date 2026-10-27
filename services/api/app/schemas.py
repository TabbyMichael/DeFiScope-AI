"""Pydantic response schemas for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChainShare(BaseModel):
    chain: str
    tvl: float
    share: float


class ProtocolOverview(BaseModel):
    slug: str
    name: str
    category: str | None = None
    tvl: float | None = None
    change_7d: float | None = None
    change_30d: float | None = None
    volatility_30d: float | None = None
    top_chain: str | None = None
    top_chain_share: float | None = None
    incentive_ratio: float | None = None
    risk_score: float | None = None
    risk_band: str = "unknown"
    stale_days: int | None = None
    source: str = "defillama"
    as_of: str | None = None
    sparkline: list[TvlPoint] = Field(default_factory=list)


class TvlPoint(BaseModel):
    date: str
    tvl: float


class RiskIndicatorOut(BaseModel):
    key: str
    label: str
    value: float | None
    score: float | None
    weight: float
    evidence: str
    limitation: str


class ProtocolResearch(BaseModel):
    slug: str
    name: str
    category: str | None = None
    url: str | None = None
    overview: ProtocolOverview
    tvl_series: list[TvlPoint] = Field(default_factory=list)
    chains: list[ChainShare] = Field(default_factory=list)
    risk: dict = Field(default_factory=dict)
    data_gaps: list[str] = Field(default_factory=list)
    as_of: str
    sources: list[str] = Field(default_factory=list)


class Alert(BaseModel):
    id: str
    slug: str
    protocol: str
    rule: str
    severity: str  # info | warning | critical
    message: str
    evidence: dict
    triggered_at: str


class BriefSection(BaseModel):
    executive_summary: str
    growth_drivers: list[str]
    risks: list[str]
    data_gaps: list[str]
    confidence: str
    recommendations: list[str]


class ResearchBrief(BaseModel):
    slug: str
    protocol: str
    generated_by: str  # "llm" | "template"
    markdown: str
    sections: BriefSection
    as_of: str
    sources: list[str]


class Mover(BaseModel):
    """A protocol ranked by 7d TVL change (used for top gainers/losers)."""

    slug: str
    name: str
    change_7d: float


class DashboardStats(BaseModel):
    total_tvl: float = 0.0
    protocol_count: int = 0
    by_band: dict[str, int] = Field(default_factory=dict)
    active_critical: int = 0
    active_warning: int = 0
    top_gainer: Mover | None = None
    top_loser: Mover | None = None


class DashboardResponse(BaseModel):
    """Everything the dashboard needs, sourced from the DB (latest snapshot
    per protocol + alert_records) with a live DefiLlama hydration fallback."""

    stats: DashboardStats
    protocols: list[ProtocolOverview] = Field(default_factory=list)
    alerts: list[Alert] = Field(default_factory=list)
    aggregate_history: list[TvlPoint] = Field(default_factory=list)
    as_of: str | None = None
