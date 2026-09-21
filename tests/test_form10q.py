"""Tests for revenue_model.form10q — 10-Q / 10-K filings from EDGAR
into the queue. All offline (injected getters + fake pdf_writer); the
one end-to-end test needs the [pdf] extra and skips without it."""
from datetime import datetime
from pathlib import Path

import pytest

from revenue_model.form10q import (digest_filings, fetch_10k_filings,
                                    fetch_10q_filings, fy_tag, quarter_tag,
                                    queue_10k, queue_10q)

CIK = 1868275

TICKERS = {"0": {"cik_str": CIK, "ticker": "CEG",
                 "title": "Constellation Energy Corp"}}

SUBMISSIONS = {"filings": {"recent": {
    "form": ["8-K", "10-Q", "10-Q/A", "10-Q", "10-Q", "10-Q", "10-Q",
             "10-Q", "10-K", "10-K/A", "10-K", "10-K"],
    "filingDate": ["2026-08-06", "2026-08-06", "2026-08-20",
                   "2026-05-11", "2026-02-27", "2026-01-05", "2025-11-06",
                   "2025-08-06", "2026-02-24", "2026-04-30", "2025-02-25",
                   "2026-01-31"],
    "reportDate": [None, "2026-06-30", "2026-06-30", "2026-03-31",
                   "2025-12-31", "2026-04-30", "2025-09-30",
                   "2025-06-30", "2025-12-31", "2025-12-31", "2024-12-31",
                   "2025-11-30"],
    "accessionNumber": ["0001868275-26-000097", "0001868275-26-000081",
                        "0001868275-26-000105", "0001868275-26-000055",
                        "0001868275-26-000020", "0001868275-26-000011",
                        "0001868275-25-000093", "0001868275-25-000051",
                        "0001868275-26-000015", "0001868275-26-000048",
                        "0001868275-25-000012", "0001868275-26-000003"],
    "primaryDocument": ["ceg-20260806.htm", "ceg-20260630.htm",
                        "ceg-20260630_r1.htm", "ceg-20260331.htm",
                        "ceg-20251231.htm", "ceg-20260430.htm",
                        "R2.htm", "ceg-20250630.pdf",
                        "ceg-20251231.htm", "ceg-20251231_r1.htm",
                        "ceg-20241231.htm", "ceg-20251130.htm"],
}}, "tickers": ["CEG"]}

TENQ_HTML = """
<html><head><title>Form 10-Q</title><script>var x = 1;</script></head>
<body>
<p>Constellation Energy Corporation quarterly report on Form 10-Q.</p>
<table>
<tr><td>Mid-Atlantic</td><td>$2,441</td><td>$2,233</td></tr>
<tr><td>Midwest</td><td>$1,120</td><td>$987</td></tr>
</table>
<p>Total revenues were 4,433 million, driven by nuclear generation.</p>
</body></html>
"""


def http_get(url, timeout):
    if "company_tickers" in url:
        return TICKERS
    if "submissions" in url:
        return SUBMISSIONS
    raise AssertionError(f"unexpected url {url}")


def http_get_text(url, timeout):
    assert "/Archives/edgar/data/1868275/" in url, url
    return TENQ_HTML


class FakeWriter:
    """Records every write; drops a marker file so `exists()` works."""

    def __init__(self):
        self.calls = []

    def __call__(self, text, pdf, header):
        self.calls.append((text, Path(pdf), list(header)))
        Path(pdf).write_bytes(b"%PDF-fake")
        return Path(pdf)


class TestQuarterTag:
    def test_calendar_quarters(self):
        assert quarter_tag("2026-03-31") == "Q1_2026"
        assert quarter_tag("2026-06-30") == "Q2_2026"
        assert quarter_tag("2026-09-30") == "Q3_2026"
        assert quarter_tag("2025-12-31") == "Q4_2025"

    def test_non_calendar_and_junk_are_rejected(self):
        assert quarter_tag("2026-04-30") is None   # week-53 style filer
        assert quarter_tag("") is None
        assert quarter_tag("junk") is None


class TestFyTag:
    def test_calendar_year_end(self):
        assert fy_tag("2025-12-31") == "FY2025"
        assert fy_tag("2024-12-31") == "FY2024"

    def test_non_calendar_and_junk_are_rejected(self):
        assert fy_tag("2025-11-30") is None        # non-Dec fiscal year
        assert fy_tag("") is None
        assert fy_tag("junk") is None


class TestFetch10qFilings:
    def test_filters_forms_and_supersedes_amendments(self):
        events = fetch_10q_filings("CEG", http_get=http_get)
        # 8-K out, non-calendar period out, non-htm primary doc out;
        # the Q2'26 original (2026-08-06) superseded by the /A (2026-08-20)
        assert [e["report_date"] for e in events] == \
            ["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]
        assert events[-1]["form"] == "10-Q/A"
        assert events[-1]["file"] == "ceg-20260630_r1.htm"

    def test_oldest_first_with_urls(self):
        events = fetch_10q_filings("CEG", http_get=http_get)
        dates = [e["date"] for e in events]
        assert dates == sorted(dates)
        nod = events[-1]["accession"].replace("-", "")
        assert events[-1]["url"] == \
            f"https://www.sec.gov/Archives/edgar/data/{CIK}/{nod}/" \
            f"ceg-20260630_r1.htm"

    def test_int_cik_bypasses_ticker_lookup(self):
        events = fetch_10q_filings(CIK, http_get=http_get)
        assert len(events) == 4

    def test_since_filter(self):
        events = fetch_10q_filings("CEG", since="2026-03-01",
                                   http_get=http_get)
        assert [e["report_date"] for e in events] == \
            ["2026-03-31", "2026-06-30"]
        events = fetch_10q_filings("CEG",
                                   since=datetime(2026, 6, 1),
                                   http_get=http_get)
        assert len(events) == 1


class TestQueue10q:
    def test_lands_pdf_per_filing_with_pltr_names(self, tmp_path):
        w = FakeWriter()
        recs = queue_10q("CEG", tmp_path, http_get=http_get,
                         http_get_text=http_get_text, pdf_writer=w)
        assert [Path(r["pdf"]).name for r in recs] == [
            "CEG_Q3_2025_10Q.pdf", "CEG_Q4_2025_10Q.pdf",
            "CEG_Q1_2026_10Q.pdf", "CEG_Q2_2026_10Q.pdf"]
        assert all(r["landed"] for r in recs)
        assert (tmp_path / "CEG_Q2_2026_10Q.pdf").exists()

    def test_text_extracted_and_header_carries_source(self, tmp_path):
        w = FakeWriter()
        queue_10q("CEG", tmp_path, http_get=http_get,
                  http_get_text=http_get_text, pdf_writer=w)
        text, pdf, header = w.calls[-1]
        assert "Mid-Atlantic" in text and "4,433" in text
        assert "<td>" not in text and "var x" not in text
        assert header[0].startswith("CEG Q2_2026 Form 10-Q/A")
        assert header[1].startswith(
            "source: https://www.sec.gov/Archives/edgar/data/1868275/")

    def test_idempotent_skip_and_refresh(self, tmp_path):
        w = FakeWriter()
        queue_10q("CEG", tmp_path, http_get=http_get,
                  http_get_text=http_get_text, pdf_writer=w)
        assert len(w.calls) == 4
        recs = queue_10q("CEG", tmp_path, http_get=http_get,
                         http_get_text=http_get_text, pdf_writer=w)
        assert len(w.calls) == 4                     # nothing re-fetched
        assert all(not r["landed"] for r in recs)
        recs = queue_10q("CEG", tmp_path, refresh=True, http_get=http_get,
                         http_get_text=http_get_text, pdf_writer=w)
        assert len(w.calls) == 8
        assert all(r["landed"] for r in recs)

    def test_ticker_required_for_naming(self, tmp_path):
        with pytest.raises(ValueError):
            queue_10q(CIK, tmp_path, http_get=http_get)
        with pytest.raises(ValueError):
            queue_10q("1868275", tmp_path, http_get=http_get)


class TestFetch10kFilings:
    def test_filters_forms_and_supersedes_amendments(self):
        events = fetch_10k_filings("CEG", http_get=http_get)
        # 10-Qs out; the Nov-30 fiscal year out; the FY2025 10-K
        # (2026-02-24) superseded by the /A (2026-04-30)
        assert [e["report_date"] for e in events] == \
            ["2024-12-31", "2025-12-31"]
        assert events[-1]["form"] == "10-K/A"
        assert events[-1]["file"] == "ceg-20251231_r1.htm"
        nod = events[-1]["accession"].replace("-", "")
        assert events[-1]["url"] == \
            f"https://www.sec.gov/Archives/edgar/data/{CIK}/{nod}/" \
            f"ceg-20251231_r1.htm"

    def test_since_filter(self):
        events = fetch_10k_filings("CEG", since="2026-01-01",
                                   http_get=http_get)
        assert [e["report_date"] for e in events] == ["2025-12-31"]


class TestQueue10k:
    def test_lands_fy_named_pdfs(self, tmp_path):
        w = FakeWriter()
        recs = queue_10k("CEG", tmp_path, http_get=http_get,
                         http_get_text=http_get_text, pdf_writer=w)
        assert [Path(r["pdf"]).name for r in recs] == [
            "CEG_FY2024_10K.pdf", "CEG_FY2025_10K.pdf"]
        assert all(r["landed"] for r in recs)
        assert recs[-1]["quarter"] == "FY2025"

    def test_header_carries_the_amendment(self, tmp_path):
        w = FakeWriter()
        queue_10k("CEG", tmp_path, http_get=http_get,
                  http_get_text=http_get_text, pdf_writer=w)
        text, pdf, header = w.calls[-1]
        assert header[0] == ("CEG FY2025 Form 10-K/A "
                             "(filed 2026-04-30, period 2025-12-31)")
        assert header[1].startswith(
            "source: https://www.sec.gov/Archives/edgar/data/1868275/")

    def test_idempotent_and_ticker_required(self, tmp_path):
        w = FakeWriter()
        queue_10k("CEG", tmp_path, http_get=http_get,
                  http_get_text=http_get_text, pdf_writer=w)
        assert len(w.calls) == 2
        recs = queue_10k("CEG", tmp_path, http_get=http_get,
                         http_get_text=http_get_text, pdf_writer=w)
        assert len(w.calls) == 2
        assert all(not r["landed"] for r in recs)
        with pytest.raises(ValueError):
            queue_10k(CIK, tmp_path, http_get=http_get)


class TestEndToEnd:
    def test_real_writer_then_digest(self, tmp_path):
        """Default pdf_writer (fitz) + the standard digest channel:
        the fake backend's verifiable quote becomes a card, the
        hallucinated one is voided, and the page cache lands."""
        pytest.importorskip("fitz")

        def backend(page_text, file_name, page_no):
            if page_no != 1:
                return []
            return [
                {"clue": "区域分部收入存在", "quote": "Mid-Atlantic",
                 "ring": "core", "segment": "区域分部"},
                {"clue": "hallucinated", "quote": "Texas secession revenue",
                 "ring": "core", "segment": ""},
            ]

        recs = queue_10q("CEG", tmp_path, http_get=http_get,
                         http_get_text=http_get_text)
        r = digest_filings(recs[:1], backend, queue_dir=tmp_path)
        doc = r["documents"]["CEG_Q3_2025_10Q.pdf"]
        assert doc["pages"] >= 1
        assert len(r["cards"]) == 1
        assert r["cards"][0].quote == "Mid-Atlantic"
        assert r["cards"][0].anchor_file == "CEG_Q3_2025_10Q.pdf"
        assert len(r["voided"]) == 1
        assert (tmp_path / "digest_cache" / "CEG_Q3_2025_10Q_p1.json").exists()
