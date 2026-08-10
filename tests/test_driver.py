"""Tests for Driver extrapolation (A2: Principle 3 encoded as API)."""

import math

from revenue_model.driver import Driver, PENETRATION, SHARE, PRICE, LEVEL_C


def test_extrapolate_incremental_absolute():
    d = Driver("pen", PENETRATION, {2024: 0.10}, level="B", unit="fraction")
    ext = d.extrapolate_incremental([2025, 2026, 2027], 0.03)
    assert ext.values[2024] == 0.10           # history preserved
    assert ext.values[2025] == 0.13
    assert ext.values[2026] == 0.16
    assert ext.values[2027] == 0.19
    assert ext.level == LEVEL_C                # downgraded to C
    assert "incremental" in ext.source


def test_extrapolate_incremental_clamps_bounded():
    d = Driver("share", SHARE, {2024: 0.90}, level="C")
    ext = d.extrapolate_incremental([2025, 2026, 2027], 0.10)
    assert ext.values[2025] == 1.0             # clamped at 1.0
    assert ext.values[2026] == 1.0
    assert ext.values[2027] == 1.0
    assert "clamped" in ext.source


def test_extrapolate_incremental_unbounded_not_clamped():
    d = Driver("price", PRICE, {2024: 600.0})
    ext = d.extrapolate_incremental([2025, 2026], 50.0)
    assert ext.values[2025] == 650.0
    assert ext.values[2026] == 700.0
    assert "clamped" not in ext.source


def test_extrapolate_logistic_midpoint():
    d = Driver("pen", PENETRATION, {2020: 0.05})
    ext = d.extrapolate_logistic([2026], L=0.30, k=0.5, t0=2026)
    assert math.isclose(ext.values[2026], 0.15, rel_tol=1e-9)   # L/2 at t0
    assert ext.level == LEVEL_C
    assert "logistic" in ext.source


def test_fit_trend_linear():
    d = Driver("price", PRICE, {2022: 600.0, 2023: 620.0, 2024: 640.0})
    fit = d.fit_trend([2022, 2023, 2024])
    assert fit.slope == 20.0
    ext = fit.extrapolate([2025, 2026])
    assert ext.values[2025] == 660.0
    assert ext.values[2026] == 680.0
    assert ext.level == LEVEL_C
    assert "trend" in ext.source


def test_fit_trend_needs_two_years():
    d = Driver("price", PRICE, {2024: 100.0})
    raised = False
    try:
        d.fit_trend([2024])
    except ValueError:
        raised = True
    assert raised


def test_extrapolation_does_not_mutate_original():
    d = Driver("pen", PENETRATION, {2024: 0.10}, level="B")
    ext = d.extrapolate_incremental([2025], 0.03)
    assert d.values == {2024: 0.10}            # original values untouched
    assert d.level == "B"                       # original level untouched
    assert ext is not d                         # new object returned


# ---- i18n (kind_label bilingual) -------------------------------------------
def test_kind_label_default_zh():
    from revenue_model.driver import BASE
    assert Driver("x", BASE, {2024: 1.0}).kind_label() == "市场基数"
    assert Driver("x", PENETRATION, {2024: 0.1}).kind_label() == "渗透率"
    assert Driver("x", SHARE, {2024: 0.1}).kind_label() == "市占率"
    assert Driver("x", PRICE, {2024: 1.0}).kind_label() == "单价"


def test_kind_label_en():
    from revenue_model.driver import BASE
    assert Driver("x", BASE, {2024: 1.0}).kind_label("en") == "Market Base"
    assert Driver("x", PENETRATION, {2024: 0.1}).kind_label("en") == "Penetration"
    assert Driver("x", SHARE, {2024: 0.1}).kind_label("en") == "Share"
    assert Driver("x", PRICE, {2024: 1.0}).kind_label("en") == "Unit Price"


def test_kind_label_unknown_lang_falls_back_to_zh():
    from revenue_model.driver import BASE
    # graceful fallback: an unknown lang code returns the Chinese label
    assert Driver("x", BASE, {2024: 1.0}).kind_label("fr") == "市场基数"
