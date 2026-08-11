"""q4cdn_adapter tests — fully offline (pdf_text_getter injected; no PDF/network).

Uses a real NVDA FY27 'Revenue by Market Platform' text fixture (captured via
PyMuPDF) and verifies both parsing and the internal caliber consistency
(Hyperscale + ACIE == Data Center; Data Center + Edge == TOTAL).
"""
import pytest

from revenue_model.q4cdn_adapter import (
    _parse_money, _clean_name, _extract_market_platform,
    fetch_market_platform, fiscal_year_rollup,
)

# Real NVDA text captured from the Q1 FY27 'Rev by Mkt Qtrly Trend' PDF.
NVDA_TEXT = """
===== Page 1 =====
Fiscal 2025
Fiscal 2026
Fiscal  
2027
($ in millions)
Q1 
Q2 
Q3 
Q4 
Q1 
Q2 
Q3 
Q4 
Q1 
Data Center1
$22,563
$26,272
$30,771
$35,580
$39,112
$41,096
$51,215
$62,314
$75,246
Hyperscale
10,690
10,622
13,390
19,094
17,599
23,883
30,340
33,814
37,869
AI Clouds,
Industrial, &
Enterprise
11,873
15,650
17,381
16,486
21,513
17,213
20,875
28,500
37,377
Edge Computing2
3,481
3,768
4,311
3,751
4,950
5,647
5,791
5,813
6,369
TOTAL
$26,044
$30,040
$35,082
$39,331
$44,062
$46,743
$57,006
$68,127
$81,615
NVIDIA QUARTERLY REVENUE 
REVENUE BY MARKET PLATFORM
Note: In the first quarter of fiscal year 2027, we changed our presentation.
1 Data Center will include two sub-markets, Hyperscale and ACIE.
2 Edge Computing highlights devices for agentic and physical AI.
"""


def test_parse_money():
    assert _parse_money("$22,563") == 22563.0
    assert _parse_money("10,690") == 10690.0
    assert _parse_money("") is None
    assert _parse_money("-") is None


def test_clean_name():
    assert _clean_name("Data Center1") == "Data Center"
    assert _clean_name("Edge Computing2") == "Edge Computing"
    assert _clean_name("AI Clouds,  Industrial, &  Enterprise") == "AI Clouds, Industrial, & Enterprise"


def test_extract_market_platform_quarters():
    _, quarters = _extract_market_platform(NVDA_TEXT)
    assert len(quarters) == 9
    assert quarters[0] == (2025, "Q1")
    assert quarters[4] == (2026, "Q1")
    assert quarters[-1] == (2027, "Q1")  # FY27 partial — only Q1


def test_extract_market_platform_values():
    data, _ = _extract_market_platform(NVDA_TEXT)
    assert "Data Center" in data
    assert data["Data Center"][(2025, "Q1")] == 22563.0
    assert data["Data Center"][(2027, "Q1")] == 75246.0
    assert data["Hyperscale"][(2025, "Q1")] == 10690.0
    assert data["TOTAL"][(2025, "Q1")] == 26044.0


def test_caliber_consistency():
    """The whole point — parsed numbers must satisfy NVDA's caliber identity:
    Hyperscale + ACIE == Data Center;  Data Center + Edge == TOTAL."""
    data, quarters = _extract_market_platform(NVDA_TEXT)
    dc, hyp = data["Data Center"], data["Hyperscale"]
    acie = data["AI Clouds, Industrial, & Enterprise"]
    edge, total = data["Edge Computing"], data["TOTAL"]
    for q in quarters:
        assert abs(dc[q] - (hyp[q] + acie[q])) < 1.0, f"DC != Hyper+ACIE at {q}"
        assert abs(total[q] - (dc[q] + edge[q])) < 1.0, f"TOTAL != DC+Edge at {q}"


def test_fiscal_year_rollup():
    data, _ = _extract_market_platform(NVDA_TEXT)
    dc_annual, dc_complete = fiscal_year_rollup(data["Data Center"])
    assert dc_annual[2025] == 22563 + 26272 + 30771 + 35580  # full year
    assert dc_annual[2026] == 39112 + 41096 + 51215 + 62314
    assert dc_annual[2027] == 75246  # partial — only Q1 reported
    assert dc_complete == {2025, 2026}     # M7: 2027 partial (1 of 4 quarters)
    assert 2027 not in dc_complete         # partial year must NOT be "complete"


def test_fetch_market_platform_injectable():
    data, quarters = fetch_market_platform(
        "dummy-url", pdf_text_getter=lambda url: NVDA_TEXT)
    assert data["Hyperscale"][(2026, "Q1")] == 17599.0
    assert len(quarters) == 9


def test_extract_empty_text():
    data, quarters = _extract_market_platform("no fiscal/quarter headers here")
    assert data == {}
    assert quarters == []


def test_note_in_middle_does_not_drop_items():
    # M5: a footnote appearing mid-table must be skipped, not abort the parse.
    # Previously the first _is_note hit did `break`, dropping every line item
    # after it. Edge Computing (after the note) must still be extracted.
    text = (
        "Fiscal 2025\n($ in millions)\nQ1\nQ2\nQ3\nQ4\n"
        "Data Center\n100\n200\n300\n400\n"
        "Note: DC includes AI revenue\n"
        "Edge Computing\n50\n60\n70\n80\n"
    )
    data, quarters = _extract_market_platform(text)
    assert "Data Center" in data
    assert "Edge Computing" in data      # would be lost under the old `break`
    assert len(quarters) == 4
