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
    # Economic-activity enrichment (Increment D). Null = the fees/volume host had
    # no tracked series (a data gap), never a zero or a "safe" reading.
    fees_1d: float | None = None
    fees_30d: float | None = None
    revenue_1d: float | None = None
    volume_1d: float | None = None
    fees_tvl: float | None = None
    volume_tvl: float | None = None
    # Stablecoin depeg watch (Increment E). Only populated for protocols that
    # mint a tracked USD-pegged coin; null means no tracked coin or no price
    # feed - a data gap, never a claim that everything is on peg.
    depeg_worst_bps: float | None = None
    depeg_asset: str | None = None
    risk_score: float | None = None
    risk_band: str = "unknown"
    stale_days: int | None = None
    source: str = "defillama"
    as_of: str | None = None
    sparkline: list[TvlPoint] = Field(default_factory=list)


class TvlPoint(BaseModel):
    date: str
    tvl: float


class RiskPoint(BaseModel):
    """One daily risk-score observation from ``protocol_snapshots``.

    Only rows the scheduler actually scored carry a ``score``/``band``; the
    deep DefiLlama backfill seeds TVL history without re-scoring every day, so
    those are excluded from the trend rather than plotted as zero."""

    date: str
    score: float | None = None
    band: str | None = None


class RiskIndicatorOut(BaseModel):
    key: str
    label: str
    value: float | None
    score: float | None
    weight: float
    evidence: str
    limitation: str


class RiskAssessmentOut(BaseModel):
    """Typed shape of ``scoring.RiskAssessment.to_dict()``. Declaring it here
    (rather than a bare ``dict``) makes the explainable-risk structure part of
    the OpenAPI contract so the frontend's generated types stay precise."""

    slug: str = ""
    composite_score: float | None = None
    band: str = "unknown"
    indicators: list[RiskIndicatorOut] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)


class ProtocolResearch(BaseModel):
    slug: str
    name: str
    category: str | None = None
    url: str | None = None
    overview: ProtocolOverview
    tvl_series: list[TvlPoint] = Field(default_factory=list)
    chains: list[ChainShare] = Field(default_factory=list)
    risk: RiskAssessmentOut = Field(default_factory=RiskAssessmentOut)
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


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    # When set, retrieval is scoped to that protocol's own evidence first
    # (falling back to shared methodology docs). Omit for a general question.
    protocol_slug: str | None = None


class ChatCitation(BaseModel):
    """A numbered source an answer is grounded in. ``n`` matches the [n] marker
    inline in the answer text; ``quote`` is the exact passage retrieved."""

    n: int
    source: str  # human source name (Methodology, protocol name, ...)
    location: str  # section heading within the source
    quote: str  # the cited passage (possibly truncated)


class ChatAnswer(BaseModel):
    answer: str
    citations: list[ChatCitation] = Field(default_factory=list)
    # True when the answer is backed by retrieved, cited context; False when it
    # had to report that the evidence base cannot establish an answer.
    grounded: bool
    # "llm" (model-composed), "extractive" (offline quoted passages), or
    # "none" (no supporting context found - a refusal, not a fabricated answer).
    generated_by: str
    model: str | None = None
