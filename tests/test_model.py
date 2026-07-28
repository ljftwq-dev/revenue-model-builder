"""Core logic tests."""

import pytest

from revenue_model.driver import Driver, BASE, PENETRATION, SHARE, PRICE
from revenue_model.segment import Segment
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
