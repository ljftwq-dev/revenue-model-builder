"""C1 regression: validate() must not false-positive on reported-anchor models.

Reported figures are whole-millions, so Σ reported segments vs reported total
differs by ±1-2 from rounding. The back-solve (Principle 1) and structure-wrong
warnings must NOT fire for that — only for genuine driver-layer back-solving.
"""
import pytest

from revenue_model.driver import Driver, BASE, PENETRATION, SHARE, PRICE
from revenue_model.segment import Segment
from revenue_model.model import RevenueModel


def _reported_seg(name, reported):
    """A segment whose revenue comes entirely from reported_revenue."""
    return Segment(
        name=name,
        base=Driver(f"{name} base", BASE, {}),
        penetration=Driver(f"{name} pen", PENETRATION, {}),
        share=Driver(f"{name} share", SHARE, {}),
        price=Driver(f"{name} price", PRICE, {}),
        reported_revenue=reported,
    )


def test_reported_anchor_positive_rounding_no_false_positive():
    """Σ reported = total - 1 (rounding) must NOT trigger back-solve warning."""
    model = RevenueModel(
        company="Co",
        segments=[_reported_seg("A", {2025: 100.0}), _reported_seg("B", {2025: 50.0})],
        total_revenue={2025: 151.0},  # Σ=150, resid=+1
    )
    r = model.validate(2025)
    assert r.residual == 1.0
    assert not any("back-solved" in w for w in r.warnings), r.warnings


def test_reported_anchor_negative_rounding_no_false_positive():
    """Σ reported = total + 1 (rounding) must NOT trigger structure-wrong."""
    model = RevenueModel(
        company="Co",
        segments=[_reported_seg("A", {2025: 100.0}), _reported_seg("B", {2025: 51.0})],
        total_revenue={2025: 150.0},  # Σ=151, resid=-1
    )
    r = model.validate(2025)
    assert r.residual == -1.0
    assert not any("structure" in w.lower() for w in r.warnings), r.warnings


def test_driver_backsolve_still_warns():
    """A driver-product model with near-zero residual MUST still warn (Principle 1
    intact). Reported-anchor tolerance must not weaken back-solve detection."""
    seg = Segment(
        name="A",
        base=Driver("b", BASE, {2025: 10.0}),
        penetration=Driver("p", PENETRATION, {2025: 0.5}),
        share=Driver("s", SHARE, {2025: 0.2}),
        price=Driver("pr", PRICE, {2025: 100.0}),  # revenue = 100
    )
    model = RevenueModel(company="Co", segments=[seg], total_revenue={2025: 100.5})
    r = model.validate(2025)
    assert any("back-solved" in w for w in r.warnings), r.warnings


def test_reported_anchor_large_residual_still_warns():
    """Reported anchors but a BIG residual (missing segment) MUST still warn."""
    model = RevenueModel(
        company="Co",
        segments=[_reported_seg("A", {2025: 50.0})],  # only 50 of 150
        total_revenue={2025: 150.0},  # resid=100, ratio 67%
    )
    r = model.validate(2025)
    assert any("too high" in w or "dominates" in w for w in r.warnings), r.warnings
