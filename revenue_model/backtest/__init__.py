"""Backtesting toolkit for revenue-model-builder: out-of-sample evaluation.

Three importable layers, none of which pulls a third-party dependency at
import time:

    metrics  — forecast-accuracy metrics (pure stdlib)
    methods  — forecasting adapters (Naive / Linear / CAGR are stdlib;
               Holt / ARIMA lazy-import statsmodels on use)
    rolling  — expanding / fixed-window backtest engine (pure stdlib)

A fourth, :mod:`revenue_model.backtest.data`, loads real A-share annual
revenue from akshare with an on-disk CSV cache — import it explicitly
(``from revenue_model.backtest.data import load_annual_revenue``); it lazy-
imports akshare.

So ``import revenue_model.backtest`` works with zero extras installed. Only
using Holt/ARIMA (needs ``pip install -e ".[backtest]"`` for statsmodels) or
the data loader (needs akshare) triggers a lazy import with a clear hint.
"""

from . import metrics
from .methods import (
    ForecastMethod,
    Naive,
    LinearTrend,
    LogLinearCAGR,
    HoltLinear,
    ARIMA,
    default_methods,
)
from .rolling import (
    StepResult,
    MethodScore,
    rolling_backtest,
    evaluate,
    score_table,
)

__all__ = [
    "metrics",
    "ForecastMethod",
    "Naive",
    "LinearTrend",
    "LogLinearCAGR",
    "HoltLinear",
    "ARIMA",
    "default_methods",
    "StepResult",
    "MethodScore",
    "rolling_backtest",
    "evaluate",
    "score_table",
]
