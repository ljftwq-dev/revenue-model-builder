"""Tests for revenue_model.industry — profiles, resolution, forecast, checks."""

import math

import pytest

from revenue_model import (
    Driver, Segment, RevenueModel,
    BASE, PENETRATION, SHARE, PRICE,
    resolve_industry, list_profiles, forecast_segment,
    check_segment, benchmark_warnings, profile_warnings, segment_warnings,
    INDUSTRY_PROFILES,
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _seg(industry="", base=None, pen=None, share=None, price=None, name="t"):
    return Segment(
        name=name,
        base=base or Driver("base", BASE, {2022: 100.0, 2023: 110.0, 2024: 120.0},
                            level="B", unit="M units"),
        penetration=pen or Driver("pen", PENETRATION, {2022: 0.10, 2023: 0.13, 2024: 0.16},
                                  level="C", unit="fraction"),
        share=share or Driver("share", SHARE, {2022: 0.20, 2023: 0.20, 2024: 0.20},
                              level="C", unit="fraction"),
        price=price or Driver("price", PRICE, {2022: 100.0, 2023: 100.0, 2024: 100.0},
                              level="C", unit="yuan"),
        industry=industry,
    )


YEARS = [2025, 2026]


# ---------------------------------------------------------------------------
# registry & resolution
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_ten_profiles_complete(self):
        assert len(INDUSTRY_PROFILES) == 10
        for p in INDUSTRY_PROFILES.values():
            assert p.fit in ("strong", "adapt", "weak")
            assert set(p.defaults) == {BASE, PENETRATION, SHARE, PRICE}
            for c in p.checks:
                assert c, f"check name empty in {p.key}"

    def test_list_profiles(self):
        rows = list_profiles()
        assert len(rows) == 10
        assert any(r[0] == "regime_shift_tech" and r[1] == "weak" for r in rows)

    def test_mechanism_keys_resolve(self):
        for key in INDUSTRY_PROFILES:
            assert resolve_industry(key).key == key

    @pytest.mark.parametrize("alias,expected", [
        ("40", "semiconductor"),
        ("information technology", "semiconductor"),
        ("Information Technology ", "semiconductor"),   # case/space tolerant
        ("45", "financial_interest"),
        ("financials", "financial_interest"),
        ("银行", "financial_interest"),
        ("10", "commodity_cyclical"),
        ("能源", "commodity_cyclical"),
        ("软件", "saas_subscription"),
        ("ai", "regime_shift_tech"),
        ("人工智能", "regime_shift_tech"),
        ("消费电子", "consumer_electronics"),
    ])
    def test_aliases(self, alias, expected):
        assert resolve_industry(alias).key == expected

    def test_unknown_raises_with_catalog(self):
        with pytest.raises(KeyError, match="regime_shift_tech"):
            resolve_industry("health care")   # intentionally unmapped


# ---------------------------------------------------------------------------
# forecast_segment — per-industry default behavior
# ---------------------------------------------------------------------------

class TestForecastSegment:
    def test_requires_industry(self):
        with pytest.raises(ValueError, match="industry"):
            forecast_segment(_seg(), YEARS)

    def test_hand_coverage_wins_before_param_resolution(self):
        """Soft-default contract: a driver already extended to ALL target
        years is returned untouched — spec params are not even resolved.
        Regression for the Track-B API finding: a structural constant at 1.0
        on a logistic-default kind used to raise ValueError from the anchor
        check despite the hand extension (profile-validation.md section 4)."""
        held = Driver("pen", PENETRATION,
                      {2022: 1.0, 2023: 1.0, 2024: 1.0, 2025: 1.0, 2026: 1.0},
                      level="A", unit="fraction")
        seg = _seg(industry="saas_subscription", pen=held)   # logistic L=0.6
        out = forecast_segment(seg, YEARS)                   # must not raise
        assert out.penetration.values[2025] == 1.0
        assert out.penetration.values[2026] == 1.0
        assert out.penetration.level == "A"                  # hand grade kept

    def test_partial_coverage_still_extrapolates(self):
        partly = Driver("pen", PENETRATION,
                        {2022: 0.2, 2023: 0.25, 2024: 0.3, 2025: 0.3},
                        level="A", unit="fraction")
        out = forecast_segment(_seg(industry="saas_subscription", pen=partly),
                               YEARS)
        assert out.penetration.values[2025] == 0.3           # hand year kept
        assert 2026 in out.penetration.values               # 2026 filled by spec
        assert out.penetration.values[2026] != 1.0          # actually modeled

    def test_reads_segment_tag(self):
        out = forecast_segment(_seg(industry="consumer_electronics"), YEARS)
        assert out.industry == "consumer_electronics"

    def test_history_untouched_and_c_grade(self):
        out = forecast_segment(_seg(industry="retail_store"), YEARS)
        for d in out.drivers():
            assert 2024 in d.values and d.values[2024] == pytest.approx(
                {dd.kind: dd for dd in _seg().drivers()}[d.kind].values[2024])
            assert d.level == "C"                     # forecast years are C-grade
            assert "extrapolat" in d.source or d.source

    def test_consumer_electronics_asp_erodes(self):
        out = forecast_segment(_seg(industry="consumer_electronics"), YEARS)
        assert out.price.values[2025] == pytest.approx(95.0)      # 100 × 0.95
        assert out.price.values[2026] == pytest.approx(90.25)     # 100 × 0.95²

    def test_saas_penetration_logistic(self):
        out = forecast_segment(_seg(industry="saas_subscription"), YEARS)
        # logistic toward L=0.6 with t0=last(2024): 2025 must move up, stay < L
        assert out.penetration.values[2025] > 0.16
        assert out.penetration.values[2026] > out.penetration.values[2025]
        assert out.penetration.values[2026] < 0.6

    def test_saas_arpu_escalates(self):
        out = forecast_segment(_seg(industry="saas_subscription"), YEARS)
        assert out.price.values[2025] == pytest.approx(102.0)
        assert out.price.values[2026] == pytest.approx(104.04)

    def test_industrial_utilization_mean_reverts_to_80(self):
        hot = Driver("pen", PENETRATION,
                     {2022: 0.90, 2023: 0.92, 2024: 0.94}, unit="fraction")
        out = forecast_segment(_seg(industry="industrial_capacity", pen=hot), YEARS)
        v25 = out.penetration.values[2025]
        assert v25 == pytest.approx(0.94 + 0.4 * (0.8 - 0.94))
        assert v25 < 0.94 and v25 > 0.8                # pulled toward anchor

    def test_advertising_price_mean_reverts_to_3yr_mean(self):
        cyc = Driver("ecpm", PRICE, {2022: 30.0, 2023: 40.0, 2024: 50.0}, unit="yuan")
        out = forecast_segment(_seg(industry="advertising", price=cyc), YEARS)
        target = (30.0 + 40.0 + 50.0) / 3.0            # 40
        assert out.price.values[2025] == pytest.approx(50.0 + 0.3 * (target - 50.0))

    def test_financial_yield_pulls_to_4pct(self):
        y = Driver("yield", PRICE, {2022: 0.05, 2023: 0.05, 2024: 0.05}, unit="fraction")
        out = forecast_segment(_seg(industry="financial_interest", price=y), YEARS)
        assert out.price.values[2025] == pytest.approx(0.05 + 0.5 * (0.04 - 0.05))

    def test_hold_flat(self):
        out = forecast_segment(_seg(industry="telecom_subscriber"), YEARS)
        assert out.price.values[2025] == pytest.approx(100.0)
        assert out.price.values[2026] == pytest.approx(100.0)

    def test_telecom_base_net_growth(self):
        """v0.17: telecom base = water-in/water-out (gross 5%, churn 3.5%)."""
        out = forecast_segment(_seg(industry="telecom_subscriber"), YEARS)
        net = 1.0 + 0.05 - 0.035                    # 1.015
        assert out.base.values[2025] == pytest.approx(120.0 * net)
        assert out.base.values[2026] == pytest.approx(120.0 * net ** 2)

    def test_saas_base_net_growth(self):
        """v0.17: saas base = gross adds 30% - churn 12% (Direction B)."""
        out = forecast_segment(_seg(industry="saas_subscription"), YEARS)
        net = 1.0 + 0.30 - 0.12                    # 1.18
        assert out.base.values[2025] == pytest.approx(120.0 * net)

    def test_net_growth_rejects_extinguishing_base(self):
        with pytest.raises(ValueError, match="net growth"):
            Driver("subs", BASE, {2024: 100.0}).extrapolate_net_growth(
                [2025], gross_rate=0.05, churn=1.10)   # net = -0.05 <= 0

    def test_net_churn_positive_check_fires(self):
        """Base shrinking faster than ARPU grows -> the check says so."""
        shrinking = Driver("subs", BASE,
                           {2022: 100.0, 2023: 95.0, 2024: 89.0}, unit="M")
        escalator = Driver("arpu", PRICE,
                           {2022: 100.0, 2023: 101.5, 2024: 103.0}, unit="$")
        seg = _seg(industry="saas_subscription",
                   base=shrinking, price=escalator)
        msgs = check_segment(seg)
        assert any("net churn" in m and "escalator" in m for m in msgs)

    def test_net_churn_positive_check_silent_when_growing(self):
        seg = _seg(industry="saas_subscription")    # base 100/110/120 grows
        assert not any("net churn" in m for m in check_segment(seg))

    def test_regime_shift_all_trend_baseline(self):
        out = forecast_segment(_seg(industry="regime_shift_tech"), YEARS)
        # naive linear baseline on base 100/110/120 → slope 10 → 130, 140
        assert out.base.values[2025] == pytest.approx(130.0, abs=1e-6)
        assert out.base.values[2026] == pytest.approx(140.0, abs=1e-6)

    def test_override_by_hand_still_possible(self):
        """Soft-default rule: user extrapolations win over profile defaults."""
        seg = _seg(industry="consumer_electronics")
        manual = seg.price.extrapolate_erosion(YEARS, rate=0.10)
        seg2 = Segment(seg.name, seg.base, seg.penetration, seg.share, manual,
                       industry=seg.industry)
        out = forecast_segment(seg2, YEARS)
        assert out.price.values[2025] == pytest.approx(90.0)     # 10% erosion won


# ---------------------------------------------------------------------------
# warnings & checks
# ---------------------------------------------------------------------------

class TestWarningsChecks:
    def test_weak_fit_redirect(self):
        p = resolve_industry("regime_shift_tech")
        w = profile_warnings(p)
        assert any("structurally unreliable" in x for x in w)
        assert any("Monte Carlo" in x or "scenarios" in x for x in w)

    def test_strong_fit_no_weak_warning(self):
        w = profile_warnings(resolve_industry("consumer_electronics"))
        assert not any("unreliable" in x for x in w)

    def test_regime_check_unconditional(self):
        seg = _seg(industry="regime_shift_tech")
        assert any("$115B" in x or "simulate_segment" in x for x in check_segment(seg))

    def test_hypergrowth_base_fires(self):
        hot = Driver("base", BASE,
                     {2022: 1.0, 2023: 1.5, 2024: 2.5}, unit="M units")  # ~58%/yr
        seg = _seg(industry="semiconductor", base=hot)
        assert any("regime" in x.lower() for x in check_segment(seg))

    def test_hypergrowth_base_silent_when_calm(self):
        calm = Driver("base", BASE, {2022: 98.0, 2023: 100.0, 2024: 102.0},
                      unit="M units")
        assert check_segment(_seg(industry="semiconductor", base=calm)) == []

    def test_utilization_cap_fires(self):
        hot = Driver("pen", PENETRATION,
                     {2022: 0.85, 2023: 0.93, 2024: 0.97}, unit="fraction")
        seg = _seg(industry="industrial_capacity", pen=hot)
        assert any("binding constraint" in x for x in check_segment(seg))

    def test_cycle_top_fires(self):
        cyc = Driver("price", PRICE,
                     {2020: 10.0, 2021: 11.0, 2022: 12.0, 2023: 13.0, 2024: 25.0},
                     unit="yuan")
        seg = _seg(industry="commodity_cyclical", price=cyc)
        assert any("cycle top" in x.lower() for x in check_segment(seg))

    def test_asp_rising_fires_on_pricing_power(self):
        up = Driver("asp", PRICE, {2022: 100.0, 2023: 105.0, 2024: 112.0},
                    unit="yuan")                                   # ~6%/yr
        seg = _seg(industry="consumer_electronics", price=up)
        assert any("erosion" in x.lower() for x in check_segment(seg))

    def test_segment_warnings_combines(self):
        seg = _seg(industry="financial_interest")
        w = segment_warnings(seg)
        assert any("weak fit" in x or "unreliable" in x for x in w)

    def test_untagged_segment_no_warnings(self):
        assert segment_warnings(_seg()) == []


# ---------------------------------------------------------------------------
# benchmarks — sourced industry bands (v0.18)
# ---------------------------------------------------------------------------

class TestBenchmarks:
    def test_nine_profiles_anchored_regime_shift_empty(self):
        for key, p in INDUSTRY_PROFILES.items():
            if key == "regime_shift_tech":
                assert p.benchmarks == ()   # no benchmark by design
            else:
                assert len(p.benchmarks) >= 2, f"{key} missing benchmarks"

    def test_band_ordering_and_complete_citation(self):
        for p in INDUSTRY_PROFILES.values():
            for b in p.benchmarks:
                assert b.p25 <= b.p50 <= b.p75, (p.key, b.metric)
                assert b.unit == "fraction"
                assert b.source and "Damodaran" in b.source
                assert b.vintage == "2026-01"
                assert b.grade == "B"
                assert "cluster:" in b.note

    def test_growth_metrics_present(self):
        for key, p in INDUSTRY_PROFILES.items():
            if key == "regime_shift_tech":
                continue
            metrics = {b.metric for b in p.benchmarks}
            assert "revenue_cagr_5y" in metrics, key
            assert "revenue_exp_growth_2y" in metrics, key

    def test_cross_profile_ordering_sanity(self):
        def p50(key, metric):
            return next(b.p50 for b in INDUSTRY_PROFILES[key].benchmarks
                        if b.metric == metric)
        # SaaS historical growth far above retail — the bands must preserve
        # this well-known ordering, else the citations are suspect
        assert p50("saas_subscription", "revenue_cagr_5y") > \
               p50("retail_store", "revenue_cagr_5y")
        assert p50("semiconductor", "revenue_cagr_5y") > \
               p50("consumer_electronics", "revenue_cagr_5y")

    def test_benchmark_importable_from_package(self):
        from revenue_model import Benchmark
        b = Benchmark("x", 0.1, 0.2, 0.3)
        assert (b.p25, b.p50, b.p75) == (0.1, 0.2, 0.3)


# ---------------------------------------------------------------------------
# benchmark warnings — citation-based band checks (v0.18 step 3)
# ---------------------------------------------------------------------------

class TestBenchmarkWarnings:
    def _saas(self, base, pen):
        return Segment(
            name="s", industry="saas_subscription",
            base=Driver("b", BASE, base, level="B", unit="M users"),
            penetration=Driver("p", PENETRATION, pen, level="C", unit="frac"),
            share=Driver("sh", SHARE, {y: 1.0 for y in base}, level="C"),
            price=Driver("pr", PRICE, {y: 1.0 for y in base}, level="C"),
        )

    def test_above_band_cites_cluster_and_grade(self):
        # product CAGR ~38.6%/yr vs SaaS band 16.4-27.6%
        seg = self._saas({2022: 100.0, 2023: 110.0, 2024: 120.0},
                         {2022: 0.10, 2023: 0.13, 2024: 0.16})
        out = benchmark_warnings(seg)
        assert len(out) == 1
        assert "ABOVE the industry band" in out[0]
        assert "cluster: Software" in out[0]
        assert "grade B" in out[0]

    def test_inside_band_silent(self):
        # product CAGR ~20%/yr — inside the SaaS band
        seg = self._saas({2022: 100.0, 2023: 110.0, 2024: 120.0},
                         {2022: 0.10, 2023: 0.11, 2024: 0.12})
        assert benchmark_warnings(seg) == []

    def test_below_band_flags(self):
        # flat revenue (0%/yr) vs retail band floor 2.3%
        seg = Segment(
            name="r", industry="retail_store",
            base=Driver("b", BASE, {2022: 100.0, 2023: 100.0, 2024: 100.0}),
            penetration=Driver("p", PENETRATION,
                               {2022: 0.10, 2023: 0.10, 2024: 0.10}),
            share=Driver("sh", SHARE, {2022: 0.2, 2023: 0.2, 2024: 0.2}),
            price=Driver("pr", PRICE, {2022: 1.0, 2023: 1.0, 2024: 1.0}),
        )
        out = benchmark_warnings(seg)
        assert len(out) == 1
        assert "BELOW the industry band" in out[0]

    def test_no_benchmark_profile_returns_empty(self):
        assert benchmark_warnings(_seg(industry="regime_shift_tech")) == []

    def test_forecast_window_compared_when_boundary_given(self):
        # history in-band (~20%), forecast years 2025-26 at ~40%/yr
        seg = self._saas(
            {2022: 100.0, 2023: 110.0, 2024: 120.0, 2025: 168.0, 2026: 235.0},
            {2022: 0.10, 2023: 0.11, 2024: 0.12, 2025: 0.12, 2026: 0.12})
        # without boundary: all years = history, one ABOVE line from history
        out_no_boundary = benchmark_warnings(seg)
        assert len(out_no_boundary) == 1
        assert "last-3y" in out_no_boundary[0]
        # with boundary: history clean, forecast window ABOVE the exp band
        out = benchmark_warnings(seg, history_end=2024)
        assert len(out) == 1
        assert "forecast-window" in out[0]
        assert "ABOVE" in out[0]

    def test_segment_warnings_includes_benchmark_layer(self):
        seg = self._saas({2022: 100.0, 2023: 110.0, 2024: 120.0},
                         {2022: 0.10, 2023: 0.13, 2024: 0.16})
        allw = segment_warnings(seg)
        assert any("industry band" in w for w in allw)


# ---------------------------------------------------------------------------
# integration — profiles coexist with the existing engine
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_segment_without_industry_backward_compatible(self):
        model = RevenueModel("DemoCo", [_seg()], total_revenue={2024: 10.0})
        results = model.validate_all()
        assert results

    def test_forecasted_segment_feeds_model(self):
        seg = forecast_segment(_seg(industry="saas_subscription"),
                               [2025, 2026, 2027])
        rev25 = seg.revenue(2025)
        assert rev25 > 0
        assert all(math.isfinite(seg.revenue(y)) for y in (2025, 2026, 2027))

    def test_reported_anchor_still_wins(self):
        seg = _seg(industry="retail_store")
        seg.reported_revenue[2025] = 123.0
        out = forecast_segment(seg, YEARS)
        assert out.revenue(2025) == 123.0
        assert out.revenue_source(2025) == "reported"
        assert out.revenue_source(2026) == "drivers"
