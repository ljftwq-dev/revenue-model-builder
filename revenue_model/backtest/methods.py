"""Forecasting-method adapters for the rolling backtest.

Every method follows one minimal protocol::

    name: str
    fit_predict(years, values, horizon) -> list[float]   # len == horizon

``years`` / ``values`` are ascending historical actuals; the method fits on all
of them and returns point forecasts for the next ``horizon`` years.

Dependency tiers (mirrors the viz/app philosophy — keep heavy imports out of
the import path):
    * Naive / LinearTrend / LogLinearCAGR — pure stdlib, always available.
    * HoltLinear / ARIMA — lazy-import statsmodels inside ``fit_predict``; a
      missing dep raises a clear ``pip install -e ".[backtest]"`` hint.

Design note — "our method" on the revenue-total level:
    Driver-extrapolation (Principle 3: incremental / OLS-trend on each driver)
    is the project's contribution. But on an *aggregate revenue total* with no
    driver decomposition, trend extrapolation of the total is just a linear
    fit — so ``LinearTrend`` is the faithful representative of the project's
    approach here. The driver decomposition's edge appears at the *segment*
    level (see the Luxun hold-out experiment), not on a single total. Stating
    this plainly is more honest than inventing a "driver-total" method that is
    linear under the hood.
"""

import math
from typing import List, Sequence


class ForecastMethod:
    """Base class. Subclasses set ``name`` and implement ``fit_predict``."""

    name: str = "base"

    def fit_predict(self, years: Sequence[int], values: Sequence[float],
                    horizon: int) -> List[float]:
        raise NotImplementedError

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name!r}>"


def _ols(xs: Sequence[float], ys: Sequence[float]):
    """Ordinary-least-squares slope/intercept (pure stdlib). Needs >= 2 points."""
    n = len(xs)
    if n < 2:
        raise ValueError(f"_ols needs >=2 points, got {n}")
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        raise ValueError("_ols: all x identical")
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    return slope, my - slope * mx


class Naive(ForecastMethod):
    """Random walk: next year equals the last observed value.

    The forecasting benchmark to beat — surprisingly hard to beat in 1-step-ahead
    revenue prediction. Any method that cannot beat Naive on average adds
    complexity for no gain.
    """

    name = "Naive"

    def fit_predict(self, years, values, horizon):
        last = values[-1]
        return [last] * horizon


class LinearTrend(ForecastMethod):
    """OLS linear trend on (year, value), extrapolated.

    The aggregate-total stand-in for the project's driver-trend extrapolation.
    """

    name = "Linear"

    def fit_predict(self, years, values, horizon):
        slope, intercept = _ols(list(years), list(values))
        last_year = years[-1]
        return [intercept + slope * (last_year + h + 1) for h in range(horizon)]


class LogLinearCAGR(ForecastMethod):
    """Compound Annual Growth Rate: OLS on (year, log value), exp-extrapolated.

    Models constant-* growth (geometric), vs LinearTrend's constant-absolute
    growth. Needs all values > 0. Often a better fit for high-growth names
    whose revenue compounds rather than adds.
    """

    name = "CAGR"

    def fit_predict(self, years, values, horizon):
        if any(v <= 0 for v in values):
            raise ValueError("LogLinearCAGR needs all values > 0")
        logs = [math.log(v) for v in values]
        slope, intercept = _ols(list(years), logs)
        last_year = years[-1]
        return [math.exp(intercept + slope * (last_year + h + 1))
                for h in range(horizon)]


class HoltLinear(ForecastMethod):
    """Holt's linear exponential smoothing (level + trend).

    Lazy-imports statsmodels. Adapts the trend smoothly — between Naive (no
    trend) and LinearTrend (rigid trend). ``damped`` applies the damped-trend
    variant, which is more conservative on long horizons.
    """

    name = "Holt"

    def __init__(self, damped: bool = True):
        self.damped = damped

    def fit_predict(self, years, values, horizon):
        try:
            from statsmodels.tsa.holtwinters import ExponentialSmoothing
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "HoltLinear requires statsmodels. "
                'Install it with:  pip install -e ".[backtest]"'
            ) from exc
        if len(values) < 3:
            # too short for a stable trend estimate; fall back to Naive
            return [values[-1]] * horizon
        fit = ExponentialSmoothing(
            list(values), trend="add", damped_trend=self.damped,
            initialization_method="estimated").fit(optimized=True)
        return list(fit.forecast(horizon))


class ARIMA(ForecastMethod):
    """ARIMA forecaster via statsmodels.

    Uses a simple, robust (1, 1, 1) order by default (one autoregressive lag,
    one difference for stationarity, one moving-average lag) — deliberately
    *not* auto-ARIMA, to keep the backtest deterministic and dependency-light.
    Override via ``order``.
    """

    name = "ARIMA"

    def __init__(self, order=(1, 1, 1)):
        self.order = order

    def fit_predict(self, years, values, horizon):
        try:
            from statsmodels.tsa.arima.model import ARIMA as _ARIMA
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "ARIMA requires statsmodels. "
                'Install it with:  pip install -e ".[backtest]"'
            ) from exc
        if len(values) < 5:
            return [values[-1]] * horizon
        try:
            fit = _ARIMA(list(values), order=self.order).fit()
            return list(fit.forecast(horizon))
        except Exception:
            # ARIMA can fail to converge on short/noisy series — degrade
            # gracefully rather than abort the whole backtest.
            return [values[-1]] * horizon


class DampedTrend(ForecastMethod):
    """Damped trend: OLS slope with geometrically decaying contribution.

    ``y[T+h] = y_T + slope * (phi + phi^2 + ... + phi^h)`` — between
    LinearTrend (phi=1) and Naive (phi=0). Graduated into the battery from
    the pre-registered profile validation (v0.16.1): best adapt-bucket
    method vs Naive on validation (-1.2pp, p_adj=0.020) and the best
    directional accuracy on test (74%); the revenue-layer translation of
    the industrial_capacity / mean-revert driver defaults.
    See docs/profile-validation.md."""

    name = "Damped"

    def __init__(self, phi: float = 0.85):
        self.phi = phi

    def fit_predict(self, years, values, horizon):
        slope, _intercept = _ols(list(years), list(values))
        level = values[-1]
        out, cum = [], 0.0
        for h in range(1, horizon + 1):
            cum += self.phi ** h
            out.append(level + slope * cum)
        return out


class DeceleratingCAGR(ForecastMethod):
    """Fitted CAGR applied with a decaying exponent: growth matures as the
    base grows (the logistic/S-curve intuition, linearized).

    ``y[T+h] = y_T * (1+g)^(phi + phi^2 + ... + phi^h)``. Graduated with
    the strongest result in the validation battery: beats Naive on its
    home saas_subscription profile with double significance (-5.7pp
    p_adj=0.0009 validation, -7.2pp p_adj=0.0164 test, rank-biserial
    r ~= -0.7). See docs/profile-validation.md."""

    name = "DecelCAGR"

    def __init__(self, phi: float = 0.80):
        self.phi = phi

    def fit_predict(self, years, values, horizon):
        if any(v <= 0 for v in values):
            raise ValueError("DeceleratingCAGR needs all values > 0")
        logs = [math.log(v) for v in values]
        slope, _intercept = _ols(list(years), logs)
        g = math.exp(slope) - 1.0
        level = values[-1]
        out, exponent = [], 0.0
        for h in range(1, horizon + 1):
            exponent += self.phi ** h
            out.append(level * (1.0 + g) ** exponent)
        return out


def default_methods() -> List[ForecastMethod]:
    """The standard method set used in cross-company comparisons.

    Naive (benchmark), LinearTrend (project's aggregate-trend stand-in),
    LogLinearCAGR (constant-growth), HoltLinear (adaptive trend), ARIMA
    (statistical), plus the two profile-implied shape methods graduated
    from the pre-registered validation (DampedTrend, DeceleratingCAGR —
    v0.17). Callers may pass a subset — e.g. drop the statsmodels-based
    ones for a zero-dependency run.
    """
    return [Naive(), LinearTrend(), LogLinearCAGR(), HoltLinear(), ARIMA(),
            DampedTrend(), DeceleratingCAGR()]
