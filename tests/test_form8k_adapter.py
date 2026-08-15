"""Tests for form8k_adapter — fully offline via injected fake http_get."""
from datetime import date, datetime

import pytest

from revenue_model import form8k_adapter
from revenue_model.form8k_adapter import classify_items, fetch_8k_events


def _fake_http(routes):
    def http_get(url, timeout):
        if url in routes:
            return routes[url]
        raise ValueError(f"unexpected url: {url}")
    return http_get


_TICKERS = {"0": {"ticker": "NVDA", "cik_str": 1045810,
                  "title": "NVIDIA Corporation"}}


def _submissions_url(cik: int) -> str:
    return f"https://data.sec.gov/submissions/CIK{cik:010d}.json"


def _subs(forms, dates, items, accessions=None):
    return {"filings": {"recent": {
        "form": forms, "filingDate": dates, "items": items,
        "accessionNumber": accessions or [""] * len(forms)}}}


# ---- classify_items: materiality priority ----------------------------------

def test_classify_earnings_with_exhibits_is_earnings():
    assert classify_items("2.02,9.01") == "Earnings"


def test_classify_agreement_outranks_earnings():
    """1.01 is more material than 2.02; both present -> Agreement."""
    assert classify_items("1.01,2.02,9.01") == "Agreement"


def test_classify_ma_completion_outranks_everything():
    assert classify_items("5.02,2.01,9.01") == "M&A"


def test_classify_exhibits_only_maps_to_nothing():
    assert classify_items("9.01") == ""
    assert classify_items("") == ""


def test_classify_whitespace_and_padding():
    assert classify_items(" 2.02 , 9.01 ") == "Earnings"
    assert classify_items("7.01") == "Other/RegFD"
    assert classify_items("3.02") == "Equity Issuance"
    assert classify_items("2.03") == "Financing/Oblig"


# ---- fetch_8k_events: parsing, filtering, injection --------------------------

def test_fetch_skips_non_8k_and_unmapped():
    sub = _subs(
        ["8-K", "10-Q", "8-K", "8-K"],
        ["2024-01-05", "2024-02-01", "2024-03-10", "2024-04-01"],
        ["2.02,9.01", "", "9.01", "5.02,9.01"],
        ["a1", "a2", "a3", "a4"])
    http = _fake_http({_submissions_url(1045810): sub})
    events = fetch_8k_events(1045810, http_get=http)
    assert [e["category"] for e in events] == ["Earnings", "Management"]
    assert events[0]["date"] == datetime(2024, 1, 5)
    assert events[0]["accession"] == "a1"
    assert all(e["form"] == "8-K" for e in events)


def test_fetch_sorted_oldest_first():
    sub = _subs(["8-K", "8-K"],
                ["2024-06-01", "2024-01-01"],
                ["2.02", "5.02"], ["a", "b"])
    http = _fake_http({_submissions_url(1045810): sub})
    events = fetch_8k_events(1045810, http_get=http)
    assert [e["date"] for e in events] == \
        [datetime(2024, 1, 1), datetime(2024, 6, 1)]


def test_fetch_ticker_resolves_cik():
    sub = _subs(["8-K"], ["2024-01-05"], ["1.01,9.01"], ["a1"])
    http = _fake_http({
        "https://www.sec.gov/files/company_tickers.json": _TICKERS,
        _submissions_url(1045810): sub,
    })
    events = fetch_8k_events("NVDA", http_get=http)
    assert len(events) == 1 and events[0]["category"] == "Agreement"


def test_fetch_since_filters_inclusive():
    sub = _subs(["8-K", "8-K", "8-K"],
                ["2024-01-01", "2024-03-01", "2024-06-01"],
                ["2.02", "2.02", "2.02"], ["a", "b", "c"])
    http = _fake_http({_submissions_url(1045810): sub})
    # date object
    assert len(fetch_8k_events(1045810, since=date(2024, 3, 1),
                               http_get=http)) == 2
    # string form, inclusive boundary
    evs = fetch_8k_events(1045810, since="2024-03-01", http_get=http)
    assert evs[0]["date"] == datetime(2024, 3, 1)
    # datetime form
    assert len(fetch_8k_events(1045810, since=datetime(2024, 4, 1),
                               http_get=http)) == 1


def test_fetch_skips_malformed_dates():
    sub = _subs(["8-K", "8-K"], ["not-a-date", "2024-01-05"],
                ["2.02", "2.02"], ["a", "b"])
    http = _fake_http({_submissions_url(1045810): sub})
    assert len(fetch_8k_events(1045810, http_get=http)) == 1


def test_item_categories_table_is_priority_ordered():
    """The mapping list drives classify_items; keep the documented order."""
    codes = [c for c, _ in form8k_adapter.ITEM_CATEGORIES]
    assert codes.index("2.01") < codes.index("1.01") < codes.index("2.02")
    assert codes.index("2.02") < codes.index("7.01")
