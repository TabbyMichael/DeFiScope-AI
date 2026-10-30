"""OpenAI-compatible embeddings for the chat retrieval index.

Mirrors the brief LLM path (``services/briefs.py``): a single raw ``httpx``
call guarded by "is a key configured?". When there is no key (the offline
showcase, or any unit test) ``embed_texts`` returns ``None`` and the caller
falls back to the pure-Python BM25 index - so embeddings are an enhancement,
never a hard dependency.
"""

from __future__ import annotations

import logging
import math

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


async def embed_texts(texts: list[str], http: httpx.AsyncClient) -> list[list[float]] | None:
    """Embed ``texts`` via ``{openai_base_url}/embeddings``.

    Returns one vector per input text, or ``None`` when no API key is set or the
    request fails (the caller degrades to lexical retrieval). Never raises -
    embedding is best-effort, exactly like the brief LLM path."""
    settings = get_settings()
    if not settings.openai_api_key or not texts:
        return None
    try:
        resp = await http.post(
            f"{settings.openai_base_url}/embeddings",
            json={
                "model": settings.openai_embedding_model,
                "input": texts,
                "dimensions": settings.embedding_dimensions,
            },
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        # The API returns objects keyed by index; reorder defensively.
        ordered = sorted(data, key=lambda d: d.get("index", 0))
        return [item["embedding"] for item in ordered]
    except Exception as exc:  # noqa: BLE001 - degrade to lexical, never crash
        # Log only the exception TYPE: httpx's raise_for_status() embeds the
        # full request URL (with the bearer-keyed host) in the message.
        logger.warning("Embedding request failed (%s); using lexical fallback", type(exc).__name__)
        return None


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity, clamped to [0, 1] for use as a ranking floor.

    Identical short vectors can overshoot 1.0 slightly under float error; a
    negative cosine (opposite vectors) is floored to 0 since we never want a
    'dissimilar' score to compete with unrelated-but-positive matches."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))
