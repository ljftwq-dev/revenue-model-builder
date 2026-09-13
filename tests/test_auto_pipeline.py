"""Tests for revenue_model.auto_pipeline — the v0.20 offline spine."""

import os

import pytest

from revenue_model import auto_pipeline
from revenue_model.auto_pipeline import _build_segment
from revenue_model.gate import GateBook

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


# ---------------------------------------------------------------------------
# v0.20b: SEC auto total revenue (injected http_get, zero network)
# ---------------------------------------------------------------------------

def _fake_http(payload_by_url):
    """http_get injector: matches by URL substring, fails loudly otherwise."""
    def _get(url, timeout):
        for frag, data in payload_by_url.items():
            if frag in url:
                return data
        raise OSError(f"unexpected url {url}")
    return _get


_TICKERS = {"0": {"cik_str": 1321655, "ticker": "DEMO", "title": "Demo Inc"}}
_FACTS = {
    "units": {"USD": [
        {"form": "10-K", "start": "2021-01-01", "end": "2021-12-31",
         "fy": 2021, "fp": "FY", "val": 94_000_000},
        {"form": "10-K", "start": "2022-01-01", "end": "2022-12-31",
         "fy": 2022, "fp": "FY", "val": 110_000_000},
        {"form": "10-K", "start": "2023-01-01", "end": "2023-12-31",
         "fy": 2023, "fp": "FY", "val": 131_000_000},
        {"form": "10-K", "start": "2024-01-01", "end": "2024-12-31",
         "fy": 2024, "fp": "FY", "val": 160_000_000},
    ]},
}


class TestSecAutoTotal:
    def test_auto_fetch_fills_total(self):
        http = _fake_http({
            "company_tickers.json": _TICKERS,
            "companyconcept": _FACTS,
        })
        r = auto_pipeline(
            "DEMO", SEGMENTS, total_revenue=None, years=YEARS,
            tags={"Core": "semiconductor", "AI": "auto"}, http_get=http)
        assert r.total_source == "SEC EDGAR (auto)"
        assert r.model.total_revenue[2024] == 160.0   # $M

    def test_explicit_total_skips_the_fetch(self):
        def _boom(url, timeout):
            raise AssertionError("network must not be touched")
        r = auto_pipeline(
            "DemoCo", SEGMENTS, TOTAL, YEARS,
            tags={"Core": "semiconductor", "AI": "auto"}, http_get=_boom)
        assert r.total_source == "manual"

    def test_unknown_ticker_degrades_loudly(self):
        http = _fake_http({"company_tickers.json": _TICKERS})
        with pytest.raises(ValueError, match="total_revenue"):
            auto_pipeline("NOPE", SEGMENTS, total_revenue=None, years=YEARS,
                          http_get=http)

    def test_years_required(self):
        with pytest.raises(ValueError, match="years"):
            auto_pipeline("Co", SEGMENTS, TOTAL)


class TestMomentumWiring:
    def test_momentum_stage_runs_when_auto_fetch(self, monkeypatch):
        from revenue_model import momentum as mom
        reading = mom.MomentumReading(
            "accelerating", 0.55, 0.20, 12, "TTM growth +55%/yr vs +20%")
        monkeypatch.setattr(mom, "quarterly_momentum", lambda *a, **k: reading)
        http = _fake_http({"company_tickers.json": _TICKERS,
                           "companyconcept": _FACTS})
        r = auto_pipeline("DEMO", SEGMENTS, total_revenue=None, years=YEARS,
                          tags={"Core": "semiconductor", "AI": "auto"},
                          http_get=http)
        assert r.momentum is not None
        assert r.momentum.state == "accelerating"

    def test_momentum_failure_degrades_softly(self, monkeypatch):
        from revenue_model import momentum as mom

        def _boom(*a, **k):
            raise OSError("network down")
        monkeypatch.setattr(mom, "quarterly_momentum", _boom)
        http = _fake_http({"company_tickers.json": _TICKERS,
                           "companyconcept": _FACTS})
        r = auto_pipeline("DEMO", SEGMENTS, total_revenue=None, years=YEARS,
                          tags={"Core": "semiconductor"}, http_get=http)
        assert r.momentum is None          # soft skip, spine unaffected
        assert r.model is not None

    def test_momentum_disabled(self, monkeypatch):
        from revenue_model import momentum as mom
        called = []
        monkeypatch.setattr(mom, "quarterly_momentum",
                            lambda *a, **k: called.append(1))
        http = _fake_http({"company_tickers.json": _TICKERS,
                           "companyconcept": _FACTS})
        auto_pipeline("DEMO", SEGMENTS, total_revenue=None, years=YEARS,
                      tags={"Core": "semiconductor"}, http_get=http,
                      momentum_enabled=False)
        assert called == []                # really off, not silently skipped


# ---------------------------------------------------------------------------
# v0.21b: evidence stage wiring (offline, injected backend)
# ---------------------------------------------------------------------------

def _evidence_backend(page_text, file_name, page_no):
    if "Revenue grew" in page_text:
        return [{"clue": "record quarter",
                 "quote": "Revenue grew +93% Y/Y",
                 "ring": "core", "segment": ""}]
    return []


class TestEvidenceStage:
    def test_cards_and_coverage_flow_through(self, tmp_path):
        import fitz

        doc = fitz.open()
        for i in range(3):
            page = doc.new_page()
            page.insert_text((72, 72), "Revenue grew +93% Y/Y" if i == 1
                             else f"filler {i}")
        doc.save(str(tmp_path / "doc.pdf"))
        doc.close()

        r = auto_pipeline(
            "DemoCo", SEGMENTS, TOTAL, YEARS,
            tags={"Core": "semiconductor", "AI": "regime_shift_tech"},
            digest_queue=str(tmp_path), digest_backend=_evidence_backend,
            workdir=str(tmp_path / "run"),
        )
        assert r.chainbook is not None
        assert len(r.chainbook.cards) == 1
        assert r.chainbook.cards[0].verified
        assert r.coverage == {"doc.pdf": "present"}
        assert r.gates_waiting == ()

    def test_missing_backend_raises_gate_question(self, tmp_path):
        r = auto_pipeline(
            "DemoCo", SEGMENTS, TOTAL, YEARS,
            tags={"Core": "semiconductor"},
            digest_queue=str(tmp_path), digest_backend=None,
            workdir=str(tmp_path / "run"),
        )
        assert r.gates_waiting == ("documents",)     # Gate H, not a crash
        assert r.chainbook is None

    def test_resume_semantics_via_state_file(self, tmp_path):
        workdir = tmp_path / "run"
        auto_pipeline("DemoCo", SEGMENTS, TOTAL, YEARS,
                      tags={"Core": "semiconductor"},
                      digest_queue=str(tmp_path), digest_backend=None,
                      workdir=str(workdir))
        book = GateBook.load(workdir)
        book.answer("documents",
                    "I don't know either — search and judge yourself")
        assert book.answered_answer("documents") is not None
        assert [g.authority for g in book.gates
                if g.gate == "documents"] == ["user-delegated"]
