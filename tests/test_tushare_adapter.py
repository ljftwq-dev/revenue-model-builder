"""Tests for tushare_adapter — fully offline, via an injected fake http_get.

No network, no token: the fake dispatches on ``api_name`` and returns canned
tushare-shaped payloads. Mirrors extractor's ``llm=`` injection pattern.
"""
import json
import pytest
from revenue_model.tushare_adapter import (
    fetch_income, fetch_company_name, build_model_from_tushare, TUSHARE_URL)


def _fake_http(responses):
    """fake http_get(url, payload_dict, timeout) -> dict, dispatch on api_name."""
    def http_get(url, payload, timeout):
        assert url == TUSHARE_URL
        body = payload if isinstance(payload, dict) else json.loads(payload)
        return responses.get(body["api_name"], {"data": {"fields": [], "items": []}})
    return http_get


# ---- fetch_income: keep only annual reports (end_date YYYY1231) ------------
def test_fetch_income_keeps_only_annual_reports():
    http = _fake_http({"income": {"data": {"fields": ["end_date", "revenue"], "items": [
        ["20241231", 1688e8], ["20240930", 1200e8],
        ["20231231", 1500e8], ["20240630", 700e8],
    ]}}})
    inc = fetch_income("600519.SH", "tok", http_get=http)
    assert inc == {2024: 1688e8, 2023: 1500e8}   # quarters filtered out


def test_fetch_income_empty_when_no_data():
    assert fetch_income("000000.SZ", "tok", http_get=_fake_http({})) == {}


# ---- fetch_company_name: returns name; falls back to ts_code on error ------
def test_fetch_company_name_ok():
    http = _fake_http({"stock_basic": {"data": {"fields": ["ts_code", "name"],
                                               "items": [["002405.SZ", "德赛西威"]]}}})
    assert fetch_company_name("002405.SZ", "tok", http_get=http) == "德赛西威"


def test_fetch_company_name_falls_back_to_ts_code_on_ssl_error():
    def boom(url, payload, timeout):
        raise RuntimeError("SSL UNEXPECTED_EOF")
    assert fetch_company_name("002405.SZ", "tok", http_get=boom) == "002405.SZ"


# ---- build_model_from_tushare: anchor filled, drivers are placeholders -----
def _fake_full():
    return _fake_http({
        "income": {"data": {"fields": ["end_date", "revenue"], "items": [
            ["20241231", 1696.0e8], ["20231231", 2200.0e8]]}},
        "stock_basic": {"data": {"fields": ["ts_code", "name"],
                                 "items": [["002405.SZ", "德赛西威"]]}},
    })


def test_build_model_fills_total_revenue_in_million_yuan():
    model = build_model_from_tushare("002405.SZ", token="tok", http_get=_fake_full())
    assert model.company == "德赛西威"
    assert model.years() == [2023, 2024]
    # 1696e8 yuan == 16960 million yuan (the engine's unit)
    assert pytest.approx(model.total_revenue[2024], rel=1e-6) == 1696.0e8 / 1e6


def test_build_model_seeds_intelligent_driving_segments():
    model = build_model_from_tushare("002405.SZ", token="tok", http_get=_fake_full())
    assert [s.name for s in model.segments] == ["智能驾驶", "智能座舱"]
    for seg in model.segments:                      # every driver is a placeholder
        assert len(seg.drivers()) == 4
        for d in seg.drivers():
            assert all(v == 0.0 for v in d.values.values())
            assert d.source.startswith("[adapter]")
            assert d.level == "C"


def test_build_model_pre_fills_industry_sources_and_urls():
    model = build_model_from_tushare("002405.SZ", token="tok", http_get=_fake_full())
    adas = model.segments[0]                        # 智能驾驶
    assert adas.base.source_url == "http://www.caam.org.cn"
    assert adas.penetration.source_url == "http://www.gg-ii.com"
    assert "德赛西威" in adas.share.name             # company interpolated into share name


def test_build_model_raises_when_no_annual_income():
    with pytest.raises(ValueError, match="no annual data"):
        build_model_from_tushare("000000.SZ", token="tok", http_get=_fake_http({}))


def test_build_model_years_filter_keeps_only_requested():
    model = build_model_from_tushare("002405.SZ", token="tok",
                                     years=[2024], http_get=_fake_full())
    assert model.years() == [2024]
