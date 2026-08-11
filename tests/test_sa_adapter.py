"""sa_adapter tests — fully offline (table_extractor injected; no browser/network).

Covers the pure parser, the injectable build path, and the Segment reported
anchor precedence (history-first).
"""
import pytest

from revenue_model.sa_adapter import (
    _parse_money, _extract_segment_revenue, fetch_segments_sa, build_model_from_sa,
)

# Real NVDA fixture captured from stockanalysis.com (FY22-FY26, million USD).
NVDA_TABLES = [
    {
        "caption": "Revenue & Profits",
        "headers": ["Fiscal Year", "TTM", "FY 2026", "FY 2025", "FY 2024",
                    "FY 2023", "FY 2022", "Period Ending", "Apr 26, 2026",
                    "Jan 25, 2026", "Jan 26, 2025", "Jan 28, 2024",
                    "Jan 29, 2023", "Jan 30, 2022"],
        "rows": [["Revenue", "253,491", "215,938", "130,497", "60,922",
                  "26,974", "26,914"]],
    },
    {
        "caption": "Revenue by Segment",
        "headers": ["Fiscal Year", "TTM", "FY 2026", "FY 2025", "FY 2024",
                    "FY 2023", "FY 2022", "Period Ending", "Apr 26, 2026",
                    "Jan 25, 2026", "Jan 26, 2025", "Jan 28, 2024",
                    "Jan 29, 2023", "Jan 30, 2022"],
        "rows": [
            ["Compute & Networking", "228,440", "193,479", "116,193", "47,405",
             "15,068", "11,046"],
            ["Graphics", "25,051", "22,459", "14,304", "13,517", "11,906", "15,868"],
            ["Revenue (Total)", "253,491", "215,938", "130,497", "60,922",
             "26,974", "26,914"],
        ],
    },
]


def _extractor(_tables=NVDA_TABLES):
    return lambda url: _tables


def test_parse_money():
    assert _parse_money("$193,479") == 193479.0
    assert _parse_money("193,479") == 193479.0
    assert _parse_money("11,046") == 11046.0
    assert _parse_money("") is None
    assert _parse_money("-") is None
    assert _parse_money("N/A") is None


def test_extract_segment_revenue():
    segs, total = _extract_segment_revenue(NVDA_TABLES)
    assert "Compute & Networking" in segs
    assert "Graphics" in segs
    assert segs["Compute & Networking"][2026] == 193479.0
    assert segs["Compute & Networking"][2022] == 11046.0
    assert segs["Graphics"][2025] == 14304.0
    # Total row separated out, not mixed into segments
    assert "Revenue (Total)" not in segs
    assert total[2026] == 215938.0
    assert total[2022] == 26914.0
    # TTM column (no 'FY' in header) is excluded from year map
    assert all(y > 2000 for y in total)


def test_extract_raises_when_no_segment_table():
    with pytest.raises(ValueError, match="Revenue by Segment"):
        _extract_segment_revenue([{"caption": "Other", "headers": [], "rows": []}])


def test_fetch_segments_sa_injectable():
    segs, total = fetch_segments_sa("NVDA", table_extractor=_extractor())
    assert segs["Graphics"][2024] == 13517.0
    assert total[2024] == 60922.0


def test_build_model_from_sa_injectable():
    model = build_model_from_sa("NVDA", table_extractor=_extractor())
    assert model.company == "NVDA"
    assert {s.name for s in model.segments} == {"Compute & Networking", "Graphics"}
    # reported anchor precedence: revenue(2026) is the reported figure, not the
    # driver product (which would be 0 from placeholders)
    cn = next(s for s in model.segments if "Compute" in s.name)
    assert cn.revenue(2026) == 193479.0
    assert cn.revenue_source(2026) == "reported"
    assert cn.revenue_source(2099) == "drivers"  # no reported -> driver layer
    # total anchor
    assert model.total_revenue[2026] == 215938.0
    # Σ reported segments == reported total -> residual ~ 0 (caliber-consistent)
    r = model.validate(2026)
    assert abs(r.residual) < 1.0


def test_build_model_year_filter():
    model = build_model_from_sa("NVDA", table_extractor=_extractor(),
                                years=[2024, 2025])
    assert model.years() == [2024, 2025]


def test_sa_cache_behavior_default_getter_cached(monkeypatch, tmp_path):
    """Default extractor (None) + use_cache -> tables cached; 2nd call hits cache;
    refresh re-fetches; injected extractor bypasses the cache entirely."""
    monkeypatch.setenv("RMB_CACHE_DIR", str(tmp_path))
    calls = []

    def fake_default(url, **kw):
        calls.append(url)
        return NVDA_TABLES

    monkeypatch.setattr("revenue_model.sa_adapter._default_table_extractor", fake_default)

    segs1, _ = fetch_segments_sa("NVDA", use_cache=True)   # miss -> fetch + cache
    assert len(calls) == 1
    segs2, _ = fetch_segments_sa("NVDA", use_cache=True)   # hit -> no fetch
    assert len(calls) == 1
    assert segs1 == segs2
    fetch_segments_sa("NVDA", use_cache=True, refresh=True)  # refresh -> re-fetch
    assert len(calls) == 2
    # injected extractor bypasses the cache (default never called)
    fetch_segments_sa("NVDA", table_extractor=lambda url: NVDA_TABLES, use_cache=True)
    assert len(calls) == 2


def test_build_model_raises_when_total_label_unrecognized():
    # M1: total row uses 'Net Revenue' (a variant sa_adapter won't recognize),
    # but segments have data. Must raise instead of returning a half-built
    # model (which would later cause validate() KeyError on empty years()).
    tables = [{
        "caption": "Revenue by Segment",
        "headers": ["Fiscal Year", "FY 2025", "Period Ending", "Jan 26, 2025"],
        "rows": [
            ["Compute & Networking", "193,479"],
            ["Graphics", "22,459"],
            ["Net Revenue", "215,938"],     # unrecognized total variant
        ],
    }]
    with pytest.raises(ValueError, match="no total row"):
        build_model_from_sa("TEST", table_extractor=lambda url: tables)
