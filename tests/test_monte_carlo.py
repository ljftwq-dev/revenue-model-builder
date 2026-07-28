"""Monte Carlo + sensitivity tests."""

import pytest

from revenue_model.driver import Driver, BASE, PENETRATION, SHARE, PRICE
from revenue_model.segment import Segment
from revenue_model.model import RevenueModel
from revenue_model.monte_carlo import (
    simulate_segment, simulate_model, tornado, scenarios,
)
from revenue_model.demo import build_novatech


def _seg(base, pen, share, price, year=2024, names=("b", "p", "s", "$")):
    return Segment(
        name="t",
        base=Driver(names[0], BASE, {year: base}),
        penetration=Driver(names[1], PENETRATION, {year: pen}),
        share=Driver(names[2], SHARE, {year: share}),
        price=Driver(names[3], PRICE, {year: price}),
    )


def test_mc_reproducible():
    seg = _seg(10.0, 0.5, 0.2, 100)
    r1 = simulate_segment(seg, 2024, {"b": (8, 12)}, n=5000, seed=42)
    r2 = simulate_segment(seg, 2024, {"b": (8, 12)}, n=5000, seed=42)
    assert r1.samples == r2.samples
    assert r1.mean == r2.mean


def test_mc_percentiles_monotonic():
    seg = _seg(10.0, 0.5, 0.2, 100)
    r = simulate_segment(seg, 2024, {"b": (5, 15), "p": (0.3, 0.7)}, n=8000, seed=1)
    p = r.percentiles
    assert p["p5"] <= p["p25"] <= r.median <= p["p75"] <= p["p95"]
    assert p["p5"] <= r.mean <= p["p95"]


def test_mc_no_range_is_deterministic():
    seg = _seg(10.0, 0.5, 0.2, 100)
    r = simulate_segment(seg, 2024, {}, n=1000, seed=0)
    assert r.stdev == 0.0
    assert r.mean == pytest.approx(seg.revenue(2024))
    assert r.median == pytest.approx(seg.revenue(2024))


def test_mc_uniform_mean_is_midpoint():
    # revenue = base * 0.5 * 0.2 * 100; base ~ Uniform(8,12) -> mean base 10
    seg = _seg(10.0, 0.5, 0.2, 100)
    r = simulate_segment(seg, 2024, {"b": (8, 12)}, n=40000, seed=7)
    assert r.mean == pytest.approx(100.0, abs=1.0)


def test_model_mc_matches_sum_of_segments():
    model = build_novatech()
    ranges = {
        "NovaTech 国内市占率": (0.10, 0.18),
        "NovaTech 海外市占率": (0.02, 0.06),
    }
    rm = simulate_model(model, 2024, ranges, n=20000, seed=3)
    s1 = simulate_segment(model.segments[0], 2024, ranges, n=20000, seed=3)
    s2 = simulate_segment(model.segments[1], 2024, ranges, n=20000, seed=3)
    assert rm.mean == pytest.approx(s1.mean + s2.mean, rel=0.05)


def test_tornado_base_matches_revenue():
    seg = _seg(10.0, 0.5, 0.2, 100)
    items = tornado(seg, 2024, {"b": (8, 12), "p": (0.4, 0.6)})
    for it in items:
        assert it.base_revenue == pytest.approx(seg.revenue(2024))


def test_tornado_sorted_descending():
    seg = _seg(10.0, 0.5, 0.2, 100)
    items = tornado(seg, 2024, {"b": (8, 12), "p": (0.4, 0.6),
                                "s": (0.18, 0.22), "$": (90, 110)})
    swings = [it.swing for it in items]
    assert swings == sorted(swings, reverse=True)


def test_tornado_distinct_swings():
    # A wider driver band must produce a larger swing — the whole point of a
    # tornado. (A uniform ±% would make all swings equal in a product model.)
    seg = _seg(10.0, 0.5, 0.2, 100)
    items = {it.driver: it for it in tornado(
        seg, 2024, {"b": (9.9, 10.1), "p": (0.3, 0.7)})}
    assert items["p"].swing > items["b"].swing


def test_tornado_penetration_capped_at_one():
    seg = _seg(10.0, 0.5, 0.2, 100)
    items = {it.driver: it for it in tornado(seg, 2024, {"p": (0.4, 1.5)})}
    pen = items["p"]
    # high clipped to 1.0 -> high_rev = 10 * 1.0 * 0.2 * 100 = 200
    assert pen.high_revenue == pytest.approx(200.0)


def test_tornado_skips_absent_drivers():
    seg = _seg(10.0, 0.5, 0.2, 100)
    items = tornado(seg, 2024, {"b": (8, 12)})
    assert [it.driver for it in items] == ["b"]


def test_tornado_deterministic():
    seg = _seg(10.0, 0.5, 0.2, 100)
    a = tornado(seg, 2024, {"b": (8, 12), "p": (0.4, 0.6)})
    b = tornado(seg, 2024, {"b": (8, 12), "p": (0.4, 0.6)})
    assert [(x.driver, x.swing) for x in a] == [(x.driver, x.swing) for x in b]


def test_mc_missing_year_raises():
    seg = _seg(10.0, 0.5, 0.2, 100, year=2024)
    with pytest.raises(KeyError):
        simulate_segment(seg, 2099, {"b": (8, 12)}, n=100)


def test_scenarios_ordered_bear_base_bull():
    seg = _seg(10.0, 0.5, 0.2, 100)
    mc = simulate_segment(seg, 2024, {"b": (5, 15), "p": (0.3, 0.7)}, n=8000, seed=1)
    rev = {s.name: s.revenue for s in scenarios(mc)}
    assert rev["Bear"] < rev["Base"] < rev["Bull"]


def test_scenarios_base_is_median():
    seg = _seg(10.0, 0.5, 0.2, 100)
    mc = simulate_segment(seg, 2024, {"b": (8, 12)}, n=5000, seed=2)
    base = next(s for s in scenarios(mc) if s.name == "Base")
    assert base.revenue == pytest.approx(mc.median)
    assert base.percentile == 0.50


def test_scenarios_custom_bands_widen():
    seg = _seg(10.0, 0.5, 0.2, 100)
    mc = simulate_segment(seg, 2024, {"b": (5, 15)}, n=8000, seed=3)
    wide = {s.name: s.revenue for s in scenarios(mc, bear_p=0.05, bull_p=0.95)}
    narrow = {s.name: s.revenue for s in scenarios(mc, bear_p=0.40, bull_p=0.60)}
    assert wide["Bear"] < narrow["Bear"]      # wider band => lower bear
    assert wide["Bull"] > narrow["Bull"]      # wider band => higher bull
