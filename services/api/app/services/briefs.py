"""Research brief generation.

Primary path: send a structured evidence pack to an OpenAI-compatible chat
API and request JSON sections. Fallback path (no API key, or LLM failure):
a deterministic template that composes the same sections from the evidence.

The fallback guarantees the product still produces a useful, honest brief
offline - and makes the LLM's contribution auditable by comparison.
"""

from __future__ import annotations

import json
import logging

import httpx

from app.config import get_settings
from app.schemas import BriefSection, ResearchBrief
from app.services.protocols import ResearchPack

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a senior DeFi research analyst writing for a consulting engagement. "
    "Use ONLY the evidence provided in the user message; never invent numbers. "
    "Distinguish observed facts from hypotheses, state what the data cannot "
    "establish, and flag missing evidence. Be concise and concrete. "
    "Respond with JSON only."
)

USER_PROMPT_TEMPLATE = """Generate a research brief for the protocol below.

Evidence pack (as of {as_of}):
- Protocol: {name} (category: {category}), DefiLlama slug: {slug}
- Latest TVL: ${tvl:,.0f}
- TVL change: 7d {chg7}, 30d {chg30}
- 30d daily TVL volatility (std dev): {vol}
- Largest chain: {top_chain} holding {top_share} of TVL
- Staking/incentive TVL ratio: {inc}
- Composite risk score: {risk_score}/100 (band: {band})
- Risk indicators (value, score, evidence, limitation):
{indicators_json}
- Data gaps: {gaps}

Return JSON with keys:
  executive_summary (2-3 sentences, plain prose),
  growth_drivers (list of 2-4 short bullets, each grounded in the evidence),
  risks (list of 2-4 bullets referencing specific indicators),
  data_gaps (list: what this analysis CANNOT conclude and what evidence is missing),
  confidence ("high" | "medium" | "low" with a one-line justification),
  recommendations (list of 3-5 next investigative or monitoring actions an analyst
  should take, ordered by value).
"""


def _fmt(value, pct=False, dollars=False) -> str:
    if value is None:
        return "n/a"
    if pct:
        return f"{value:+.1f}%"
    if dollars:
        return f"${value:,.0f}"
    return f"{value}"


def build_evidence_context(pack: ResearchPack) -> str:
    ov = pack.risk  # scores embedded; recompute light facts from metrics consumers already stored
    from app.services.protocols import pack_to_overview

    o = pack_to_overview(pack)
    indicators = [
        {
            "label": i.label,
            "value": i.value,
            "score": i.score,
            "evidence": i.evidence,
            "limitation": i.limitation,
        }
        for i in (ov.indicators if ov else [])
    ]
    return USER_PROMPT_TEMPLATE.format(
        as_of=pack.latest_date or "unknown",
        name=pack.detail.name,
        category=o.category or "unknown",
        slug=pack.slug,
        tvl=o.tvl or 0.0,
        chg7=_fmt(o.change_7d, pct=True),
        chg30=_fmt(o.change_30d, pct=True),
        vol=_fmt(None if o.volatility_30d is None else f"{o.volatility_30d:.4f}"),
        top_chain=o.top_chain or "n/a",
        top_share=_fmt(None if o.top_chain_share is None else f"{o.top_chain_share * 100:.1f}%"),
        inc=_fmt(None if o.incentive_ratio is None else f"{o.incentive_ratio:.2f}"),
        risk_score=_fmt(o.risk_score),
        band=o.risk_band,
        indicators_json=json.dumps(indicators, indent=2),
        gaps=", ".join(ov.data_gaps if ov else []) or "none recorded",
    )


async def generate_llm_brief(pack: ResearchPack, http: httpx.AsyncClient) -> BriefSection | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_evidence_context(pack)},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    try:
        resp = await http.post(
            f"{settings.openai_base_url}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            timeout=90,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        return BriefSection(
            executive_summary=data["executive_summary"],
            growth_drivers=data["growth_drivers"],
            risks=data["risks"],
            data_gaps=data["data_gaps"],
            confidence=data["confidence"],
            recommendations=data["recommendations"],
        )
    except Exception as exc:  # noqa: BLE001 - fall back to the template
        logger.warning("LLM brief failed (%s); using template fallback", exc)
        return None


def generate_template_brief(pack: ResearchPack) -> BriefSection:
    """Deterministic, evidence-backed brief used when no LLM is configured."""
    from app.services.protocols import pack_to_overview

    o = pack_to_overview(pack)
    risk = pack.risk
    name = pack.detail.name

    drivers = []
    if o.change_7d is not None and o.change_30d is not None:
        if o.change_30d > 5 and o.change_7d > 0:
            drivers.append(
                f"TVL expanded {o.change_30d:+.1f}% over 30d and {o.change_7d:+.1f}% over 7d; "
                "sustained multi-window growth is more consistent with adoption than a one-off deposit."
            )
        elif o.change_30d > 5:
            drivers.append(
                f"30d TVL growth ({o.change_30d:+.1f}%) is not currently confirmed by 7d momentum "
                f"({o.change_7d:+.1f}%); the earlier inflow may be stabilizing or reversing."
            )
        else:
            drivers.append(
                f"No net TVL expansion over 30d ({o.change_30d:+.1f}%); recent flows are the main "
                "growth channel to investigate."
            )
    if (
        o.top_chain_share is not None
        and o.top_chain_share < 0.7
        and len(pack.detail.current_chain_tvls) > 3
    ):
        drivers.append(
            f"Deployment spans multiple chains with no single chain above "
            f"{o.top_chain_share * 100:.0f}% of TVL, widening the addressable user base."
        )
    if not drivers:
        drivers.append(
            "Evidence available from TVL data alone is insufficient to identify growth drivers; "
            "volume, fee and active-user data are required."
        )

    risks = []
    if risk:
        risky = sorted(
            [i for i in risk.indicators if i.score is not None and i.score >= 55],
            key=lambda i: -i.score,
        )
        for i in risky[:4]:
            risks.append(f"{i.label}: {i.evidence} (caveat: {i.limitation})")
    if not risks:
        risks.append(
            "No risk indicator currently scores in the elevated range on available data; "
            "this reflects data availability, not a security guarantee."
        )

    gaps = []
    if risk and risk.data_gaps:
        label_map = {
            "liquidity_concentration": "per-chain TVL breakdown",
            "tvl_volatility": "a >=5-day TVL history for volatility estimation",
            "tvl_trend": "sufficient history for 7d/30d trend windows",
            "incentive_dependence": "staking/emissions TVL series (DefiLlama does not report it for this protocol)",
            "security_posture": "audit metadata; manual audit and incident review still required",
        }
        gaps.extend(f"Missing {label_map.get(g, g)}" for g in risk.data_gaps)
    gaps.append(
        "USD TVL conflates price movement with usage; on-chain volume/fee data is needed to "
        "confirm organic activity. This brief cannot establish token-emission schedules or "
        "the proportion of mercenary capital."
    )

    confidence = (
        "medium" if risk and risk.composite_score is not None and not risk.data_gaps else "low"
    )
    confidence_line = (
        f"{confidence.capitalize()}: composite risk computable from {len(risk.indicators) - len(risk.data_gaps) if risk else 0}/5 indicators."
        if risk
        else "Low: no risk indicators computable."
    )

    recs = [
        f"Cross-check TVL trend against trading volume and fee revenue on DefiLlama and Dune for {name}.",
        "Verify incentive/emissions schedules (governance forums, tokenomics docs) to test whether recent TVL is reward-driven.",
        "Review the most recent audit reports and any post-audit contract upgrades before recommending integration.",
    ]
    if o.stale_days and o.stale_days > 1:
        recs.insert(
            0,
            f"Data freshness: latest observation is {o.stale_days}d old - re-pull before circulating conclusions.",
        )
    if risk and "incentive_dependence" in (risk.data_gaps or []):
        recs.append(
            "Source emissions data (e.g. token terminal / Dune emissions queries) - incentive dependence is unmeasured here."
        )

    summary = (
        f"{name} ({o.category or 'DeFi'}) currently holds ${(o.tvl or 0.0):,.0f} TVL "
        f"({o.change_7d if o.change_7d is not None else 'n/a'}% 7d, "
        f"{o.change_30d if o.change_30d is not None else 'n/a'}% 30d) with a composite risk score of "
        f"{o.risk_score if o.risk_score is not None else 'n/a'}/100 ({o.risk_band}). "
        "Scores are derived from public TVL data only; see data gaps before acting."
    )
    return BriefSection(
        executive_summary=summary,
        growth_drivers=drivers,
        risks=risks,
        data_gaps=gaps,
        confidence=confidence_line,
        recommendations=recs,
    )


def sections_to_markdown(
    name: str, slug: str, s: BriefSection, as_of: str, sources: list[str], generated_by: str
) -> str:
    def bullets(items: list[str]) -> str:
        return "\n".join(f"- {i}" for i in items)

    return f"""# {name} - Research Brief

*Generated by: {generated_by} analyst engine | Data as of: {as_of}*

## Executive summary

{s.executive_summary}

## Growth drivers

{bullets(s.growth_drivers)}

## Risks

{bullets(s.risks)}

## What this analysis cannot establish

{bullets(s.data_gaps)}

## Confidence

{s.confidence}

## Recommended next steps

{bullets(s.recommendations)}

---
Sources: {", ".join(sources)}
"""


async def build_brief(pack: ResearchPack, http: httpx.AsyncClient) -> ResearchBrief:
    sections = await generate_llm_brief(pack, http)
    generated_by = "llm"
    if sections is None:
        sections = generate_template_brief(pack)
        generated_by = "template"
    sources = [
        f"https://defillama.com/protocol/{pack.slug}",
        "https://api.llama.fi",
    ]
    markdown = sections_to_markdown(
        pack.detail.name, pack.slug, sections, pack.latest_date or "n/a", sources, generated_by
    )
    return ResearchBrief(
        slug=pack.slug,
        protocol=pack.detail.name,
        generated_by=generated_by,
        markdown=markdown,
        sections=sections,
        as_of=pack.latest_date or "n/a",
        sources=sources,
    )
