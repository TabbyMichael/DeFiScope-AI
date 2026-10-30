"""Offline, deterministic tests for the ask-the-analyst RAG engine (#8).

Every retrieval/answer path is exercised WITHOUT a live network: the lexical
(BM25) path needs nothing, and the LLM/embedding paths are mocked with respx.
The contract under test is the honesty guarantee: answers cite retrieved context,
and when there is no supporting context the engine refuses rather than invents.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from app.config import get_settings
from app.rag.chunking import Chunk, _make_chunk, chunk_evidence, chunk_markdown, content_hash
from app.rag.embeddings import cosine, embed_texts
from app.rag.lexical import LexicalIndex, tokenize
from app.rag.service import RagService


def chunk(text: str, *, source="Test Doc", section="Sec", slug=None, emb=None) -> Chunk:
    return Chunk(
        id=content_hash(text),
        doc_id=f"doc:{source}",
        section=section,
        text=text,
        source_type="doc" if slug is None else "evidence",
        source_name=source,
        protocol_slug=slug,
        embedding=emb,
    )


@pytest.fixture()
async def http():
    async with httpx.AsyncClient() as client:
        yield client


# --- chunking ---------------------------------------------------------------


class TestChunking:
    def test_splits_on_headings_and_keeps_section(self):
        md = (
            "# Title\n\nThis introductory paragraph is long enough to survive.\n\n"
            "## Alpha\n\nalpha body paragraph here.\n\n## Beta\n\nbeta body text value."
        )
        chunks = chunk_markdown("d", "Doc", md, chunk_size=200)
        sections = {c.section for c in chunks}
        assert "Alpha" in sections and "Beta" in sections
        # intro is attributed to the leading (title) section, not dropped.
        assert any("introductory paragraph" in c.text for c in chunks)

    def test_short_fragments_are_dropped(self):
        chunks = chunk_markdown("d", "Doc", "## Head\n\nhi", chunk_size=200)
        assert all(len(c.text) >= 20 for c in chunks)

    def test_long_section_is_packed_within_chunk_size(self):
        body = " ".join(f"word{i}" for i in range(400))
        chunks = chunk_markdown("d", "Doc", f"## Big\n\n{body}", chunk_size=200)
        assert len(chunks) > 1
        assert all(len(c.text) <= 260 for c in chunks)  # section label adds a little

    def test_content_hash_is_stable_id(self):
        a, b = chunk("identical passage text"), chunk("identical passage text")
        assert a.id == b.id

    def test_identical_text_different_source_gets_distinct_id(self):
        # Regression: identical boilerplate evidence across two protocols used to
        # hash to the same id and collide on the chat_chunks primary key. The id
        # now folds in provenance, so same text under different doc_id is distinct
        # while unchanged text in the same place stays idempotent.
        text = "Protocol does not mint a stablecoin we track; no direct peg exposure."
        common = dict(section="Peg", source_type="evidence", source_name="P", protocol_slug=None)
        a = _make_chunk(text, doc_id="protocol:alpha", **common)
        b = _make_chunk(text, doc_id="protocol:beta", **common)
        a2 = _make_chunk(text, doc_id="protocol:alpha", **common)
        assert a.id != b.id  # different source -> no primary-key collision
        assert a.id == a2.id  # same source + text -> stable id (idempotent)


class TestEvidenceChunking:
    def test_indicator_limitation_is_preserved_verbatim(self):
        chunks = chunk_evidence(
            "aave-v3",
            "Aave V3",
            overview_lines=["TVL $10,000,000,000"],
            indicators=[
                {
                    "label": "Liquidity concentration",
                    "value": 0.65,
                    "score": 50,
                    "evidence": "Ethereum holds 65% of TVL",
                    "limitation": "Does not see bridge-mediated liquidity",
                }
            ],
            data_gaps=["no emissions schedule"],
            recent_alerts=["warning: TVL fell"],
        )
        joined = "\n".join(c.text for c in chunks)
        assert "Does not see bridge-mediated liquidity" in joined
        assert all(c.protocol_slug == "aave-v3" for c in chunks)
        assert any("cannot establish" in c.text for c in chunks)  # data gaps framed honestly


# --- lexical ----------------------------------------------------------------


class TestLexical:
    def test_bm25_ranks_relevant_doc_first(self):
        docs = [
            ("peg", tokenize("the stablecoin lost its peg and deviated from one dollar")),
            ("yield", tokenize("real yield depends on fees rather than token emissions")),
            ("noise", tokenize("a generic unrelated sentence about weather today")),
        ]
        idx = LexicalIndex(docs)
        top = idx.search("stablecoin peg deviation", top_k=2)
        assert top and top[0][0] == "peg"

    def test_no_overlap_scores_zero(self):
        idx = LexicalIndex([("a", tokenize("alpha beta gamma"))])
        assert idx.search("delta epsilon", top_k=3) == []

    def test_cosine_and_embeddings(self):
        assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
        assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)
        assert cosine([], []) == 0.0

    async def test_embed_texts_no_key_returns_none(self, http):
        s = get_settings()
        s_cache = s.openai_api_key
        s.openai_api_key = None
        try:
            assert await embed_texts(["hello"], http) is None
        finally:
            s.openai_api_key = s_cache


# --- service: offline extractive + guardrail ----------------------------------


class TestAnswerOffline:
    async def test_extractive_answer_is_grounded_and_cited(self, http, monkeypatch):
        s = get_settings()
        monkeypatch.setattr(s, "openai_api_key", None, raising=False)
        svc = RagService()
        svc.index(
            [
                chunk(
                    "The composite risk score is a weighted mean of the available indicators.",
                    source="Methodology",
                    section="Composite score",
                ),
                chunk(
                    "Missing data is surfaced as a data gap and never treated as safe.",
                    source="Methodology",
                    section="Data gaps",
                ),
            ]
        )
        ans = await svc.answer("how is the composite risk score computed", http)
        assert ans.generated_by == "extractive"
        assert ans.grounded is True
        assert ans.citations and ans.citations[0].source == "Methodology"
        assert "weighted mean" in ans.answer

    async def test_guardrail_refuses_when_nothing_supports(self, http, monkeypatch):
        s = get_settings()
        monkeypatch.setattr(s, "openai_api_key", None, raising=False)
        svc = RagService()
        svc.index([chunk("TVL measures total value locked in a protocol's smart contracts.")])
        ans = await svc.answer("what is the capital of france", http)
        assert ans.grounded is False
        assert ans.generated_by == "none"
        assert ans.citations == []

    async def test_lexical_gate_refuses_on_one_stray_common_word(self, http, monkeypatch):
        # Regression: BM25 scores are unbounded, so the old fixed 0.5 floor let an
        # off-topic query qualify purely because a common word ("like") appeared in
        # a passage. The lexical gate now requires shared *informative* terms.
        s = get_settings()
        monkeypatch.setattr(s, "openai_api_key", None, raising=False)
        monkeypatch.setattr(s, "rag_min_query_term_overlap", 2, raising=False)
        svc = RagService()
        svc.index(
            [
                chunk(
                    "DeFiScope reads leverage like a slow credit cycle, compounding quietly.",
                    source="Methodology",
                    section="Primer",
                ),
                chunk(
                    "The composite risk score is a weighted mean of the indicators.",
                    source="Methodology",
                    section="Score",
                ),
            ]
        )
        # Only "like" overlaps -> not enough; must refuse rather than quote noise.
        off = await svc.answer("what is the weather like in Paris tomorrow", http)
        assert off.generated_by == "none"
        assert off.grounded is False
        # A genuinely on-topic multi-term query still answers, grounded.
        on = await svc.answer("how is the composite risk score computed", http)
        assert on.generated_by == "extractive"
        assert on.grounded is True

    async def test_empty_index_refuses(self, http):
        svc = RagService()
        ans = await svc.answer("anything at all", http)
        assert ans.grounded is False and ans.generated_by == "none"

    async def test_protocol_scope_limits_retrieval(self, http, monkeypatch):
        s = get_settings()
        monkeypatch.setattr(s, "openai_api_key", None, raising=False)
        svc = RagService()
        svc.index(
            [
                chunk("Aave exposes liquidation risk on Ethereum.", source="Aave", slug="aave"),
                chunk("Uniswap is an automated market maker.", source="Uniswap", slug="uniswap"),
                chunk("General methodology note about risk bands and scoring.", source="Method"),
            ]
        )
        ans = await svc.answer("liquidation risk on ethereum", http, protocol_slug="aave")
        sources = {c.source for c in ans.citations}
        assert "Uniswap" not in sources  # other protocol's evidence excluded


# --- service: LLM path (respx) ----------------------------------------------


class TestAnswerLLM:
    async def test_llm_composes_cited_answer(self, http, monkeypatch):
        s = get_settings()
        monkeypatch.setattr(s, "openai_api_key", "sk-test", raising=False)
        monkeypatch.setattr(s, "openai_base_url", "https://api.test/v1", raising=False)
        svc = RagService()
        svc.index([chunk("Real yield is the share of TVL growth backed by fees, not emissions.")])
        with respx.mock(base_url="https://api.test/v1") as rsp:
            rsp.post("/chat/completions").respond(
                200,
                json={
                    "choices": [
                        {"message": {"content": "Real yield means fees-backed growth [1]."}}
                    ]
                },
            )
            ans = await svc.answer("real yield fees backed growth", http)
        assert ans.generated_by == "llm"
        assert ans.grounded is True
        assert ans.model == s.openai_model
        assert ans.answer.startswith("Real yield")
        assert ans.citations[0].n == 1

    async def test_llm_request_carries_style_and_grounding(self, http, monkeypatch):
        s = get_settings()
        monkeypatch.setattr(s, "openai_api_key", "sk-test", raising=False)
        monkeypatch.setattr(s, "openai_base_url", "https://api.test/v1", raising=False)
        monkeypatch.setattr(s, "rag_max_tokens", 1234, raising=False)
        monkeypatch.setattr(s, "rag_temperature", 0.42, raising=False)
        svc = RagService()
        svc.index([chunk("Real yield is the share of TVL growth backed by fees, not emissions.")])
        with respx.mock(base_url="https://api.test/v1") as rsp:
            route = rsp.post("/chat/completions").respond(
                200, json={"choices": [{"message": {"content": "ok [1]"}}]}
            )
            await svc.answer("real yield fees backed growth", http)
        body = json.loads(route.calls.last.request.content)
        # Engaging/long generation is unlocked via style knobs, not prompt restraint.
        assert body["max_tokens"] == 1234
        assert body["temperature"] == 0.42
        # ...while the honesty guardrail stays baked into the system prompt.
        system = body["messages"][0]["content"]
        assert "ONLY from the numbered context" in system
        assert "Never invent numbers" in system

    async def test_llm_failure_degrades_to_extractive(self, http, monkeypatch):
        s = get_settings()
        monkeypatch.setattr(s, "openai_api_key", "sk-test", raising=False)
        monkeypatch.setattr(s, "openai_base_url", "https://api.test/v1", raising=False)
        svc = RagService()
        svc.index([chunk("Real yield is fees-backed TVL growth, distinct from emissions.")])
        with respx.mock(base_url="https://api.test/v1") as rsp:
            rsp.post("/chat/completions").respond(500, json={"error": "boom"})
            ans = await svc.answer("real yield fees backed growth", http)
        assert ans.generated_by == "extractive"
        assert ans.grounded is True

    async def test_stream_yields_token_citations_and_done(self, http, monkeypatch):
        s = get_settings()
        monkeypatch.setattr(s, "openai_api_key", None, raising=False)
        svc = RagService()
        svc.index([chunk("The depeg watch flags stablecoins drifting from their one dollar peg.")])
        frames = [
            f async for f in svc.answer_stream("what does the depeg watch flag stablecoins", http)
        ]
        types = [f["type"] for f in frames]
        assert "citations" in types and types[-1] == "done"
        assert frames[-1]["answer"]["grounded"] is True


# --- service: vector ranking path -------------------------------------------


class TestVectorRetrieval:
    async def test_uses_cosine_when_embeddings_present(self, http, monkeypatch):
        s = get_settings()
        monkeypatch.setattr(s, "openai_api_key", "sk-test", raising=False)
        monkeypatch.setattr(s, "openai_base_url", "https://api.test/v1", raising=False)
        svc = RagService()
        # Two chunks with orthogonal-ish embeddings; query maps to the second.
        svc.index(
            [
                chunk("alpha about pegs", emb=[1.0, 0.0, 0.0]),
                chunk("beta about fees", emb=[0.0, 1.0, 0.0]),
            ]
        )
        with respx.mock(base_url="https://api.test/v1") as rsp:
            rsp.post("/embeddings").respond(
                200, json={"data": [{"index": 0, "embedding": [0.0, 1.0, 0.0]}]}
            )
            scored, used_vectors = await svc.retrieve("which is about fees", http)
        assert used_vectors is True
        assert scored[0][0].text.startswith("beta")
