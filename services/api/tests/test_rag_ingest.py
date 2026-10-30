"""Ingestion tests: doc chunking from the repo docs + idempotent reindex."""

from __future__ import annotations

import httpx
from app.db import ChatChunk, SessionLocal, init_db
from app.rag.ingest import docs_chunks, reindex
from app.rag.service import RagService


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
