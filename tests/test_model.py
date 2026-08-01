"""Core logic tests."""

import pytest

from revenue_model.driver import Driver, BASE, PENETRATION, SHARE, PRICE
from revenue_model.segment import Segment, implied_driver
from revenue_model.model import RevenueModel
from revenue_model.demo import build_novatech


def _seg(base, pen, share, price, year=2020):
    return Segment(
        name="t",
        base=Driver("b", BASE, {year: base}),
        penetration=Driver("p", PENETRATION, {year: pen}),
        share=Driver("s", SHARE, {year: share}),
        price=Driver("$", PRICE, {year: price}),
    )


def test_revenue_formula():
    seg = _seg(10.0, 0.5, 0.2, 100)
    assert seg.revenue(2020) == pytest.approx(100.0)


def test_zero_penetration_zero_revenue():
    seg = _seg(10.0, 0.0, 0.5, 100)
    assert seg.revenue(2020) == 0.0


def test_segment_rejects_duplicate_driver_kind():
    with pytest.raises(ValueError):
        Segment(
            name="bad",
            base=Driver("b", BASE, {2020: 1}),
            penetration=Driver("p", BASE, {2020: 1}),
            share=Driver("s", SHARE, {2020: 1}),
            price=Driver("$", PRICE, {2020: 1}),
        )


def test_driver_missing_year_raises():
    seg = _seg(10.0, 0.5, 0.2, 100, year=2020)
    with pytest.raises(KeyError):
        seg.revenue(2021)


def test_residual_definition():
    model = build_novatech()
    for year in model.years():
        expected = model.total_revenue[year] - model.segment_sum(year)
        assert abs(model.residual(year) - expected) < 1e-9


def test_alignment_identity():
    model = build_novatech()
    for year in model.years():
        s = model.segment_sum(year)
        resid = model.residual(year)
        total = model.total_revenue[year]
        assert abs((s + resid) - total) < 1e-9


def test_demo_residual_nonnegative():
    model = build_novatech()
    for r in model.validate_all():
        assert r.residual >= 0


def test_demo_residual_ratio_reasonable():
    model = build_novatech()
    for r in model.validate_all():
        assert 0.1 <= r.residual_ratio <= 0.5


def test_negative_residual_warns():
    seg = _seg(100.0, 1.0, 1.0, 1000)
    model = RevenueModel("x", [seg], {2020: 10.0})
    r = model.validate(2020)
    assert r.residual < 0
    assert any("negative" in w for w in r.warnings)


def test_driver_kind_validation():
    with pytest.raises(ValueError):
        Driver("x", "bogus", {2020: 1})


def test_implied_driver_solves_price():
    seg = _seg(10.0, 0.5, 0.2, 100, year=2020)   # revenue = 100
    # target 200, solve PRICE -> 200 / (10*0.5*0.2) = 200
    assert implied_driver(seg, 2020, 200.0, PRICE) == pytest.approx(200.0)


def test_implied_driver_round_trip():
    seg = _seg(10.0, 0.5, 0.2, 100, year=2020)
    rev = seg.revenue(2020)  # 100
    # solving any driver kind and substituting back recovers the target revenue
    for kind in (BASE, PENETRATION, SHARE, PRICE):
        v = implied_driver(seg, 2020, rev, kind)
        factors = {d.kind: (v if d.kind == kind else d.get(2020)) for d in seg.drivers()}
        product = factors[BASE] * factors[PENETRATION] * factors[SHARE] * factors[PRICE]
        assert product == pytest.approx(rev)


def test_implied_driver_aligns_to_reported():
    # Analyst workflow: know base/pen/share, align price to reported revenue
    seg = _seg(24.0, 0.09, 0.14, 650, year=2024)   # revenue = 196.56
    reported = 196.56
    implied_price = implied_driver(seg, 2024, reported, PRICE)
    assert implied_price == pytest.approx(650.0, rel=1e-3)


def test_validate_near_zero_warns_backsolve():
    seg = _seg(10.0, 1.0, 1.0, 10.0)                 # revenue = 100
    model = RevenueModel("x", [seg], {2020: 100.5})  # residual 0.5% (<1%)
    r = model.validate(2020)
    assert any("near zero" in w for w in r.warnings)


def test_validate_small_residual_caliber_note():
    seg = _seg(10.0, 1.0, 1.0, 10.0)                 # revenue = 100
    model = RevenueModel("x", [seg], {2020: 103.0})  # residual 2.9% (1-5%)
    r = model.validate(2020)
    assert any("small" in w and "cover most revenue" in w for w in r.warnings)
    assert not any("near zero" in w for w in r.warnings)


def test_validate_no_small_warning_above_threshold():
    seg = _seg(10.0, 1.0, 1.0, 10.0)                 # revenue = 100
    model = RevenueModel("x", [seg], {2020: 120.0})  # residual 16.7% (>5%)
    r = model.validate(2020)
    assert not any("near zero" in w for w in r.warnings)
    assert not any("small" in w and "cover most revenue" in w for w in r.warnings)
