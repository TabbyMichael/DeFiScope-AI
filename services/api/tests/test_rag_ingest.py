"""Ingestion tests: doc chunking from the repo docs + idempotent reindex."""

from __future__ import annotations

import httpx
from app.analysis import metrics
from app.clients.defillama import ProtocolDetail
from app.db import ChatChunk, SessionLocal, init_db
from app.rag.ingest import _overview_lines, chunks_from_pack, docs_chunks, reindex
from app.rag.service import RagService
from app.services import onchain as onchain_service
from app.services.protocols import ResearchPack


def make_pack(activity: onchain_service.OnchainActivity | None = None) -> ResearchPack:
    """A pack with no DefiLlama data at all - only the on-chain block matters."""
    detail = ProtocolDetail(
        slug="aave-v3",
        name="Aave",
        current_chain_tvls={},
        tvl_history=[],
        staking_history=[],
        borrowed_history=[],
    )
    return ResearchPack(
        summary=None,
        detail=detail,
        tvl_df=metrics.series_to_frame([]),  # empty, not None: metrics expect a frame
        onchain=activity,
    )


class TestOnchainEvidence:
    """Second-provider numbers reach the corpus - and only when measured."""

    def test_ok_activity_adds_the_numbers_and_their_scope(self):
        pack = make_pack(
            onchain_service.OnchainActivity(
                status="ok",
                as_of="2026-10-29",
                chains=["ethereum"],
                active_wallets=1234,
                tx_count=9876,
                tx_volume_usd=45678901.0,
                returning_wallets=470,
                returning_wallet_share=0.381,
            )
        )
        lines = _overview_lines(pack)
        measured = [line for line in lines if line.startswith("on-chain")]
        assert len(measured) == 2
        assert "2026-10-29" in measured[0]
        assert "1,234 active wallets" in measured[0]
        assert "9,876 transactions" in measured[0]
        assert "$45,678,901 transfer volume" in measured[0]
        assert "470 returning wallets (38% of active)" in measured[0]
        # The caveat travels with the number so a quote cannot drop it.
        assert "contract-level" in measured[1]
        assert "not an input to the risk score" in measured[1]

    def test_partial_activity_still_speaks_for_the_chains_that_reported(self):
        pack = make_pack(
            onchain_service.OnchainActivity(
                status="partial",
                as_of="2026-10-29",
                chains=["ethereum"],
                missing_chains=["bsc"],
                tx_count=42,
            )
        )
        lines = _overview_lines(pack)
        assert any("42 transactions" in line for line in lines)
        # A missing metric is omitted, never rendered as 0.
        assert not any("0 active wallets" in line for line in lines)

    def test_unconfigured_or_empty_adds_nothing(self):
        for activity in (
            None,
            onchain_service.OnchainActivity(status="unconfigured", note="no key"),
            onchain_service.OnchainActivity(status="no_data", note="no mapping"),
            onchain_service.OnchainActivity(status="stale", as_of="2020-01-01"),
        ):
            lines = _overview_lines(make_pack(activity))
            assert not [line for line in lines if "on-chain" in line]

    def test_chunks_carry_the_activity_and_stay_idempotent(self):
        activity = onchain_service.OnchainActivity(
            status="ok", as_of="2026-10-29", chains=["ethereum"], active_wallets=12
        )
        first = chunks_from_pack(make_pack(activity), [])
        second = chunks_from_pack(make_pack(activity), [])
        assert any("12 active wallets" in c.text for c in first)
        # Content-hashed ids: identical evidence must not duplicate on re-ingest.
        assert [c.id for c in first] == [c.id for c in second]

    async def test_ingest_threads_the_session_so_activity_is_visible(self, monkeypatch):
        from app.rag import ingest

        seen: dict = {}

        class StubService:
            async def get_pack(self, slug, http, session=None):
                seen["session"] = session
                return make_pack(
                    onchain_service.OnchainActivity(
                        status="ok",
                        as_of="2026-10-29",
                        chains=["ethereum"],
                        active_wallets=7,
                    )
                )

        monkeypatch.setattr(ingest, "_tracked_slugs", lambda session: ["aave-v3"])
        init_db()
        db = SessionLocal()
        try:
            chunks = await ingest.build_chunks(db, StubService(), None)
        finally:
            db.close()
        # Only run_monitor calls Dune; ingest can see the numbers only through
        # the session, so passing it here is what makes the evidence reachable.
        assert seen["session"] is db
        assert any("7 active wallets" in c.text for c in chunks)


class TestDocsIngest:
    def test_reads_repo_docs_into_citable_chunks(self):
        chunks = docs_chunks()
        assert chunks, "expected the repo docs/ to produce chunks"
        # methodology.md is always indexed and must surface under its label.
        assert any(c.source_name == "Methodology" for c in chunks)
        assert all(c.source_type == "doc" for c in chunks)
        assert all(len(c.text) >= 20 for c in chunks)

    async def test_reindex_is_idempotent_and_loads_service(self):
        init_db()
        svc = RagService()
        async with httpx.AsyncClient() as http:
            session = SessionLocal()
            try:
                first = await reindex(session, None, http, svc)  # no tracked slugs -> docs only
                rows_after_first = session.query(ChatChunk).count()
                second = await reindex(session, None, http, svc)
                rows_after_second = session.query(ChatChunk).count()
            finally:
                session.close()
        assert first > 0
        assert svc.count == first
        # content-hash ids mean a re-run neither duplicates nor grows the table.
        assert second == first
        assert rows_after_second == rows_after_first

    async def test_rag_disabled_skips_ingest(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "rag_enabled", False, raising=False)
        svc = RagService()
        async with httpx.AsyncClient() as http:
            session = SessionLocal()
            try:
                assert await reindex(session, None, http, svc) == 0
            finally:
                session.close()
        assert svc.count == 0
