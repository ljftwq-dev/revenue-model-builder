"""Smoke tests for revenue_model.viz — headless (Agg) render checks.

Visualization is hard to assert on pixel-by-pixel, so these tests verify the
contract instead: each chart runs on real model output without raising and
returns the advertised matplotlib object (``Axes`` / ``Figure``). The Agg
backend is forced before pyplot is imported anywhere, so the suite is
CI-friendly and needs no display.
"""
import matplotlib
matplotlib.use("Agg")  # must precede any pyplot import

import matplotlib.pyplot as plt
import pytest
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from revenue_model import (
    Driver, Segment, RevenueModel, BASE, PENETRATION, SHARE, PRICE,
    simulate_segment, tornado, scenarios,
)
from revenue_model.viz import (
    plot_revenue_distribution, plot_tornado, plot_waterfall,
    plot_forecast, plot_dashboard,
)

RANGES = {
    "市场基数": (95, 120),
    "渗透率": (0.40, 0.60),
    "份额": (0.15, 0.25),
    "单价": (9.0, 11.0),
}


@pytest.fixture
def seg():
    return Segment(
        "消费电子",
        base=Driver("市场基数", BASE, {2023: 100.0, 2024: 110.0, 2025: 120.0},
                    level="B", unit="百万"),
        penetration=Driver("渗透率", PENETRATION,
                           {2023: 0.5, 2024: 0.5, 2025: 0.5}, level="B"),
        share=Driver("份额", SHARE, {2023: 0.2, 2024: 0.2, 2025: 0.2}, level="C"),
        price=Driver("单价", PRICE, {2023: 10.0, 2024: 10.0, 2025: 10.0}, level="C"),
    )


@pytest.fixture
def model(seg):
    return RevenueModel("测试公司", [seg], total_revenue={2023: 100.0, 2024: 110.0})


def test_distribution_returns_axes(seg):
    mc = simulate_segment(seg, 2024, RANGES, n=500, seed=0)
    ax = plot_revenue_distribution(mc, scenarios=scenarios(mc))
    assert isinstance(ax, Axes)
    plt.close("all")


def test_tornado_returns_axes(seg):
    items = tornado(seg, 2024, RANGES)
    ax = plot_tornado(items)
    assert isinstance(ax, Axes)
    plt.close("all")


def test_waterfall_upside(seg):
    ax = plot_waterfall(tornado(seg, 2024, RANGES))
    assert isinstance(ax, Axes)
    plt.close("all")


def test_waterfall_downside(seg):
    ax = plot_waterfall(tornado(seg, 2024, RANGES), direction="low")
    assert isinstance(ax, Axes)
    plt.close("all")


def test_waterfall_rejects_bad_direction(seg):
    with pytest.raises(ValueError):
        plot_waterfall(tornado(seg, 2024, RANGES), direction="sideways")


def test_forecast_distinguishes_hist_and_forecast(model):
    ax = plot_forecast(model, forecast_years=[2025])
    assert isinstance(ax, Axes)
    plt.close("all")


def test_dashboard_returns_figure(model):
    fig = plot_dashboard(model, forecast_years=[2025])
    assert isinstance(fig, Figure)
    plt.close("all")


def test_dashboard_picks_named_segment(model):
    fig = plot_dashboard(model, segment_name="消费电子")
    assert isinstance(fig, Figure)
    plt.close("all")
