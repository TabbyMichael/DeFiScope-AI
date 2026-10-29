"""Unit tests for brief export rendering (no HTTP)."""

import csv
import io

import pytest
from app.schemas import BriefSection, ResearchBrief
from app.services import export


def make_brief() -> ResearchBrief:
    sections = BriefSection(
        executive_summary="Aave V3 holds $10B TVL (& growing); composite risk 42/100.",
        growth_drivers=[
            'TVL +8% over 30d, with a "quoted" caveat',
            "Multi-chain, but no single chain >70%",
        ],
        risks=[
            "Liquidity concentration: Ethereum 65%",
            "Incentive dependence (limitation: needs <5d history)",
        ],
        data_gaps=["Missing on-chain volume/fee data"],
        confidence="Medium: 4/5 indicators computable",
        recommendations=["Cross-check fees on Dune", "Review the latest audits"],
    )
    return ResearchBrief(
        slug="aave-v3",
        protocol="Aave V3",
        generated_by="template",
        markdown="# Aave V3 - Research Brief\n\n## Executive summary\n\nAave V3 holds $10B TVL.\n",
        sections=sections,
        as_of="2026-01-15",
        sources=["https://defillama.com/protocol/aave-v3", "https://api.llama.fi"],
    )


class TestMarkdown:
    def test_returns_brief_markdown_verbatim(self):
        brief = make_brief()
        assert export.to_markdown(brief) == brief.markdown


class TestCsv:
    def test_header_and_metadata_rows(self):
        rows = list(csv.DictReader(io.StringIO(export.to_csv(make_brief()))))
        by_section: dict[str, list[str]] = {}
        for r in rows:
            by_section.setdefault(r["section"], []).append(r["text"])
        assert by_section["protocol"] == ["Aave V3"]
        assert by_section["slug"] == ["aave-v3"]
        assert len(by_section["growth_driver"]) == 2
        assert len(by_section["risk"]) == 2
        assert len(by_section["source"]) == 2

    def test_special_characters_round_trip(self):
        # commas, embedded quotes and the ampersand must survive CSV quoting.
        raw = export.to_csv(make_brief())
        rows = list(csv.reader(io.StringIO(raw)))
        texts = [r[1] for r in rows if len(r) == 2 and r[0] == "growth_driver"]
        assert 'TVL +8% over 30d, with a "quoted" caveat' in texts

    def test_formula_injection_is_neutralized(self):
        # A cell starting with =/+/-/@ can be executed by Excel/Sheets on open;
        # the export must prefix such cells so they are treated as literal text.
        brief = make_brief()
        brief.sections.executive_summary = '=HYPERLINK("http://evil","click")'
        brief.sections.recommendations = ["@SUM(A1:A9)", "-2+3", "Review audits normally"]
        rows = list(csv.reader(io.StringIO(export.to_csv(brief))))
        cells = {r[0]: r[1] for r in rows if len(r) == 2}
        assert cells["executive_summary"].startswith("'=")
        recs = [r[1] for r in rows if len(r) == 2 and r[0] == "recommendation"]
        assert all(v.startswith("'") for v in recs if v[:1] in ("@", "-"))
        # ordinary prose is left untouched
        assert "Review audits normally" in recs


class TestPdf:
    def test_produces_pdf_bytes(self):
        data = export.to_pdf(make_brief())
        assert isinstance(data, bytes)
        assert data[:4] == b"%PDF"
        assert len(data) > 500


class TestRender:
    @pytest.mark.parametrize(
        ("fmt", "media", "ext"),
        [
            ("md", "text/markdown", ".md"),
            ("csv", "text/csv", ".csv"),
            ("pdf", "application/pdf", ".pdf"),
        ],
    )
    def test_dispatch_types_and_filenames(self, fmt, media, ext):
        payload, content_type, filename = export.render(make_brief(), fmt)
        assert content_type.startswith(media)
        assert filename == f"defiscope-aave-v3-2026-01-15{ext}"
        assert payload  # non-empty

    def test_unknown_format_raises(self):
        with pytest.raises(ValueError):
            export.render(make_brief(), "xls")
