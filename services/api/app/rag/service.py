"""The ask-the-analyst retrieval + grounding engine.

One request flow, three honest outcomes:
1. **No supporting context** (nothing retrieved above the relevance floor) ->
   a refusal that says what it cannot establish. ``generated_by="none"``,
   ``grounded=False``. Never a fabricated answer.
2. **No API key** -> an *extractive* answer composed from the quoted retrieved
   passages. Every claim carries an [n] citation. ``generated_by="extractive"``.
3. **Key configured** -> the model composes prose ONLY from the numbered
   context (system prompt forbids outside knowledge), same citations.
   ``generated_by="llm"``.

Retrieval itself also degrades cleanly: OpenAI embeddings + cosine when a key
is present, deterministic BM25 otherwise. The two produce incomparable scores
(cosine in [0,1], BM25 unbounded), so the relevance gate is method-aware: a fixed
cosine floor for the vector path, a shared-informative-term bar for the lexical
path. Either way "did we find anything real?" is what the guardrail keys off.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

import httpx

from app.config import get_settings
from app.db import ChatChunk
from app.rag.chunking import Chunk
from app.rag.embeddings import cosine, embed_texts
from app.rag.lexical import LexicalIndex, tokenize
from app.schemas import ChatAnswer, ChatCitation

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are the DeFiScope analyst. Answer ONLY from the numbered context blocks "
    "in the user message. Write a clear, engaging, well-structured explanation that "
    "a curious analyst would enjoy reading - open with the direct answer, then walk "
    "through the reasoning in a few short paragraphs, and close with anything the "
    "data cannot establish. Attribute every factual claim to its source with the "
    "bracketed number, e.g. [2]. If the context does not support part of the answer, "
    "say plainly what cannot be established and what evidence is missing rather than "
    "filling the gap. Never invent numbers, never use knowledge outside the context, "
    "and never present a hypothesis as a verified fact - being engaging must never "
    "come at the cost of honesty."
)

_MAX_QUOTE = 280


def _quote(text: str) -> str:
    return text if len(text) <= _MAX_QUOTE else text[:_MAX_QUOTE].rstrip() + "…"


class RagService:
    """Holds the in-memory chunk index and answers grounded questions.

    The chunk store (``self._chunks``) is the single source of truth for
    citations. Vectors, when present, accelerate ranking; their absence just
    routes to BM25. Nothing here touches the network except the explicit,
    best-effort OpenAI calls - so an offline instance is fully functional."""

    def __init__(self) -> None:
        self._chunks: dict[str, Chunk] = {}
        self._lex: LexicalIndex | None = None

    # -- index management ----------------------------------------------------

    def index(self, chunks: list[Chunk]) -> None:
        self._chunks = {c.id: c for c in chunks}
        self._lex = None  # rebuild lazily on next retrieve

    def load_rows(self, rows: list[ChatChunk]) -> None:
        self.index(
            [
                Chunk(
                    id=r.chunk_id,
                    doc_id=r.doc_id,
                    section=r.section or "",
                    text=r.text,
                    source_type=r.source_type or "doc",
                    source_name=r.source_name or r.doc_id,
                    protocol_slug=r.protocol_slug,
                    embedding=list(r.embedding) if r.embedding else None,
                )
                for r in rows
            ]
        )

    @property
    def count(self) -> int:
        return len(self._chunks)

    @property
    def _vectors_ready(self) -> bool:
        return bool(self._chunks) and all(c.embedding for c in self._chunks.values())

    # -- retrieval -----------------------------------------------------------

    def _pool(
        self, protocol_slug: str | None, visible_slugs: set[str] | None = None
    ) -> list[Chunk]:
        if protocol_slug:
            # Protocol-scoped: its own evidence plus the shared methodology docs.
            pool = [
                c
                for c in self._chunks.values()
                if c.protocol_slug == protocol_slug or c.source_type == "doc"
            ]
        else:
            pool = list(self._chunks.values())
        if visible_slugs is not None:
            # Retrieval obeys the same data scope as the board. A subject limited
            # to two categories must not receive a quote - or a citation proving
            # existence - from a protocol they cannot open, so out-of-scope
            # evidence is removed from the pool *before* ranking rather than
            # filtered out afterwards (a removed passage cannot leak through a
            # citation number or a model paraphrase).
            pool = [c for c in pool if c.protocol_slug is None or c.protocol_slug in visible_slugs]
        return pool

    async def retrieve(
        self,
        query: str,
        http: httpx.AsyncClient,
        *,
        protocol_slug: str | None = None,
        visible_slugs: set[str] | None = None,
    ) -> tuple[list[tuple[Chunk, float]], bool]:
        """Return the top chunks with scores, and whether they came from the
        vector path. The flag matters because cosine (``[0, 1]``) and BM25
        (unbounded) scores aren't comparable, so the relevance gate differs."""
        settings = get_settings()
        pool = self._pool(protocol_slug, visible_slugs)
        if not pool:
            return [], False

        scored: list[tuple[Chunk, float]] = []
        used_vectors = False
        if self._vectors_ready:
            qvec = await embed_texts([query], http)
            if qvec:
                scored = [(c, cosine(qvec[0], c.embedding or [])) for c in pool]
                used_vectors = bool(scored)
        if not scored or all(s <= 0 for _, s in scored):
            # No vectors (offline) or an embedding miss: fall back to lexical.
            used_vectors = False
            if self._lex is None:
                self._lex = LexicalIndex([(c.id, tokenize(c.text)) for c in self._chunks.values()])
            by_id = {c.id: c for c in pool}
            pool_ids = set(by_id)
            scored = [
                (by_id[doc_id], score)
                for doc_id, score in self._lex.search(query, settings.rag_top_k * 3)
                if doc_id in pool_ids
            ]

        scored.sort(key=lambda cs: cs[1], reverse=True)
        return scored[: settings.rag_top_k], used_vectors

    def _supporting(
        self, question: str, scored: list[tuple[Chunk, float]], used_vectors: bool
    ) -> list[Chunk]:
        """Decide which retrieved chunks actually support an answer. The vector
        path uses a fixed cosine floor; the lexical path requires shared
        informative terms, because a raw BM25 floor would let one stray common
        word (e.g. "like") qualify an irrelevant passage."""
        settings = get_settings()
        if used_vectors:
            return [c for c, s in scored if s >= settings.rag_min_score]
        qterms = set(tokenize(question))
        if not qterms:
            return []
        need = min(settings.rag_min_query_term_overlap, len(qterms))
        return [c for c, s in scored if s > 0 and len(qterms & set(tokenize(c.text))) >= need]

    def _citations(self, passages: list[Chunk]) -> list[ChatCitation]:
        return [
            ChatCitation(
                n=i + 1,
                source=c.source_name,
                location=c.section,
                quote=_quote(c.text),
            )
            for i, c in enumerate(passages)
        ]

    def _context_block(self, passages: list[Chunk]) -> str:
        return "\n\n".join(
            f"[{i + 1}] ({c.source_name} - {c.section})\n{c.text}" for i, c in enumerate(passages)
        )

    # -- answering -----------------------------------------------------------

    def _extractive(self, passages: list[Chunk]) -> str:
        lines = ["Here is what the indexed DeFiScope evidence supports:"]
        for i, c in enumerate(passages):
            lines.append(f"- [{i + 1}] {c.text}")
        return "\n".join(lines)

    def _refusal(self, protocol_slug: str | None) -> ChatAnswer:
        scope = f" for {protocol_slug}" if protocol_slug else ""
        return ChatAnswer(
            answer=(
                f"I can't establish an answer{scope} from the evidence indexed so far. "
                "This means no retrieved passage cleared the relevance bar - not that "
                "the answer is favorable. To widen the evidence base, run a monitoring "
                "pass (so protocol data is captured) or ask about the methodology the "
                "scores are built from."
            ),
            citations=[],
            grounded=False,
            generated_by="none",
        )

    async def answer(
        self,
        question: str,
        http: httpx.AsyncClient,
        *,
        protocol_slug: str | None = None,
        visible_slugs: set[str] | None = None,
    ) -> ChatAnswer:
        settings = get_settings()
        scored, used_vectors = await self.retrieve(
            question, http, protocol_slug=protocol_slug, visible_slugs=visible_slugs
        )
        supporting = self._supporting(question, scored, used_vectors)
        if not supporting:
            return self._refusal(protocol_slug)
        citations = self._citations(supporting)

        if not settings.openai_api_key:
            return ChatAnswer(
                answer=self._extractive(supporting),
                citations=citations,
                grounded=True,
                generated_by="extractive",
            )

        text = await self._complete(question, supporting, http)
        if text is None:
            # LLM failed: degrade to the honest extractive answer, don't error.
            return ChatAnswer(
                answer=self._extractive(supporting),
                citations=citations,
                grounded=True,
                generated_by="extractive",
            )
        return ChatAnswer(
            answer=text,
            citations=citations,
            grounded=True,
            generated_by="llm",
            model=settings.openai_model,
        )

    async def answer_stream(
        self,
        question: str,
        http: httpx.AsyncClient,
        *,
        protocol_slug: str | None = None,
        visible_slugs: set[str] | None = None,
    ) -> AsyncIterator[dict]:
        """Yield WS frames: ``token`` deltas, then ``citations``, then ``done``.

        Frames are plain dicts the router serializes - keeping the transport
        concerns (socket, pings, closes) out of the reasoning core."""
        settings = get_settings()
        scored, used_vectors = await self.retrieve(
            question, http, protocol_slug=protocol_slug, visible_slugs=visible_slugs
        )
        supporting = self._supporting(question, scored, used_vectors)
        if not supporting:
            refusal = self._refusal(protocol_slug)
            yield {"type": "token", "text": refusal.answer}
            yield {"type": "done", "answer": refusal.model_dump()}
            return

        yield {
            "type": "citations",
            "citations": [c.model_dump() for c in self._citations(supporting)],
        }

        if settings.openai_api_key:
            full: list[str] = []
            async for delta in self._stream(question, supporting, http):
                full.append(delta)
                yield {"type": "token", "text": delta}
            text = "".join(full)
            generated_by = "llm"
            if not text:  # empty stream -> degrade
                text = self._extractive(supporting)
                generated_by = "extractive"
                yield {"type": "token", "text": text}
            model = settings.openai_model if generated_by == "llm" else None
        else:
            text = self._extractive(supporting)
            generated_by = "extractive"
            model = None
            # Emit the composed answer in small pieces so the UI still streams.
            for piece in _chunk_text(text):
                yield {"type": "token", "text": piece}

        yield {
            "type": "done",
            "answer": ChatAnswer(
                answer=text,
                citations=self._citations(supporting),
                grounded=True,
                generated_by=generated_by,
                model=model,
            ).model_dump(),
        }

    # -- OpenAI chat (best-effort; caller has already gated on the key) ------

    def _messages(self, question: str, passages: list[Chunk]) -> list[dict]:
        user = f"Context:\n\n{self._context_block(passages)}\n\nQuestion: {question}"
        return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]

    async def _complete(
        self, question: str, passages: list[Chunk], http: httpx.AsyncClient
    ) -> str | None:
        settings = get_settings()
        try:
            resp = await http.post(
                f"{settings.openai_base_url}/chat/completions",
                json={
                    "model": settings.openai_model,
                    "messages": self._messages(question, passages),
                    "temperature": settings.rag_temperature,
                    "max_tokens": settings.rag_max_tokens,
                },
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                timeout=settings.rag_llm_timeout_seconds,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001 - degrade to extractive
            logger.warning("Chat LLM call failed (%s); using extractive answer", type(exc).__name__)
            return None

    async def _stream(
        self, question: str, passages: list[Chunk], http: httpx.AsyncClient
    ) -> AsyncIterator[str]:
        settings = get_settings()
        payload = {
            "model": settings.openai_model,
            "messages": self._messages(question, passages),
            "temperature": settings.rag_temperature,
            "max_tokens": settings.rag_max_tokens,
            "stream": True,
        }
        try:
            async with http.stream(
                "POST",
                f"{settings.openai_base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                timeout=settings.rag_llm_timeout_seconds,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0]["delta"].get("content")
                    except (KeyError, IndexError, json.JSONDecodeError):
                        continue
                    if delta:
                        yield delta
        except Exception as exc:  # noqa: BLE001 - caller degrades on empty stream
            logger.warning("Chat stream failed (%s); using extractive answer", type(exc).__name__)


def _chunk_text(text: str, size: int = 48) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]
