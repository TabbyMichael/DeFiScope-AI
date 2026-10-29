"""Format-agnostic exports of a research brief.

The brief engine already produces Markdown + structured ``BriefSection`` data;
this renders that single source of truth into the download formats an analyst
reaches for - portable Markdown, tidy CSV (re-importable into a spreadsheet),
and a print-ready PDF. No re-analysis happens here: an export shows exactly the
evidence-backed content the UI vetted, including the data-gap caveats, so a
downloaded brief can never overstate confidence relative to what was screened.
"""

from __future__ import annotations

import csv
import io
from xml.sax.saxutils import escape

from app.schemas import ResearchBrief

# format -> media type used for the download response.
MEDIA_TYPES = {
    "md": "text/markdown; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
    "pdf": "application/pdf",
}
VALID_FORMATS = tuple(MEDIA_TYPES)

# Characters that make a spreadsheet treat a cell as a formula on open.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: str) -> str:
    """Neutralize spreadsheet formula injection in a free-text cell.

    A cell whose text begins with a formula trigger (``=``, ``+``, ``-``, ``@``,
    tab, CR) is prefixed with an apostrophe so Excel/Sheets render it literally.
    Ordinary prose - the overwhelming majority of brief text - is returned
    unchanged so the export still round-trips verbatim."""
    if value[:1] in _FORMULA_PREFIXES:
        return "'" + value
    return value


def _filename(brief: ResearchBrief, ext: str) -> str:
    safe_slug = (brief.slug or "protocol").replace("/", "-")
    as_of = brief.as_of if brief.as_of and brief.as_of != "n/a" else "latest"
    return f"defiscope-{safe_slug}-{as_of}.{ext}"


def to_markdown(brief: ResearchBrief) -> str:
    """The brief's own Markdown, generated once by the brief engine."""
    return brief.markdown


def to_csv(brief: ResearchBrief) -> str:
    """Tidy two-column layout (``section,text``) with one row per list item so
    the file round-trips cleanly into a spreadsheet without cell-splicing.

    Free-text cells are passed through :func:`_csv_safe` to neutralize
    spreadsheet formula injection: a value beginning with ``=``, ``+``, ``-``,
    ``@`` (or a tab/CR) can be executed by Excel/Google Sheets on open, and
    brief text is semi-trusted (DefiLlama-sourced protocol names, notes)."""
    buf = io.StringIO()
    w = csv.writer(buf)

    def row(section: str, text: object) -> None:
        # The section key is a fixed literal we control; only the text column
        # carries upstream/derived prose that needs neutralizing.
        w.writerow([section, _csv_safe(str(text))])

    w.writerow(["section", "text"])
    s = brief.sections
    row("protocol", brief.protocol)
    row("slug", brief.slug)
    row("generated_by", brief.generated_by)
    row("as_of", brief.as_of)
    row("executive_summary", s.executive_summary)
    for item in s.growth_drivers:
        row("growth_driver", item)
    for item in s.risks:
        row("risk", item)
    for item in s.data_gaps:
        row("data_gap", item)
    row("confidence", s.confidence)
    for item in s.recommendations:
        row("recommendation", item)
    for src in brief.sources:
        row("source", src)
    return buf.getvalue()


def to_pdf(brief: ResearchBrief) -> bytes:
    """Render the brief to a PDF (reportlab platypus) and return its bytes.

    Text is XML-escaped before flowing into reportlab's mini-HTML paragraphs,
    because brief bodies routinely contain ``&``, ``<`` and ``>`` from metric
    comparisons (e.g. "no single chain above 70%", "limitation: <5d history").
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        title=f"{brief.protocol} - Research Brief",
        author="DeFiScope AI",
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )
    styles = getSampleStyleSheet()
    h1 = styles["Title"]
    h2 = styles["Heading2"]
    body = styles["BodyText"]
    meta = ParagraphStyle(
        "meta", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#6b7280")
    )
    bullet = ParagraphStyle("bullet", parent=body, leftIndent=10, spaceBefore=2)

    s = brief.sections
    story: list = []
    story.append(Paragraph(escape(f"{brief.protocol} - Research Brief"), h1))
    gen = "LLM-generated" if brief.generated_by == "llm" else "template engine (no LLM key)"
    story.append(Paragraph(escape(f"DeFiScope AI | {gen} | data as of {brief.as_of}"), meta))
    story.append(Spacer(1, 6 * mm))

    def heading(title: str) -> None:
        story.append(Paragraph(escape(title), h2))
        story.append(Spacer(1, 1.5 * mm))

    def paragraph(text: str) -> None:
        story.append(Paragraph(escape(text), body))
        story.append(Spacer(1, 3 * mm))

    def bullets(items: list[str]) -> None:
        for item in items:
            story.append(Paragraph("• " + escape(item), bullet))
        story.append(Spacer(1, 3 * mm))

    heading("Executive summary")
    paragraph(s.executive_summary)
    if s.growth_drivers:
        heading("Growth drivers")
        bullets(s.growth_drivers)
    if s.risks:
        heading("Risks")
        bullets(s.risks)
    if s.data_gaps:
        heading("What this analysis cannot establish")
        bullets(s.data_gaps)
    heading("Confidence")
    paragraph(s.confidence)
    if s.recommendations:
        heading("Recommended next steps")
        bullets(s.recommendations)

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(escape("Sources: " + ", ".join(brief.sources)), meta))
    doc.build(story)
    return buf.getvalue()


def render(brief: ResearchBrief, fmt: str) -> tuple[bytes, str, str]:
    """Dispatch to the requested format. Returns ``(payload, media_type,
    filename)``. Raises ``ValueError`` for an unknown format so the router can
    surface a clean 400."""
    if fmt not in VALID_FORMATS:
        raise ValueError(f"unsupported export format: {fmt!r}")
    if fmt == "csv":
        payload = to_csv(brief).encode("utf-8")
    elif fmt == "pdf":
        payload = to_pdf(brief)
    else:
        payload = to_markdown(brief).encode("utf-8")
    return payload, MEDIA_TYPES[fmt], _filename(brief, fmt)
