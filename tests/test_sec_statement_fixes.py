"""Regression tests for the v0.14 sec_adapter fixes + fiscal quarters.

BUG-A: fetch_statement picked ONE revenue concept; issuers switch elements
       (SDGR: ASC 606 -> Revenues in 2024), silently dropping years.
BUG-B: a YTD cumulative and a discrete quarter sharing an end date
       collided in the (fy, fp) slot map, corrupting single-quarter
       differencing (SDGR Q3'24 derived as -48.6M USD).

All offline via injected fake http_get, matching the suite's conventions.
"""
from datetime import date
from typing import Callable

from revenue_model import sec_adapter
from revenue_model.sec_adapter import SEC_API, fetch_fiscal_quarters, fetch_statement


def _fake_http(routes):
    def http_get(url, timeout):
        if url in routes:
            return routes[url]
        raise ValueError(f"unexpected url: {url}")
    return http_get


def _facts_url(cik: int) -> str:
    return f"{SEC_API}/api/xbrl/companyfacts/CIK{cik:010d}.json"


def _usd(*points):
    return {"units": {"USD": list(points)}}


def _pt(start, end, val, form="10-Q", filed="2026-01-01"):
    return {"start": start, "end": end, "val": val, "form": form,
            "fy": int(end[:4]), "fp": "FY", "filed": filed}


def _income_facts(revenues, asc606=None):
    """companyfacts with income concepts; only revenue matters here."""
    gaap = {}
    if revenues is not None:
        gaap["Revenues"] = _usd(*revenues)
    if asc606 is not None:
        gaap["RevenueFromContractWithCustomerExcludingAssessedTax"] = \
            _usd(*asc606)
    return {"cik": 1, "facts": {"us-gaap": gaap}}


# ---- BUG-A: concept switching must not drop years --------------------------

def test_statement_merges_revenue_concepts():
    """ASC 606 filed 2019-2023, Revenues filed 2024+: both must appear."""
    cik = 1001
    asc = [
        _pt("2019-01-01", "2019-03-31", 20.7e6),
        _pt("2019-01-01", "2019-12-31", 85.5e6, form="10-K"),
        _pt("2023-01-01", "2023-03-31", 64.8e6),
        _pt("2023-01-01", "2023-12-31", 216.7e6, form="10-K"),
    ]
    rev = [
        _pt("2024-01-01", "2024-03-31", 36.6e6),
        _pt("2024-01-01", "2024-12-31", 207.5e6, form="10-K"),
    ]
    http = _fake_http({_facts_url(cik): _income_facts(rev, asc606=asc)})
    stmt = fetch_statement(cik, "income", freq="quarterly",
                           single_quarter=True, http_get=http)
    years = {fy for (fy, fp) in stmt if fp == "Q1"}
    assert 2019 in years and 2023 in years and 2024 in years  # was: only 2024


# ---- BUG-B: YTD/discrete collision must not corrupt differencing -----------

def _sdgr_style_2024():
    """Discrete Q1-Q3 tagged alongside YTD chains, FY anchor, like SDGR."""
    return [
        _pt("2024-01-01", "2024-03-31", 36.6e6),   # Q1 discrete
        _pt("2024-01-01", "2024-06-30", 83.9e6),   # YTD2 (BUG-B bait)
        _pt("2024-04-01", "2024-06-30", 47.3e6),   # Q2 discrete
        _pt("2024-01-01", "2024-09-30", 119.2e6),  # YTD3
        _pt("2024-07-01", "2024-09-30", 35.3e6),   # Q3 discrete
        _pt("2024-01-01", "2024-12-31", 207.5e6, form="10-K"),  # FY
    ]


def test_statement_single_quarter_prefers_discrete_no_negatives():
    cik = 1002
    http = _fake_http({_facts_url(cik): _income_facts(_sdgr_style_2024())})
    stmt = fetch_statement(cik, "income", freq="quarterly",
                           single_quarter=True, http_get=http)
    # was: Q3 = discrete(Jul-Sep) - YTD(Jan-Jun) = -48.6
    assert stmt[(2024, "Q1")]["Revenue"] == 36.6
    assert stmt[(2024, "Q2")]["Revenue"] == 47.3
    assert stmt[(2024, "Q3")]["Revenue"] == 35.3
    assert stmt[(2024, "Q4")]["Revenue"] == 207.5 - 119.2  # FY - YTD3
    for (fy, fp), row in stmt.items():
        assert row["Revenue"] > 0, f"negative quarter at {(fy, fp)}"


def test_statement_ytd_only_chain_still_differences():
    """Issuer tags only cumulative YTD columns: derive Q2 = YTD2 - Q1."""
    cik = 1003
    pts = [
        _pt("2024-01-01", "2024-03-31", 10e6),
        _pt("2024-01-01", "2024-06-30", 35e6),
        _pt("2024-01-01", "2024-09-30", 55e6),
        _pt("2024-01-01", "2024-12-31", 75e6, form="10-K"),
    ]
    http = _fake_http({_facts_url(cik): _income_facts(pts)})
    stmt = fetch_statement(cik, "income", freq="quarterly",
                           single_quarter=True, http_get=http)
    assert stmt[(2024, "Q1")]["Revenue"] == 10
    assert stmt[(2024, "Q2")]["Revenue"] == 25
    assert stmt[(2024, "Q3")]["Revenue"] == 20
    assert stmt[(2024, "Q4")]["Revenue"] == 20


def test_statement_as_reported_prefers_ytd():
    """Plain quarterly (no differencing) documents cumulative semantics."""
    cik = 1004
    http = _fake_http({_facts_url(cik): _income_facts(_sdgr_style_2024())})
    stmt = fetch_statement(cik, "income", freq="quarterly", http_get=http)
    assert stmt[(2024, "Q2")]["Revenue"] == 83.9  # YTD, not the 47.3 discrete
    assert stmt[(2024, "Q3")]["Revenue"] == 119.2


# ---- fetch_fiscal_quarters: fiscal-general series ---------------------------

def test_fiscal_quarters_calendar_year():
    cik = 1005
    http = _fake_http({_facts_url(cik): _income_facts(_sdgr_style_2024())})
    qs = fetch_fiscal_quarters(cik, http_get=http)
    assert qs == [
        (2024, 1, date(2024, 3, 31), 36.6),
        (2024, 2, date(2024, 6, 30), 47.3),
        (2024, 3, date(2024, 9, 30), 35.3),
        (2024, 4, date(2024, 12, 31), 88.3),
    ]


def test_fiscal_quarters_non_calendar_year():
    """NVDA-style FY ending late January: quarters derive within the FY."""
    cik = 1006
    pts = [
        # FY2026: 2025-02-03 .. 2026-02-01 (365d)
        _pt("2025-02-03", "2025-05-04", 44.0e6),
        _pt("2025-02-03", "2025-08-03", 90.7e6),
        _pt("2025-05-05", "2025-08-03", 46.7e6),
        _pt("2025-02-03", "2025-11-02", 147.7e6),
        _pt("2025-08-04", "2025-11-02", 57.0e6),
        _pt("2025-02-03", "2026-02-01", 215.8e6, form="10-K"),
    ]
    http = _fake_http({_facts_url(cik): _income_facts(pts)})
    qs = fetch_fiscal_quarters(cik, http_get=http)
    assert len(qs) == 4
    fy_labels = {q[0] for q in qs}
    assert fy_labels == {2026}          # labeled by FY-END year
    assert [q[3] for q in qs] == [44.0, 46.7, 57.0, 68.1]  # Q4 = FY - YTD3


def test_fiscal_quarters_excludes_incomplete_trailing_year():
    """10-Qs filed beyond the last 10-K must not fabricate a partial FY."""
    cik = 1007
    pts = _sdgr_style_2024() + [
        _pt("2025-01-01", "2025-03-31", 59.6e6),  # no FY2025 10-K anchor
    ]
    http = _fake_http({_facts_url(cik): _income_facts(pts)})
    qs = fetch_fiscal_quarters(cik, http_get=http)
    assert all(q[0] == 2024 for q in qs)


def test_fiscal_quarters_merges_concepts():
    """Concept switching never drops fiscal years from the series."""
    cik = 1008
    asc = [_pt("2019-01-01", "2019-03-31", 20.7e6),
           _pt("2019-01-01", "2019-06-30", 39.8e6),
           _pt("2019-01-01", "2019-09-30", 59.7e6),
           _pt("2019-01-01", "2019-12-31", 85.5e6, form="10-K")]
    rev = [_pt("2024-01-01", "2024-03-31", 36.6e6),
           _pt("2024-01-01", "2024-12-31", 207.5e6, form="10-K")]
    http = _fake_http({_facts_url(cik): _income_facts(rev, asc606=asc)})
    qs = fetch_fiscal_quarters(cik, http_get=http)
    # FY2019 (ASC 606) fully derivable; FY2024 (Revenues) has only Q1
    # tagged -> exactly one quarter, and the year is never *lost*
    assert {q[0] for q in qs} == {2019, 2024}
    fy2019 = [q for q in qs if q[0] == 2019]
    assert [round(q[3], 1) for q in fy2019] == [20.7, 19.1, 19.9, 25.8]
    fy2024 = [q for q in qs if q[0] == 2024]
    assert [(q[1], round(q[3], 1)) for q in fy2024] == [(1, 36.6)]


def test_fiscal_quarters_empty_when_no_annual_anchor():
    cik = 1009
    pts = [_pt("2024-01-01", "2024-03-31", 36.6e6),
           _pt("2024-01-01", "2024-06-30", 83.9e6)]
    http = _fake_http({_facts_url(cik): _income_facts(pts)})
    assert fetch_fiscal_quarters(cik, http_get=http) == []
