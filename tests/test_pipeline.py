"""Tests for the end-to-end pipeline: templates, parsed_to_segments, from_report."""
import json

from revenue_model.templates import DRIVER_TEMPLATES, get_template
from revenue_model.pipeline import parsed_to_segments
from revenue_model.model import RevenueModel
from revenue_model.driver import BASE, PENETRATION, SHARE, PRICE


# -------------------------------- templates ------------------------------- #

def test_all_six_templates_present():
    expected = {"hardware_product", "software_subscription", "service_project",
                "advertising", "financial_interest", "retail_store"}
    assert expected == set(DRIVER_TEMPLATES)


def test_each_template_has_four_factors():
    for dtype, tpl in DRIVER_TEMPLATES.items():
        assert set(tpl) == {BASE, PENETRATION, SHARE, PRICE}, dtype
        for kind, (unit, hint) in tpl.items():
            assert isinstance(unit, str) and unit
            assert isinstance(hint, str) and hint


def test_get_template_unknown_raises():
    try:
        get_template("nonexistent")
    except KeyError:
        return
    raise AssertionError("expected KeyError for unknown driver_type")


# --------------------------- parsed_to_segments --------------------------- #

def _sample_parsed():
    return {
        "company": "DemoCo",
        "fiscal_year": 2024,
        "total_revenue": 500_000_000,
        "segments": [
            {"name": "software", "revenue": 300e6, "share": 0.6, "yoy": 0.2,
             "gross_margin": 0.7, "driver_type": "software_subscription",
             "driver_hints": {"base": "paying customers", "price": "ARPU ~800 yuan"},
             "evidence": "软件收入 3 亿元", "confidence": "A"},
            {"name": "hardware", "revenue": 150e6, "share": 0.3, "yoy": 0.1,
             "gross_margin": 0.3, "driver_type": "hardware_product",
             "driver_hints": {}, "confidence": "B"},
        ],
        "unmodeled": {"name": "other", "revenue": 50e6, "share": 0.1, "note": "residual"},
    }


def test_parsed_to_segments_structure():
    segs = parsed_to_segments(_sample_parsed(), 2024)
    assert len(segs) == 2
    assert segs[0].name == "software"
    assert segs[1].name == "hardware"
    # each segment has the four driver kinds
    for s in segs:
        kinds = {d.kind for d in s.drivers()}
        assert kinds == {BASE, PENETRATION, SHARE, PRICE}


def test_parsed_to_segments_uses_hints_as_names():
    segs = parsed_to_segments(_sample_parsed(), 2024)
    sw = segs[0]
    by_kind = {d.kind: d for d in sw.drivers()}
    assert by_kind[BASE].name == "paying customers"      # from driver_hints
    assert by_kind[PRICE].name == "ARPU ~800 yuan"        # from driver_hints
    # penetration had no hint -> falls back to template name_hint
    assert by_kind[PENETRATION].name == "adoption rate"


def test_parsed_to_segments_placeholder_values_and_source():
    segs = parsed_to_segments(_sample_parsed(), 2024)
    for s in segs:
        for d in s.drivers():
            assert d.values == {2024: 0.0}                # placeholder
            assert "[skeleton]" in d.source               # tagged for human fill


def test_parsed_to_segments_unknown_driver_type_falls_back():
    parsed = _sample_parsed()
    parsed["segments"][0]["driver_type"] = "spaceship_revenue"
    segs = parsed_to_segments(parsed, 2024)
    assert len(segs) == 2                                  # did not crash


# ------------------------------ from_report ------------------------------- #

def _fake_llm(messages):
    """A stand-in LLM returning a schema-valid JSON string (no network)."""
    return json.dumps(_sample_parsed())


def test_from_report_end_to_end_with_fake_llm():
    model = RevenueModel.from_report("some annual-report text", llm=_fake_llm)
    assert model.company == "DemoCo"
    assert len(model.segments) == 2
    # total_revenue converted from yuan -> million yuan
    assert model.total_revenue == {2024: 500.0}
    # alignment check runs (residual = total since driver values are 0 placeholders)
    r = model.validate(2024)
    assert r.segment_sum == 0.0
    assert abs(r.residual - 500.0) < 1e-9
    assert r.residual_ratio > 0.99                        # everything un-modeled -> flagged


def test_from_report_respects_explicit_year():
    model = RevenueModel.from_report("text", llm=_fake_llm, year=2023)
    # placeholders keyed on the explicit year
    for s in model.segments:
        for d in s.drivers():
            assert 2023 in d.values
