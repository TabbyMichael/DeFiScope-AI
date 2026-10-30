"""Split source text into citable chunks.

A chunk is the atomic unit the chat answers from: a contiguous span of one
document with stable provenance (which doc, which section) and a content hash
that doubles as its id, so re-ingestion is idempotent (unchanged text keeps the
same id and skips re-embedding).

Two producers:
- ``chunk_markdown`` splits ``docs/*.md`` on ATX heading boundaries, then fills
  to a target size on paragraph/sentence boundaries (never a hard mid-word cut).
- ``chunk_evidence`` turns a protocol's evidence (indicators, gaps, recent
  alerts, overview numbers) into small, self-describing chunks so a question
  about one protocol retrieves its own data.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

# ATX heading (## .. ######) - level 1 is reserved for the doc title.
_HEADING_RE = re.compile(r"^(#{2,6})\s+(.*)$")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class Chunk:
    """One citable passage. ``id`` is a content hash so identical text across
    re-ingestion runs maps to the same stored row (idempotent indexing)."""

    id: str
    doc_id: str
    section: str
    text: str
    source_type: str  # "doc" | "evidence"
    source_name: str  # human label, e.g. "Methodology" or protocol name
    protocol_slug: str | None = None
    embedding: list[float] | None = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "doc_id": self.doc_id,
            "section": self.section,
            "text": self.text,
            "source_type": self.source_type,
            "source_name": self.source_name,
            "protocol_slug": self.protocol_slug,
        }


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _clean(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _make_chunk(
    text: str,
    *,
    doc_id: str,
    section: str,
    source_type: str,
    source_name: str,
    protocol_slug: str | None,
) -> Chunk | None:
    body = _clean(text)
    if len(body) < 20:  # skip empty/label-only fragments; too short to cite
        return None
    return Chunk(
        # Provenance is folded into the hash so the SAME passage appearing under
        # different sources/sections (e.g. a boilerplate limitation reused across
        # protocols) gets a distinct id instead of colliding on the primary key,
        # while unchanged text in the same place still keeps a stable id.
        id=content_hash(f"{doc_id}\u241f{section}\u241f{body}"),
        doc_id=doc_id,
        section=section,
        text=body,
        source_type=source_type,
        source_name=source_name,
        protocol_slug=protocol_slug,
    )


def _split_into_segments(paragraphs: list[str], max_size: int) -> list[str]:
    """Greedy-pack paragraphs into segments up to ``max_size`` chars, breaking
    an over-long paragraph on sentence boundaries then (rarely) on whitespace."""
    segments: list[str] = []
    buf = ""
    for para in paragraphs:
        # A single paragraph longer than max_size can't be packed with anything:
        # flush what we have, then emit its own pre-split sub-segments.
        if len(para) > max_size:
            if buf:
                segments.append(buf)
                buf = ""
            segments.extend(_split_long(para, max_size))
            continue
        candidate = f"{buf}\n\n{para}".strip() if buf else para
        if len(candidate) <= max_size:
            buf = candidate
        else:
            if buf:
                segments.append(buf)
            buf = para
    if buf:
        segments.append(buf)
    return segments


def _split_long(text: str, max_size: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out: list[str] = []
    buf = ""
    for s in sentences:
        if len(buf) + len(s) + 1 <= max_size:
            buf = f"{buf} {s}".strip()
        else:
            if buf:
                out.append(buf)
            # A single sentence longer than max_size is hard-cut on whitespace.
            if len(s) > max_size:
                out.extend(w for w in _hard_wrap(s, max_size))
                buf = ""
            else:
                buf = s
    if buf:
        out.append(buf)
    return out


def _hard_wrap(text: str, max_size: int) -> list[str]:
    words = text.split()
    out: list[str] = []
    buf = ""
    for w in words:
        if len(buf) + len(w) + 1 <= max_size:
            buf = f"{buf} {w}".strip()
        else:
            if buf:
                out.append(buf)
            buf = w
    if buf:
        out.append(buf)
    return out


def chunk_markdown(
    doc_id: str,
    source_name: str,
    markdown: str,
    *,
    chunk_size: int = 800,
    protocol_slug: str | None = None,
) -> list[Chunk]:
    """Split a markdown document into chunks, one callout per heading section.

    A section's body is packed into <= ``chunk_size`` segments; every chunk
    remembers its section heading so a citation can point at "Methodology >
    Real-yield dependence" rather than an opaque index."""
    chunks: list[Chunk] = []
    section = source_name  # fallback label before the first heading
    buf: list[str] = []

    def flush() -> None:
        body = "\n\n".join(buf).strip()
        if not body:
            return
        for segment in _split_into_segments(body.split("\n\n"), chunk_size):
            c = _make_chunk(
                f"{section}: {segment}" if section != source_name else segment,
                doc_id=doc_id,
                section=section,
                source_type="doc",
                source_name=source_name,
                protocol_slug=protocol_slug,
            )
            if c:
                chunks.append(c)
        buf.clear()

    for line in markdown.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            flush()
            section = _clean(m.group(2))
            continue
        if line.startswith("# "):  # doc title: record as the leading section
            flush()
            section = _clean(line[2:])
            continue
        buf.append(line)
    flush()
    return chunks


def chunk_evidence(
    slug: str,
    protocol_name: str,
    *,
    overview_lines: list[str],
    indicators: list[dict],
    data_gaps: list[str],
    recent_alerts: list[str],
    chunk_size: int = 800,
) -> list[Chunk]:
    """Build chunks from a protocol's live evidence so questions about one
    protocol retrieve its own numbers. Each indicator becomes its own chunk
    (label + value + evidence + limitation) - the limitation text is exactly the
    kind of 'what this cannot establish' content the guardrail must surface."""
    doc_id = f"protocol:{slug}"
    chunks: list[Chunk] = []

    if overview_lines:
        body = f"{protocol_name} key metrics: " + "; ".join(_clean(x) for x in overview_lines)
        c = _make_chunk(
            body,
            doc_id=doc_id,
            section="Overview",
            source_type="evidence",
            source_name=protocol_name,
            protocol_slug=slug,
        )
        if c:
            chunks.append(c)

    for ind in indicators:
        label = _clean(str(ind.get("label", "")))
        text = (
            f"{protocol_name} indicator {label}: value={ind.get('value')} "
            f"score={ind.get('score')}. Evidence: {ind.get('evidence', '')} "
            f"Limitation: {ind.get('limitation', '')}"
        )
        c = _make_chunk(
            text,
            doc_id=doc_id,
            section=label or "Indicator",
            source_type="evidence",
            source_name=protocol_name,
            protocol_slug=slug,
        )
        if c:
            chunks.append(c)

    if data_gaps:
        body = f"{protocol_name} data gaps (what current data cannot establish): " + "; ".join(
            _clean(g) for g in data_gaps
        )
        c = _make_chunk(
            body,
            doc_id=doc_id,
            section="Data gaps",
            source_type="evidence",
            source_name=protocol_name,
            protocol_slug=slug,
        )
        if c:
            chunks.append(c)

    if recent_alerts:
        body = f"{protocol_name} recent alerts: " + "; ".join(_clean(a) for a in recent_alerts)
        for segment in _split_into_segments([body], chunk_size):
            c = _make_chunk(
                segment,
                doc_id=doc_id,
                section="Recent alerts",
                source_type="evidence",
                source_name=protocol_name,
                protocol_slug=slug,
            )
            if c:
                chunks.append(c)

    return chunks
