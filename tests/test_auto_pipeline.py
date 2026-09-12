"""Tests for revenue_model.auto_pipeline — the v0.20 offline spine."""

import os

import pytest

from revenue_model import auto_pipeline
from revenue_model.auto_pipeline import _build_segment

YEARS = [2026, 2027]

SEGMENTS = {
    "Core": {   # steady trend -> semiconductor family
        "base": {2021: 89.0, 2022: 100.0, 2023: 112.0, 2024: 124.0},
        "price": {2021: 0.99, 2022: 1.0, 2023: 1.02, 2024: 1.03},
    },
    "AI": {     # breakout -> regime-shift territory
        "base": {2021: 5.0, 2022: 10.0, 2023: 19.0, 2024: 36.0},
        # real adoption curve — needed when the tag's default is logistic:
        # a constant-1.0 penetration is "factor absent" and collides with
        # any S-curve anchor (documented in auto_pipeline's docstring)
        "penetration": {2021: 0.20, 2022: 0.30, 2023: 0.42, 2024: 0.55},
    },
}
TOTAL = {2021: 94.0, 2022: 110.0, 2023: 131.0, 2024: 160.0}


class TestBuildSegment:
    def test_missing_ratio_drivers_default_to_one(self):
        seg = _build_segment("X", {"base": {2024: 5.0}})
        assert seg.penetration.values == {2024: 1.0}
        assert seg.share.values == {2024: 1.0}
        assert seg.price.values == {2024: 1.0}

    def test_base_required(self):
        with pytest.raises(ValueError, match="base"):
            _build_segment("X", {"price": {2024: 1.0}})


class TestGates:
    def test_explicit_tags_forecast_everything(self, tmp_path):
        r = auto_pipeline(
            "DemoCo", SEGMENTS, TOTAL, YEARS,
            tags={"Core": "semiconductor", "AI": "regime_shift_tech"},
            report=str(tmp_path / "demo.docx"),
        )
        assert r.gate1_pending == ()
        assert r.model is not None
        assert len(r.segments) == 2
        assert r.tags_used["Core"] == "semiconductor"
        assert os.path.exists(r.report_path)

    def test_untagged_segment_parks_at_gate1(self):
        r = auto_pipeline(
            "DemoCo", SEGMENTS, TOTAL, YEARS,
            tags={"Core": "semiconductor"},          # AI left untagged
        )
        assert r.gate1_pending == ("AI",)
        assert "AI" not in r.tags_used
        assert len(r.segments) == 1                  # only Core forecast
        assert r.model is not None

    def test_all_untagged_no_model(self):
        r = auto_pipeline("DemoCo", SEGMENTS, TOTAL, YEARS)
        assert r.gate1_pending == ("Core", "AI")
        assert r.model is None
        assert r.segments == []

    def test_auto_tag_adopts_top_suggestion_loudly(self):
        r = auto_pipeline(
            "DemoCo", SEGMENTS, TOTAL, YEARS,
            tags={"Core": "semiconductor", "AI": "auto"},
        )
        assert r.auto_tagged == ("AI",)
        assert r.tags_used["AI"] == "regime_shift_tech"   # breakout prior
        assert r.gate1_pending == ()


class TestGate2:
    def test_above_band_without_story_pends(self):
        r = auto_pipeline(
            "DemoCo", SEGMENTS, TOTAL, YEARS,
            tags={"Core": "semiconductor",
                  "AI": "saas_subscription"},        # 60%+ CAGR vs band
        )
        assert "AI" in r.gate2_pending
        assert any("ABOVE the industry band" in w for w in r.warnings["AI"])

    def test_story_clears_the_gate(self):
        r = auto_pipeline(
            "DemoCo", SEGMENTS, TOTAL, YEARS,
            tags={"Core": "semiconductor", "AI": "saas_subscription"},
            stories={"AI": "AIP platform adoption is a new segment line"},
        )
        assert "AI" not in r.gate2_pending
        assert any("story on file" in w for w in r.warnings["AI"])


class TestSuggestions:
    def test_every_segment_gets_a_shortlist_when_backtestable(self):
        r = auto_pipeline(
            "DemoCo", SEGMENTS, TOTAL, YEARS,
            tags={"Core": "semiconductor", "AI": "regime_shift_tech"},
        )
        assert set(r.suggestions) == {"Core", "AI"}
        assert r.suggestions["AI"][0].key == "regime_shift_tech"

    def test_too_short_history_shortlist_empty_but_tag_still_works(self):
        segs = {"Short": {"base": {2023: 1.0, 2024: 2.0}}}
        r = auto_pipeline("Co", segs, {2023: 1.0, 2024: 2.0}, YEARS,
                          tags={"Short": "auto"})
        assert r.gate1_pending == ("Short",)        # nothing to adopt from
