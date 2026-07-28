"""Extractor tests — LLM call is mocked, so CI needs no key and no network."""

import json

import pytest

from revenue_model.extractor import (
    DRIVER_TYPES, build_prompt, parse_segments, extract_segments,
    alignment_check,
)

# A fabricated annual-report snippet (matches the NovaTech fictional demo).
# Real company data is never used in the repo — see DISCLAIMER.md.
NOVATECH_TEXT = """\
NovaTech（虚构示例）2024 年年度报告
报告期内，公司实现主营业务收入 41,000.00 万元，同比增长 28.1%。
(1) 舱内-国内业务实现营业收入 19,660.00 万元，毛利率 88.2%；
(2) 舱内-海外业务实现营业收入 12,000.00 万元，毛利率 85.5%。
主营业务分产品情况：
分产品 | 营业收入(元) | 营业成本(元) | 毛利率(%) | 收入同比(%)
舱内-国内 | 196,600,000 | 23,200,000 | 88.2 | 25.3
舱内-海外 | 120,000,000 | 17,400,000 | 85.5 | 40.1
其他 | 93,400,000 | 8,900,000 | 90.5 | 10.2
"""

MOCK_LLM_JSON = {
    "company": "NovaTech",
    "fiscal_year": 2024,
    "total_revenue": 410000000,
    "segments": [
        {"name": "舱内-国内", "revenue": 196600000, "share": 0.480, "yoy": 0.253,
         "gross_margin": 0.882, "driver_type": "hardware_product",
         "driver_hints": {"base": "China passenger car sales",
                          "penetration": "cockpit penetration",
                          "share": "NovaTech share", "price": "ASP"},
         "evidence": "舱内-国内 196,600,000 毛利率 88.2%", "confidence": "A"},
        {"name": "舱内-海外", "revenue": 120000000, "share": 0.293, "yoy": 0.401,
         "gross_margin": 0.855, "driver_type": "hardware_product",
         "driver_hints": {"base": "Europe passenger car sales",
                          "penetration": "cockpit penetration",
                          "share": "NovaTech share", "price": "ASP"},
         "evidence": "舱内-海外 120,000,000 毛利率 85.5%", "confidence": "A"},
    ],
    "unmodeled": {"name": "其他", "revenue": 93400000, "share": 0.228,
                  "note": "goes to residual line"},
}


def _mock_llm(messages):
    # A real LLM would read the text; the mock just echoes a fixed valid answer.
    return json.dumps(MOCK_LLM_JSON, ensure_ascii=False)


def test_driver_types_vocab_complete():
    assert len(DRIVER_TYPES) == 6
    for k, v in DRIVER_TYPES.items():
        assert "×" in v  # each maps to a driver tree


def test_build_prompt_has_schema_vocab_and_text():
    msgs = build_prompt(NOVATECH_TEXT)
    assert msgs[0]["role"] == "system"
    user = msgs[1]["content"]
    for key in DRIVER_TYPES:                    # controlled vocab present
        assert key in user
    assert "舱内-国内" in user                   # input text injected
    assert "share" in user and "evidence" in user  # schema fields present


def test_parse_segments_valid_and_aligned():
    parsed = parse_segments(json.dumps(MOCK_LLM_JSON, ensure_ascii=False))
    assert parsed["company"] == "NovaTech"
    assert len(parsed["segments"]) == 2
    assert parsed["_aligned"] is True            # 0.480 + 0.293 + 0.228 ≈ 1.001
    assert abs(parsed["_share_sum"] - 1.0) < 0.02


def test_parse_segments_flags_misalignment():
    bad = json.loads(json.dumps(MOCK_LLM_JSON, ensure_ascii=False))
    bad["segments"][0]["share"] = 0.10           # break the sum
    parsed = parse_segments(json.dumps(bad, ensure_ascii=False))
    assert parsed["_aligned"] is False


def test_extract_with_mock_llm():
    parsed = extract_segments(NOVATECH_TEXT, llm=_mock_llm)
    assert parsed["segments"][0]["driver_type"] == "hardware_product"
    assert parsed["segments"][0]["confidence"] == "A"
    assert parsed["_aligned"] is True


def test_extract_requires_key_or_llm():
    with pytest.raises(ValueError):
        extract_segments(NOVATECH_TEXT)          # neither api_key nor llm


def test_alignment_check_residual_holds():
    parsed = json.loads(json.dumps(MOCK_LLM_JSON, ensure_ascii=False))
    rep = alignment_check(parsed)
    # Σ segments 316.6M + unmodeled 93.4M = 410M reported total
    assert rep["segment_sum"] == pytest.approx(316_600_000)
    assert rep["residual"] == pytest.approx(93_400_000)
    assert rep["residual_ratio"] == pytest.approx(0.228, abs=0.01)
    assert rep["aligned"] is True
