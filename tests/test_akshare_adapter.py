"""Tests for akshare_adapter — fully offline via an injected fake ak module."""
import pandas as pd
import pytest
from revenue_model.akshare_adapter import (
    fetch_revenues_hk, fetch_company_name_hk, build_model_from_akshare)


class FakeAK:
    """A stand-in akshare module returning a canned report DataFrame."""
    def __init__(self, df):
        self._df = df

    def stock_financial_hk_report_em(self, stock, symbol, indicator):
        assert symbol == "利润表" and indicator == "年度"
        return self._df


# 腾讯 00700: 营业额 + 其他营业收入 (must be filtered out) + a NaN row (dropped).
_DF = pd.DataFrame([
    {"SECUCODE": "00700.HK", "SECURITY_NAME_ABBR": "腾讯控股",
     "REPORT_DATE": "2025-12-31 00:00:00", "STD_ITEM_NAME": "营业额", "AMOUNT": 743689000000.0},
    {"SECUCODE": "00700.HK", "SECURITY_NAME_ABBR": "腾讯控股",
     "REPORT_DATE": "2024-12-31 00:00:00", "STD_ITEM_NAME": "营业额", "AMOUNT": 660257000000.0},
    {"SECUCODE": "00700.HK", "SECURITY_NAME_ABBR": "腾讯控股",
     "REPORT_DATE": "2025-12-31 00:00:00", "STD_ITEM_NAME": "其他营业收入", "AMOUNT": 8077000000.0},
    {"SECUCODE": "00700.HK", "SECURITY_NAME_ABBR": "腾讯控股",
     "REPORT_DATE": "2025-12-31 00:00:00", "STD_ITEM_NAME": "销售费用", "AMOUNT": float("nan")},
])


def test_fetch_revenues_keeps_only_yingyee_and_drops_nan():
    rev = fetch_revenues_hk("00700", ak=FakeAK(_DF))
    assert rev == {2025: 743689000000.0, 2024: 660257000000.0}   # 其他营业收入 + NaN dropped


def test_fetch_revenues_empty_when_no_revenue_line():
    df = pd.DataFrame([{"SECURITY_NAME_ABBR": "X", "REPORT_DATE": "2025-12-31",
                        "STD_ITEM_NAME": "总资产", "AMOUNT": 1.0}])
    assert fetch_revenues_hk("00000", ak=FakeAK(df)) == {}


def test_fetch_company_name():
    assert fetch_company_name_hk("00700", ak=FakeAK(_DF)) == "腾讯控股"


def test_build_model_fills_total_in_million():
    model = build_model_from_akshare("00700", ak=FakeAK(_DF))
    assert model.company == "腾讯控股"
    assert model.years() == [2024, 2025]
    assert pytest.approx(model.total_revenue[2025], rel=1e-6) == 743689000000.0 / 1e6


def test_build_model_seeds_hk_intelligent_driving_template():
    model = build_model_from_akshare("00700", ak=FakeAK(_DF))
    assert [s.name for s in model.segments] == ["智能驾驶", "智能座舱"]
    for seg in model.segments:
        for d in seg.drivers():
            assert all(v == 0.0 for v in d.values.values())
            assert d.source.startswith("[adapter]")
            assert d.level == "C"
    assert "腾讯控股" in model.segments[0].share.name


def test_build_model_raises_when_no_revenue():
    df = pd.DataFrame([{"SECURITY_NAME_ABBR": "X", "REPORT_DATE": "2025-12-31",
                        "STD_ITEM_NAME": "总资产", "AMOUNT": 1.0}])
    with pytest.raises(ValueError, match="营业额"):
        build_model_from_akshare("00000", ak=FakeAK(df))
