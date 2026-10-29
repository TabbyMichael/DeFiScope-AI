"""Tests for the explainable risk scorer."""

import time

from app.analysis import metrics, scoring

DAY = 86_400


def daily_series(values: list[float]) -> list[tuple[int, float]]:
    now = int(time.time())
    n = len(values)
    return [(now - (n - 1 - i) * DAY, v) for i, v in enumerate(values)]


def make_assessment(
    tvl_values: list[float],
    chain_tvls: dict[str, float],
    staking_values: list[float] | None = None,
    slug: str = "test-protocol",
    audits: str | None = "2",
) -> scoring.RiskAssessment:
    tvl_history = daily_series(tvl_values)
    df = metrics.series_to_frame(tvl_history)
    return scoring.assess(
        slug=slug,
        tvl_df=df,
        chain_tvls=chain_tvls,
        tvl_history=tvl_history,
        staking_history=daily_series(staking_values) if staking_values else [],
        audits=audits,
    )


class TestSteadyProtocol:
    def test_stable_diversified_protocol_scores_low(self):
        result = make_assessment(
            tvl_values=[1000 + (i % 2) for i in range(60)],
            chain_tvls={"Ethereum": 500.0, "Arbitrum": 300.0, "Optimism": 200.0},
            staking_values=[10] * 60,
        )
        assert result.band == "low"
        assert result.composite_score is not None
        assert result.composite_score < 30

    def test_every_indicator_carries_evidence_and_limitation(self):
        result = make_assessment(
            tvl_values=[1000 + (i % 2) for i in range(60)],
            chain_tvls={"Ethereum": 500.0, "Arbitrum": 500.0},
            staking_values=[10] * 60,
        )
        for ind in result.indicators:
            assert ind.evidence, f"{ind.key} missing evidence"
            assert ind.limitation, f"{ind.key} missing limitation"


class TestRiskyProtocol:
    def test_collapsing_single_chain_heavily_staked_scores_high(self):
        # steady then -40% collapse over 30 days, one chain, huge staking ratio
        values = [1000.0] * 40 + [1000.0 * (1 - 0.4 * i / 20) for i in range(20)]
        result = make_assessment(
            tvl_values=values,
            chain_tvls={"Somechain": 600.0},
            staking_values=[900.0] * 60,
            audits="0",
        )
        assert result.composite_score is not None
        assert result.band in ("elevated", "high")
        by_key = {i.key: i for i in result.indicators}
        assert by_key["tvl_trend"].score > 70
        assert by_key["liquidity_concentration"].score > 80
        assert by_key["incentive_dependence"].score > 80

    def test_exploit_note_lifts_security_score(self):
        benign = make_assessment([1000] * 60, {"Ethereum": 100.0}, slug="aave-v3")
        hacked = make_assessment([1000] * 60, {"Ethereum": 100.0}, slug="curve-dex")
        b = {i.key: i for i in benign.indicators}["security_posture"].score
        h = {i.key: i for i in hacked.indicators}["security_posture"].score
        assert h > b


class TestMissingData:
    def test_short_history_produces_gaps_not_fake_scores(self):
        result = make_assessment([1000, 1010], {"Ethereum": 100.0})
        assert "tvl_volatility" in result.data_gaps
        assert "tvl_trend" in result.data_gaps
        # composite still computable from concentration + security, and reflects that
        scored = [i for i in result.indicators if i.score is not None]
        assert len(scored) == len(result.indicators) - len(result.data_gaps)

    def test_no_chain_data(self):
        result = make_assessment([1000] * 60, {})
        conc = {i.key: i for i in result.indicators}["liquidity_concentration"]
        assert conc.score is None
        assert "liquidity_concentration" in result.data_gaps

    def test_all_missing_yields_unknown_band(self):
        result = scoring.assess(
            slug="empty",
            tvl_df=metrics.series_to_frame([]),
            chain_tvls={},
            tvl_history=[],
            staking_history=[],
            audits=None,
        )
        assert result.band == "unknown"
        assert result.composite_score is None


class TestScoreMapping:
    def test_linear_score_clamps(self):
        assert scoring._linear_score(-1, 0, 1) == 0.0
        assert scoring._linear_score(5, 0, 1) == 100.0
        # inverted direction: safe_at > risky_at
        assert scoring._linear_score(100, 100, 0) == 0.0
        assert scoring._linear_score(0, 100, 0) == 100.0
