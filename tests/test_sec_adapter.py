"""Tests for sec_adapter — fully offline via an injected fake http_get."""
import pytest
from revenue_model.sec_adapter import (
    fetch_cik, fetch_revenues, build_model_from_sec, _is_annual,
    SEC_WWW, SEC_API)


def _fake_http(routes):
    """fake http_get(url, timeout) -> dict, matches by exact url."""
    def http_get(url, timeout):
        if url in routes:
            return routes[url]
        raise ValueError(f"unexpected url: {url}")
    return http_get


_TICKERS = {"0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."}}

# Apple FY2018: full-year 265.6B (period 369d) MUST be kept;
# Q4-only 62.9B (period 91d, also form=10-K) MUST be filtered out;
# FY2017 full-year 229.2B kept.
_REV_AAPL = {"units": {"USD": [
    {"start": "2017-09-25", "end": "2018-09-29", "form": "10-K", "fy": 2018, "val": 265595000000},
    {"start": "2018-06-30", "end": "2018-09-29", "form": "10-K", "fy": 2018, "val": 62900000000},
    {"start": "2016-09-25", "end": "2017-09-30", "form": "10-K", "fy": 2017, "val": 229234000000},
]}}


# ---- _is_annual: the key data-cleaning predicate ---------------------------
def test_is_annual_keeps_full_year_drops_quarter():
    assert _is_annual({"form": "10-K", "start": "2017-09-25", "end": "2018-09-29"}) is True   # 369d
    assert _is_annual({"form": "10-K", "start": "2018-06-30", "end": "2018-09-29"}) is False  # 91d
    assert _is_annual({"form": "10-Q", "start": "2017-09-25", "end": "2018-09-29"}) is False  # not 10-K
    assert _is_annual({"form": "10-K"}) is False                                               # no dates


# ---- fetch_cik -------------------------------------------------------------
def test_fetch_cik_finds_ticker():
    http = _fake_http({f"{SEC_WWW}/files/company_tickers.json": _TICKERS})
    assert fetch_cik("AAPL", http_get=http) == (320193, "Apple Inc.")


def test_fetch_cik_case_insensitive():
    http = _fake_http({f"{SEC_WWW}/files/company_tickers.json": _TICKERS})
    assert fetch_cik("aapl", http_get=http)[0] == 320193


def test_fetch_cik_raises_on_unknown_ticker():
    http = _fake_http({f"{SEC_WWW}/files/company_tickers.json": _TICKERS})
    with pytest.raises(ValueError, match="not found"):
        fetch_cik("NOPE", http_get=http)


# ---- fetch_revenues: annual-only filter + ASC 606 fallback -----------------
def test_fetch_revenues_keeps_only_full_year_rows():
    cik10 = "0000320193"
    http = _fake_http({
        f"{SEC_API}/api/xbrl/companyconcept/CIK{cik10}/us-gaap/Revenues.json": _REV_AAPL,
    })
    rev = fetch_revenues(320193, http_get=http)
    assert rev == {2018: 265595000000, 2017: 229234000000}   # 62.9B Q4 dropped


def test_fetch_revenues_falls_back_when_first_concept_missing():
    """Revenues endpoint 404s -> adapter falls back to the ASC 606 element."""
    cik10 = "0000320193"
    asc606 = {"units": {"USD": [
        {"start": "2017-09-25", "end": "2018-09-29", "form": "10-K", "fy": 2018, "val": 260170000000},
    ]}}

    def http_get(url, timeout):
        if "Revenues.json" in url:
            raise FileNotFoundError("404")        # first concept absent
        if "RevenueFromContract" in url:
            return asc606
        raise ValueError(url)
    assert fetch_revenues(320193, http_get=http_get) == {2018: 260170000000}


# ---- build_model_from_sec: anchor in million USD, US template --------------
def _full_http():
    return _fake_http({
        f"{SEC_WWW}/files/company_tickers.json": _TICKERS,
        f"{SEC_API}/api/xbrl/companyconcept/CIK0000320193/us-gaap/Revenues.json": _REV_AAPL,
    })


def test_build_model_fills_total_revenue_in_million_usd():
    model = build_model_from_sec("AAPL", http_get=_full_http())
    assert model.company == "Apple Inc."
    assert model.years() == [2017, 2018]
    assert pytest.approx(model.total_revenue[2018], rel=1e-6) == 265595000000 / 1e6


def test_build_model_seeds_us_intelligent_driving_template():
    model = build_model_from_sec("AAPL", http_get=_full_http())
    assert [s.name for s in model.segments] == ["Intelligent Driving", "Intelligent Cockpit"]
    for seg in model.segments:
        for d in seg.drivers():
            assert all(v == 0.0 for v in d.values.values())
            assert d.source.startswith("[adapter]")
            assert d.level == "C"
    assert "Apple Inc." in model.segments[0].share.name


def test_build_model_raises_when_no_revenue():
    http = _fake_http({
        f"{SEC_WWW}/files/company_tickers.json": _TICKERS,
        f"{SEC_API}/api/xbrl/companyconcept/CIK0000320193/us-gaap/Revenues.json": {"units": {"USD": []}},
        f"{SEC_API}/api/xbrl/companyconcept/CIK0000320193/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json": {"units": {"USD": []}},
    })
    with pytest.raises(ValueError, match="no annual revenue"):
        build_model_from_sec("AAPL", http_get=http)
