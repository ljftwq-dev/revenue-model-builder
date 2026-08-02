"""Rolling backtest engine — fit-on-history, predict-the-next, slide forward.

The protocol that turns a time series + a set of forecasting methods into an
honest out-of-sample evaluation:

    for each split point i in [min_train .. n-horizon]:
        train  = values[:i]
        target = values[i : i+horizon]        # the held-out actuals
        for each method: fit on train, forecast horizon steps
        record actual vs every method's forecast

No method ever sees the value it is asked to predict — that is what
*out-of-sample* means, and it is the only thing that distinguishes a real
backtest from in-sample curve-fitting. Expanding window (train grows each
step) is the default; pass ``fixed_window`` to keep a rolling window of fixed
length instead.

Directional accuracy needs the year *before* the target to define up/down, so
each :class:`StepResult` carries ``prev_actual`` (the last training value).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Sequence

from . import metrics
from .methods import ForecastMethod


@dataclass
class StepResult:
    """One held-out prediction step across all methods."""
    target_year: int
    prev_year: int
    prev_actual: float
    actual: float
    horizon: int
    forecasts: Dict[str, float] = field(default_factory=dict)

    @property
    def actual_direction(self) -> int:
        """+1 if revenue grew vs prev, -1 if shrank, 0 if flat."""
        return _sign(self.actual - self.prev_actual)


def _sign(x: float) -> int:
    if x > 1e-9:
        return 1
    if x < -1e-9:
        return -1
    return 0


def rolling_backtest(
    years: Sequence[int],
    values: Sequence[float],
    methods: Sequence[ForecastMethod],
    *,
    min_train: int = 8,
    horizon: int = 1,
    fixed_window: int = 0,
) -> List[StepResult]:
    """Run an expanding (or fixed) window backtest.

    Parameters
    ----------
    years, values
        Ascending annual actuals. ``values`` in million yuan (engine units).
    methods
        Forecasting methods to compare; each gets the same train slice.
    min_train
        First split point — the shortest history a method may train on.
        Backtesting starts at ``year[min_train]``.
    horizon
        Steps ahead to forecast each split. ``1`` = pure next-year.
    fixed_window
        If > 0, train on only the last ``fixed_window`` points (rolling
        window) instead of all history up to the split (expanding window).

    Returns one :class:`StepResult` per (split, horizon-step); for
    ``horizon=1`` that is one result per held-out year.
    """
    years = list(years)
    values = list(values)
    if len(years) != len(values):
        raise ValueError(f"years/values length mismatch: {len(years)} vs {len(values)}")
    n = len(years)
    if min_train < 2:
        raise ValueError("min_train must be >= 2 (need a trend)")
    if n < min_train + horizon:
        raise ValueError(
            f"not enough data: need >= {min_train + horizon} points for "
            f"min_train={min_train}, horizon={horizon}; got {n}")

    results: List[StepResult] = []
    i = min_train
    while i + horizon <= n:
        start = max(0, i - fixed_window) if fixed_window else 0
        train_y = years[start:i]
        train_v = values[start:i]
        actual_slice = values[i:i + horizon]
        target_years = years[i:i + horizon]
        prev_year = years[i - 1]
        prev_actual = values[i - 1]

        per_method: Dict[str, List[float]] = {}
        for m in methods:
            try:
                per_method[m.name] = m.fit_predict(train_y, train_v, horizon)
            except Exception:
                # a method that fails on this slice is marked NaN; it still
                # appears in the table so the comparison is complete.
                per_method[m.name] = [float("nan")] * horizon

        for h in range(horizon):
            results.append(StepResult(
                target_year=target_years[h],
                prev_year=prev_year if h == 0 else target_years[h - 1],
                prev_actual=prev_actual if h == 0 else actual_slice[h - 1],
                actual=actual_slice[h],
                horizon=horizon,
                forecasts={name: preds[h]
                           for name, preds in per_method.items()},
            ))
        i += 1
    return results


@dataclass
class MethodScore:
    """Aggregate accuracy of one method across all backtest steps."""
    name: str
    n: int
    mae: float
    rmse: float
    mape: float
    smape: float
    r2: float
    directional_accuracy: float

    def as_row(self) -> Dict[str, float]:
        return {
            "method": self.name, "n": self.n,
            "MAE": self.mae, "RMSE": self.rmse,
            "MAPE": self.mape, "sMAPE": self.smape,
            "R2": self.r2, "DirAcc": self.directional_accuracy,
        }


def evaluate(steps: Sequence[StepResult]) -> List[MethodScore]:
    """Compute per-method aggregate metrics from rolling-backtest steps.

    Directional accuracy counts a hit when predicted and actual year-over-year
    direction (up/down) agree. ``sMAPE`` is the headline cross-company number.
    """
    if not steps:
        return []
    method_names = list(steps[0].forecasts.keys())

    def _collect(name: str):
        actuals, preds, dirs = [], [], []
        for s in steps:
            f = s.forecasts.get(name, float("nan"))
            if f != f:  # NaN check
                continue
            actuals.append(s.actual)
            preds.append(f)
            ad = s.actual_direction
            pd = _sign(f - s.prev_actual)
            if ad != 0 or pd != 0:
                dirs.append(1 if ad == pd else 0)
        return actuals, preds, dirs

    scores: List[MethodScore] = []
    for name in method_names:
        actuals, preds, dirs = _collect(name)
        if not actuals:
            scores.append(MethodScore(name, 0, *[float("nan")] * 5,
                                      directional_accuracy=float("nan")))
            continue
        scores.append(MethodScore(
            name=name,
            n=len(actuals),
            mae=metrics.mae(actuals, preds),
            rmse=metrics.rmse(actuals, preds),
            mape=metrics.mape(actuals, preds),
            smape=metrics.smape(actuals, preds),
            r2=metrics.r_squared(actuals, preds),
            directional_accuracy=sum(dirs) / len(dirs) if dirs else float("nan"),
        ))
    return scores


def score_table(scores: Sequence[MethodScore]) -> str:
    """Render scores as a fixed-width text table (for CLI / logs)."""
    cols = ["method", "n", "sMAPE", "MAPE", "MAE", "RMSE", "R2", "DirAcc"]
    header = f"{cols[0]:<10}{cols[1]:>4}{cols[2]:>9}{cols[3]:>9}{cols[4]:>11}{cols[5]:>11}{cols[6]:>8}{cols[7]:>8}"
    lines = [header, "-" * len(header)]
    for s in sorted(scores, key=lambda x: x.smape):
        lines.append(
            f"{s.name:<10}{s.n:>4}"
            f"{_fmt_pct(s.smape):>9}{_fmt_pct(s.mape):>9}"
            f"{_fmt_amt(s.mae):>11}{_fmt_amt(s.rmse):>11}"
            f"{s.r2:>8.2f}{_fmt_pct(s.directional_accuracy):>8}"
        )
    return "\n".join(lines)


def _fmt_pct(x: float) -> str:
    return "  n/a" if x != x else f"{x * 100:6.1f}%"


def _fmt_amt(x: float) -> str:
    return "  n/a" if x != x else f"{x:11.0f}"
