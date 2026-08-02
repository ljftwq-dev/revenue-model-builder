"""Forecast-accuracy metrics for backtesting point predictions.

Pure standard library — like the Monte Carlo engine, these metrics have no
third-party dependency, so they work anywhere (tests, notebooks, restricted
environments). The *implementations* are trivial; the value is in choosing the
right metric and reading it honestly.

Why sMAPE is the headline number, not MAPE:
    MAPE = |a - f| / |a| blows up when actual is small — the early years of a
    high-growth name (Luxun, BYD) sit at a few 亿 and would dominate the mean.
    sMAPE = |a - f| / ((|a| + |f|) / 2) is bounded in [0, 2], symmetric in
    over- vs under-prediction, and stable across orders of magnitude — the
    standard robust choice for revenue series. Read as a fraction (×100 for %).

MAE / RMSE stay in the series' units (million yuan): "how many 亿 off". They
are *scale-dependent* and not comparable across companies of different size;
sMAPE is. R² can go negative — a forecast worse than "predict the mean" earns
R² < 0, which is itself informative.
"""

import math
from typing import Sequence


def _paired(a: Sequence[float], b: Sequence[float]):
    a, b = list(a), list(b)
    if len(a) != len(b):
        raise ValueError(f"unequal lengths: {len(a)} vs {len(b)}")
    if not a:
        raise ValueError("empty sequences")
    return a, b


def mae(actual: Sequence[float], forecast: Sequence[float]) -> float:
    """Mean Absolute Error (million yuan). Scale-dependent."""
    a, f = _paired(actual, forecast)
    return sum(abs(x - y) for x, y in zip(a, f)) / len(a)


def rmse(actual: Sequence[float], forecast: Sequence[float]) -> float:
    """Root Mean Squared Error (million yuan). Penalises large misses more."""
    a, f = _paired(actual, forecast)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, f)) / len(a))


def mape(actual: Sequence[float], forecast: Sequence[float]) -> float:
    """Mean Absolute Percentage Error as a fraction (0.12 = 12%).

    Points whose actual is ~0 are skipped (would divide by zero). Returns
    ``inf`` if every actual is ~0 — i.e. MAPE is undefined for that series.
    Prefer :func:`smape` for series that approach zero.
    """
    a, f = _paired(actual, forecast)
    total, n = 0.0, 0
    for x, y in zip(a, f):
        if abs(x) < 1e-9:
            continue
        total += abs(x - y) / abs(x)
        n += 1
    return total / n if n else float("inf")


def smape(actual: Sequence[float], forecast: Sequence[float]) -> float:
    """Symmetric MAPE as a fraction, bounded in [0, 2].

    Robust to small actuals and symmetric in sign of error. The recommended
    headline accuracy metric for cross-company revenue backtests.
    """
    a, f = _paired(actual, forecast)
    total, n = 0.0, 0
    for x, y in zip(a, f):
        denom = (abs(x) + abs(y)) / 2.0
        if denom < 1e-9:
            continue
        total += abs(x - y) / denom
        n += 1
    return total / n if n else 0.0


def r_squared(actual: Sequence[float], forecast: Sequence[float]) -> float:
    """Coefficient of determination for forecasts.

    ``1 - SS_res / SS_tot`` where ``SS_tot`` uses the mean of *actual*. A
    perfect forecast scores 1; predicting the mean scores 0; a forecast worse
    than the mean goes negative. Returns 0.0 when actuals have no variance
    (nothing to explain).
    """
    a, f = _paired(actual, forecast)
    mean = sum(a) / len(a)
    ss_tot = sum((x - mean) ** 2 for x in a)
    if ss_tot < 1e-12:
        return 0.0
    ss_res = sum((x - y) ** 2 for x, y in zip(a, f))
    return 1.0 - ss_res / ss_tot


ALL_METRICS = {
    "MAE": mae,
    "RMSE": rmse,
    "MAPE": mape,
    "sMAPE": smape,
    "R2": r_squared,
}
