"""Tests for sec_adapter — fully offline via an injected fake http_get."""
import pytest
from revenue_model.sec_adapter import (
    fetch_cik, fetch_revenues, build_model_from_sec, _is_annual,
    fetch_company_facts, fetch_statement, _dedupe_by_period, _period_from_end,
    _is_true_annual, SEC_WWW, SEC_API)


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


# ---- extended: company_facts + full statements + single-Q (v0.8) -----------
# Minimal companyfacts fixture: Revenues + NetIncomeLoss (flow, with start) +
# CashAndCashEquivalents (instant, start=None). Values in raw USD.
_COMPANYFACTS = {
    "cik": 1490978, "entityName": "Test Co",
    "facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [
            {"start": "2022-01-01", "end": "2022-12-31", "form": "10-K", "fy": 2022, "filed": "2023-03-01", "val": 800_000_000},
            {"start": "2023-01-01", "end": "2023-12-31", "form": "10-K", "fy": 2023, "filed": "2024-03-01", "val": 1_000_000_000},
            {"start": "2023-01-01", "end": "2023-03-31", "form": "10-Q", "fy": 2023, "fp": "Q1", "filed": "2023-05-01", "val": 200_000_000},
            {"start": "2023-01-01", "end": "2023-06-30", "form": "10-Q", "fy": 2023, "fp": "Q2", "filed": "2023-08-01", "val": 450_000_000},
            {"start": "2023-01-01", "end": "2023-09-30", "form": "10-Q", "fy": 2023, "fp": "Q3", "filed": "2023-11-01", "val": 720_000_000},
        ]}},
        "NetIncomeLoss": {"units": {"USD": [
            {"start": "2023-01-01", "end": "2023-12-31", "form": "10-K", "fy": 2023, "filed": "2024-03-01", "val": -50_000_000},
            {"start": "2023-01-01", "end": "2023-03-31", "form": "10-Q", "fy": 2023, "fp": "Q1", "filed": "2023-05-01", "val": -20_000_000},
            {"start": "2023-01-01", "end": "2023-06-30", "form": "10-Q", "fy": 2023, "fp": "Q2", "filed": "2023-08-01", "val": -30_000_000},
            {"start": "2023-01-01", "end": "2023-09-30", "form": "10-Q", "fy": 2023, "fp": "Q3", "filed": "2023-11-01", "val": -45_000_000},
        ]}},
        "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [
            {"end": "2022-12-31", "form": "10-K", "fy": 2022, "filed": "2023-03-01", "val": 300_000_000},
            {"end": "2023-12-31", "form": "10-K", "fy": 2023, "filed": "2024-03-01", "val": 400_000_000},
        ]}},
    }},
}
_CIK = 1490978
_FACTS_URL = f"{SEC_API}/api/xbrl/companyfacts/CIK{_CIK:010d}.json"


def _facts_http():
    return _fake_http({_FACTS_URL: _COMPANYFACTS})


def test_dedupe_keeps_latest_filed_same_period():
    pts = [
        {"start": "2023-01-01", "end": "2023-12-31", "filed": "2024-03-01", "val": 1},
        {"start": "2023-01-01", "end": "2023-12-31", "filed": "2025-03-01", "val": 2},
    ]
    out = _dedupe_by_period(pts)
    assert out[("2023-01-01", "2023-12-31")]["val"] == 2


def test_dedupe_handles_instant_no_start():
    out = _dedupe_by_period([{"end": "2023-12-31", "filed": "2024-03-01", "val": 5}])
    assert out[("", "2023-12-31")]["val"] == 5


def test_period_from_end_calendar():
    assert _period_from_end("2023-12-31") == (2023, "FY")
    assert _period_from_end("2023-03-31") == (2023, "Q1")
    assert _period_from_end("2023-06-30") == (2023, "Q2")
    assert _period_from_end("2023-09-30") == (2023, "Q3")


def test_fetch_company_facts_returns_payload():
    facts = fetch_company_facts(_CIK, http_get=_facts_http())
    assert facts["entityName"] == "Test Co"
    assert "Revenues" in facts["facts"]["us-gaap"]


def test_fetch_statement_annual_income():
    stmt = fetch_statement(_CIK, "income", "annual", http_get=_facts_http())
    assert stmt[(2023, "FY")]["Revenue"] == 1000.0      # 1e9 -> million
    assert stmt[(2023, "FY")]["Net Income"] == -50.0


def test_fetch_statement_quarterly_ytd():
    stmt = fetch_statement(_CIK, "income", "quarterly", http_get=_facts_http())
    assert stmt[(2023, "Q2")]["Revenue"] == 450.0        # YTD cumulative


def test_fetch_statement_single_quarter_derivation():
    stmt = fetch_statement(_CIK, "income", "quarterly",
                           single_quarter=True, http_get=_facts_http())
    assert stmt[(2023, "Q1")]["Revenue"] == 200.0        # Q1 = Q1_YTD
    assert stmt[(2023, "Q2")]["Revenue"] == 250.0        # 450 - 200
    assert stmt[(2023, "Q4")]["Revenue"] == 280.0        # FY(1000) - Q3_YTD(720)


def test_fetch_statement_balance_instant_items():
    stmt = fetch_statement(_CIK, "balance", "annual", http_get=_facts_http())
    assert stmt[(2023, "FY")]["Cash & Equivalents"] == 400.0


def test_fetch_statement_rejects_invalid_kind():
    with pytest.raises(ValueError, match="statement must be"):
        fetch_statement(_CIK, "bogus", http_get=_facts_http())


def test_fetch_statement_missing_concept_is_none():
    # GrossProfit absent from fixture -> metric present with None value
    stmt = fetch_statement(_CIK, "income", "annual", http_get=_facts_http())
    assert stmt[(2023, "FY")].get("Gross Profit") is None


# ---- bug A/B regression: Q4 comparative must not masquerade as FY ----------
def test_is_true_annual_duration_check():
    assert _is_true_annual("2023-01-01", "2023-12-31") is True    # 364d full year
    assert _is_true_annual("2023-10-01", "2023-12-31") is False   # 91d Q4 comparative
    assert _is_true_annual("", "2023-12-31") is True              # instant (balance)
    assert _is_true_annual("2023-01-01", "2023-03-31") is False   # quarterly


def test_fetch_statement_filters_q4_comparative_from_annual():
    """A 10-K income statement carries a 'year ended' (12mo) column AND a
    'three months ended Dec 31' (Q4) comparative. Both end in December — the
    3-month row must NOT be treated as FY (would overwrite the real annual)."""
    facts = {
        "cik": _CIK, "entityName": "Test Co",
        "facts": {"us-gaap": {
            "Revenues": {"units": {"USD": [
                {"start": "2023-01-01", "end": "2023-12-31", "form": "10-K", "fy": 2023, "filed": "2024-03-01", "val": 1_000_000_000},
                {"start": "2023-10-01", "end": "2023-12-31", "form": "10-K", "fy": 2023, "filed": "2024-03-01", "val": 300_000_000},
            ]}},
        }},
    }
    stmt = fetch_statement(_CIK, "income", "annual",
                           http_get=_fake_http({_FACTS_URL: facts}))
    assert stmt[(2023, "FY")]["Revenue"] == 1000.0   # full year, not 300 (3-month)
