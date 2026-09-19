"""Tests for revenue_model.form8k_exhibit — 8-K EX-99 exhibits through
the digest/verify channel. All offline (injected getters + backend)."""
from datetime import datetime

from revenue_model.form8k_exhibit import (
    _is_exhibit, digest_8k_exhibits, exhibit_to_pages, fetch_8k_exhibits,
)

CIK = 1321655

SUBMISSIONS = {
    "filings": {"recent": {
        "form": ["8-K", "8-K", "10-K", "8-K"],
        "filingDate": ["2023-08-07", "2022-11-07", "2023-02-13", "2024-02-05"],
        "items": ["2.02,9.01", "2.02,9.01", None, "7.01,9.01"],
        "accessionNumber": ["0001321655-23-000086", "0001321655-22-000029",
                            "0001321655-23-000005", "0001321655-24-000010"],
    }}
}

INDEX_086 = {"directory": {"item": [
    {"name": "0001321655-23-000086-index-headers.html"},
    {"name": "0001321655-23-000086-index.html"},
    {"name": "a2023q2ex991pressrelease.htm"},
    {"name": "pltr-20230807.htm"},
    {"name": "R1.htm"},
]}}
INDEX_029 = {"directory": {"item": [
    {"name": "a2022q3exhibit992ceoletter.htm"},
    {"name": "pltr-20221107.htm"},
]}}
INDEX_010 = {"directory": {"item": [
    {"name": "pltr-20240205.htm"},
]}}

EXHIBIT_HTML = """
<html><head><title>PR</title><script>var x = 1;</script></head><body>
<p>DENVER--(BUSINESS WIRE)-- Palantir Technologies Inc. today announced
financial results for the second quarter ended June 30, 2023.</p>
<table><tr><td>Revenue grew 13% year-over-year to $533 million.</td></tr></table>
<p>US commercial revenue grew 46% year-over-year.</p>
</body></html>
"""


def http_get(url, timeout):
    if "submissions" in url:
        return SUBMISSIONS
    if "000132165523000086" in url:
        return INDEX_086
    if "000132165522000029" in url:
        return INDEX_029
    if "000132165524000010" in url:
        return INDEX_010
    raise AssertionError(f"unexpected url {url}")


def http_get_text(url, timeout):
    assert "ex99" in url or "exhibit99" in url, url
    return EXHIBIT_HTML


def fake_backend(page_text, file_name, page_no):
    if page_no != 1:
        return []
    return [
        {"clue": "revenue growth", "quote": "Revenue grew 13% year-over-year",
         "ring": "core", "segment": ""},
        {"clue": "hallucinated", "quote": "CFO promised 200% growth",
         "ring": "self", "segment": ""},
    ]


class TestIsExhibit:
    def test_matches_observed_patterns(self):
        assert _is_exhibit("a2023q2ex991pressrelease.htm")
        assert _is_exhibit("d259921dex991.htm")
        assert _is_exhibit("a2022q3exhibit992ceoletter.htm")
        assert _is_exhibit("ex-992.htm")

    def test_skips_procedural_files(self):
        assert not _is_exhibit("index.html")
        assert not _is_exhibit("0001321655-23-000086-index-headers.html")
        assert not _is_exhibit("R1.htm")
        assert not _is_exhibit("pltr-20230807.htm")
        assert not _is_exhibit("logo.png")


class TestExhibitToPages:
    def test_extracts_text_drops_script(self):
        pages = exhibit_to_pages(EXHIBIT_HTML)
        text = "\n".join(pages)
        assert "Revenue grew 13%" in text
        assert "var x" not in text
        assert "Palantir Technologies" in text

    def test_chunks_respect_max_chars(self):
        pages = exhibit_to_pages(EXHIBIT_HTML, max_chars=140)
        assert len(pages) == 2
        # a page is at most the join of lines whose running size stayed
        # under max_chars (a single over-long line keeps its own page —
        # mid-line splits would break verbatim quotes)
        assert all(len(p) <= 141 for p in pages)

    def test_quotes_verifiable_inside_a_page(self):
        pages = exhibit_to_pages(EXHIBIT_HTML)
        assert any("US commercial revenue grew 46%" in p for p in pages)


class TestFetch8kExhibits:
    def test_lists_ex99_documents_with_event_metadata(self):
        exhibits = fetch_8k_exhibits(CIK, http_get=http_get,
                                     use_cache=False)
        files = [e["file"] for e in exhibits]
        assert files == ["a2022q3exhibit992ceoletter.htm",
                         "a2023q2ex991pressrelease.htm"]
        by_file = {e["file"]: e for e in exhibits}
        pr = by_file["a2023q2ex991pressrelease.htm"]
        assert pr["category"] == "Earnings"
        assert pr["date"] == datetime(2023, 8, 7)
        assert pr["url"].endswith("/000132165523000086/"
                                  "a2023q2ex991pressrelease.htm")

    def test_since_and_category_filters(self):
        exhibits = fetch_8k_exhibits(CIK, since="2023-01-01",
                                     categories=["Earnings"],
                                     http_get=http_get, use_cache=False)
        assert [e["file"] for e in exhibits] == \
            ["a2023q2ex991pressrelease.htm"]


class TestDigest8kExhibits:
    def test_cards_are_primary_and_verified(self):
        r = digest_8k_exhibits(CIK, fake_backend, http_get=http_get,
                               http_get_text=http_get_text, use_cache=False)
        assert r["exhibits"] == 2
        # both exhibits share the same fake html -> 1 card each
        assert len(r["cards"]) == 2
        for c in r["cards"]:
            assert c.confidence == "primary"
            assert c.verified
            assert c.anchor_file.startswith("8K_000")
        assert any("quote_not_found" in v for v in r["voided"])
        for meta in r["documents"].values():
            assert meta["category"] == "Earnings"
            assert meta["cards"] == 1

    def test_page_cache_second_run_all_cached(self, tmp_path):
        digest_8k_exhibits(CIK, fake_backend, cache_dir=tmp_path / "c",
                           http_get=http_get, http_get_text=http_get_text,
                           use_cache=False)
        r2 = digest_8k_exhibits(CIK, fake_backend, cache_dir=tmp_path / "c",
                                http_get=http_get,
                                http_get_text=http_get_text,
                                use_cache=False)
        for meta in r2["documents"].values():
            assert meta["cached"] == meta["pages"]
        assert len(r2["cards"]) == 2

    def test_fetch_failure_voids_exhibit_not_run(self):
        def bad_text(url, timeout):
            raise RuntimeError("network down")
        r = digest_8k_exhibits(CIK, fake_backend, http_get=http_get,
                               http_get_text=bad_text, use_cache=False)
        assert r["cards"] == []
        assert r["exhibits"] == 0
        assert len(r["voided"]) == 2
        assert all("error" in v for v in r["voided"])

    def test_index_json_shape_guarded(self):
        # malformed index (no directory) -> no exhibits, no crash
        def bad_json(url, timeout):
            if "index.json" in url:
                return {"unexpected": True}
            return SUBMISSIONS
        exhibits = fetch_8k_exhibits(CIK, http_get=bad_json, use_cache=False)
        assert exhibits == []
