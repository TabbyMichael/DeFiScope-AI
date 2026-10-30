"""Deterministic BM25 lexical ranking - the offline retrieval path.

Chosen deliberately over any embedding-dependent library so retrieval works
with no API key, no native deps, and identically on SQLite (dev/tests) and
Postgres. This is Okapi BM25 (k1=1.5, b=0.75) over a token index; it returns
scores used both to rank chunks and as a relevance floor for the guardrail.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable

# Light stopword set - enough to de-emphasise connectives without hiding terms
# that carry meaning in DeFi prose (a, the, of ... are noise; "yield", "peg"
# and "tvl" are the signal we must NOT drop).
_STOPWORDS = frozenset(
    """
    a an and are as at be but by for from has have if in into is it its of on or
    that the their there these this to was were will with you your we our it's
    do does can could would should may might not so such than then too very
    """.split()
)

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'._%-]*")
_K1 = 1.5
_B = 0.75


def tokenize(text: str) -> list[str]:
    """Lowercase word/number tokens, dropping punctuation and stopwords."""
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1]


class LexicalIndex:
    """BM25 over an in-memory corpus of (doc_id, tokens).

    Cheap to rebuild (a few thousand short chunks index in well under a second),
    which is why we re-derive it on each query rather than persisting it: state
    stays in the chunk store (SQLite/Postgres), ranking stays pure function."""

    def __init__(self, docs: Iterable[tuple[str, list[str]]]) -> None:
        self._ids: list[str] = []
        self._tf: list[Counter[str]] = []
        self._len: list[int] = []
        df: Counter[str] = Counter()
        for doc_id, tokens in docs:
            self._ids.append(doc_id)
            tf = Counter(tokens)
            self._tf.append(tf)
            self._len.append(len(tokens))
            for term in tf:
                df[term] += 1
        self._n = len(self._ids)
        self._avgdl = (sum(self._len) / self._n) if self._n else 0.0
        # idf with the classic BM25 "+1" smoothing to avoid zero/negative terms.
        self._idf = {
            term: math.log(1 + (self._n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()
        }

    def scores(self, query_tokens: list[str]) -> list[float]:
        """BM25 score of the whole corpus against one query (parallel to ids)."""
        if not self._n or not query_tokens:
            return [0.0] * self._n
        out = [0.0] * self._n
        for term in set(query_tokens):
            idf = self._idf.get(term)
            if idf is None:
                continue
            for i, tf in enumerate(self._tf):
                f = tf.get(term, 0)
                if not f:
                    continue
                denom = f + _K1 * (1 - _B + _B * self._len[i] / (self._avgdl or 1.0))
                out[i] += idf * (f * (_K1 + 1)) / denom
        return out

    def search(self, query: str, top_k: int) -> list[tuple[str, float]]:
        """Return ``(doc_id, score)`` for the ``top_k`` best chunks, desc score."""
        scored = list(zip(self._ids, self.scores(tokenize(query)), strict=True))
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return [(doc_id, s) for doc_id, s in scored[:top_k] if s > 0]
