"""Profile-implied revenue-layer methods (Track A-2, pre-registered).

Three methods derived from v0.16 driver defaults, translated to the
revenue-series level (spec §2 Track A-2; they graduate into
``revenue_model/backtest/`` only if they win on validation):

- DampedTrend        <- industrial_capacity / mean_revert intuition:
                       absolute trend with geometrically decaying contribution
- DeceleratingCAGR   <- saas_subscription / logistic intuition:
                       fitted growth compounds with a decaying exponent
- GrowthRevert       <- commodity_cyclical / mean_revert intuition:
                       recent growth pulled toward the series' own long-run
                       growth (extrapolate_mean_reversion at the growth level)

All pure stdlib, following the backtest ForecastMethod protocol.
"""
import math
from typing import List, Sequence

from revenue_model.backtest.methods import ForecastMethod, _ols

PHI_TREND = 0.85     # per-year trend damping
PHI_GROWTH = 0.80    # per-year growth-exponent damping
KAPPA = 0.50         # pull of recent growth toward long-run growth
RECENT_WINDOW = 3    # years defining "recent" growth


class DampedTrend(ForecastMethod):
    """ŷ_{T+h} = y_T + slope · (φ + φ² + … + φ^h)  — OLS slope, contributions
    damped by φ per year. Between LinearTrend (φ=1) and Naive (φ=0)."""

    name = "Damped"

    def fit_predict(self, years, values, horizon):
        slope, intercept = _ols(list(years), list(values))
        level = values[-1]
        out, cum = [], 0.0
        for h in range(1, horizon + 1):
            cum += PHI_TREND ** h
            out.append(level + slope * cum)
        return out


class DeceleratingCAGR(ForecastMethod):
    """ŷ_{T+h} = y_T · (1+g)^{φ^h cumulative-decayed} — fitted CAGR g applied
    with a decaying exponent: young growth matures as the base grows (the
    logistic/S-curve intuition, linearized)."""

    name = "DecelCAGR"

    def fit_predict(self, years, values, horizon):
        if any(v <= 0 for v in values):
            raise ValueError("DeceleratingCAGR needs all values > 0")
        logs = [math.log(v) for v in values]
        slope, _ = _ols(list(years), logs)
        g = math.exp(slope) - 1.0
        level = values[-1]
        out, exponent = [], 0.0
        for h in range(1, horizon + 1):
            exponent += PHI_GROWTH ** h
            out.append(level * (1.0 + g) ** exponent)
        return out


class GrowthRevert(ForecastMethod):
    """g_forecast = g_recent + κ · (g_long − g_recent);  ŷ = y_T · (1+g_forecast)
    for h=1, then growth eases toward g_long (mean_reversion at the
    growth-rate level — the commodity/cyclical profile's honest translation)."""

    name = "GrowthRevert"

    def fit_predict(self, years, values, horizon):
        if any(v <= 0 for v in values):
            raise ValueError("GrowthRevert needs all values > 0")

        def cagr(sub_y, sub_v):
            logs = [math.log(v) for v in sub_v]
            slope, _ = _ols(list(sub_y), logs)
            return math.exp(slope) - 1.0

        g_long = cagr(years, values)
        if len(values) > RECENT_WINDOW:
            g_recent = cagr(list(years)[-RECENT_WINDOW:],
                            list(values)[-RECENT_WINDOW:])
        else:
            g_recent = g_long
        level = values[-1]
        g_fc = g_recent + KAPPA * (g_long - g_recent)
        out, val = [], level
        for h in range(1, horizon + 1):
            if h == 1:
                g_h = g_fc
            else:   # after year 1, the gap keeps closing toward g_long
                frac = KAPPA ** (h - 1)
                g_h = g_fc * frac + g_long * (1 - frac)
            val *= (1.0 + g_h)
            out.append(val)
        return out


def profile_method_set():
    """The three profile-implied methods (pure stdlib)."""
    return [DampedTrend(), DeceleratingCAGR(), GrowthRevert()]
