"""Backtest engine tests: metrics, methods, rolling, evaluate."""

import math

import pytest

from revenue_model.backtest import metrics
from revenue_model.backtest.methods import (
    Naive, LinearTrend, LogLinearCAGR, default_methods,
)
from revenue_model.backtest.rolling import (
    rolling_backtest, evaluate, score_table,
)


# ---- metrics ---------------------------------------------------------------

def test_mae_and_rmse_basic():
    assert metrics.mae([100, 200], [110, 190]) == pytest.approx(10.0)
    assert metrics.rmse([100, 200], [110, 190]) == pytest.approx(10.0)


def test_mae_zero_on_perfect():
    assert metrics.mae([5, 7, 9], [5, 7, 9]) == 0.0


def test_mape_basic():
    # 10/100 + 10/200 = 0.075
    assert metrics.mape([100, 200], [110, 190]) == pytest.approx(0.075)


def test_mape_skips_near_zero():
    # one near-zero point is skipped, only the 100 point counts: 10/100=0.1
    assert metrics.mape([0.0, 100], [50, 110]) == pytest.approx(0.1)


def test_smape_bounded_and_symmetric():
    s1 = metrics.smape([100], [150])   # 50 / 125 = 0.4
    s2 = metrics.smape([150], [100])   # symmetric -> same
    assert s1 == pytest.approx(0.4)
    assert s2 == pytest.approx(0.4)
    assert 0.0 <= s1 <= 2.0


def test_r_squared_perfect_and_negative():
    assert metrics.r_squared([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)
    # predicting the mean -> R2 = 0
    m = 150
    assert metrics.r_squared([100, 200], [m, m]) == pytest.approx(0.0)
    # worse than the mean -> negative
    assert metrics.r_squared([100, 200], [300, 0]) < 0


def test_metrics_reject_unequal_lengths():
    with pytest.raises(ValueError):
        metrics.mae([1, 2], [1])
    with pytest.raises(ValueError):
        metrics.smape([], [])


# ---- methods ---------------------------------------------------------------

def test_naive_returns_last():
    assert Naive().fit_predict([2020, 2021, 2022], [10, 20, 30], 2) == [30, 30]


def test_linear_trend_extrapolates_line():
    pred = LinearTrend().fit_predict([2020, 2021, 2022], [10, 20, 30], 2)
    # slope 10/yr; 2023 -> 40, 2024 -> 50
    assert pred[0] == pytest.approx(40.0)
    assert pred[1] == pytest.approx(50.0)


def test_cagr_extrapolates_geometric():
    pred = LogLinearCAGR().fit_predict([1, 2, 3], [100, 200, 400], 1)
    # doubling/yr -> 800 at year 4
    assert pred[0] == pytest.approx(800.0, rel=1e-6)


def test_cagr_rejects_nonpositive():
    with pytest.raises(ValueError):
        LogLinearCAGR().fit_predict([1, 2], [100, 0], 1)


def test_default_methods_have_unique_names():
    names = [m.name for m in default_methods()]
    assert len(names) == len(set(names))
    assert "Naive" in names and "Linear" in names


# ---- rolling ---------------------------------------------------------------

def _series(n=10, start=2015, base=100.0, growth=0.2):
    years = list(range(start, start + n))
    values = [base * (1 + growth) ** (i) for i in range(n)]
    return years, values


def test_rolling_step_count():
    years, values = _series(n=10)
    steps = rolling_backtest(years, values, [Naive(), LinearTrend()],
                             min_train=8, horizon=1)
    # splits at i=8,9 -> 2 held-out years (2023, 2024)
    assert len(steps) == 2
    assert [s.target_year for s in steps] == [2023, 2024]


def test_rolling_prev_actual_is_last_train_value():
    years, values = _series(n=10)
    steps = rolling_backtest(years, values, [Naive()], min_train=8, horizon=1)
    s = steps[0]
    assert s.prev_year == 2022
    assert s.prev_actual == pytest.approx(values[7])
    assert s.actual == pytest.approx(values[8])


def test_rolling_is_out_of_sample():
    # Naive must equal the last training value, never peek at target.
    years, values = [2020, 2021, 2022, 2023], [10, 20, 30, 999]
    steps = rolling_backtest(years, values, [Naive()], min_train=3, horizon=1)
    assert steps[0].forecasts["Naive"] == pytest.approx(30.0)
    assert steps[0].actual == 999


def test_rolling_horizon_multi_step():
    years, values = _series(n=10)
    steps = rolling_backtest(years, values, [Naive()], min_train=8, horizon=2)
    # one split (i=8) producing 2 steps
    assert len(steps) == 2
    assert steps[0].target_year == 2023 and steps[1].target_year == 2024


def test_rolling_rejects_short_series():
    with pytest.raises(ValueError):
        rolling_backtest([2020, 2021], [1, 2], [Naive()], min_train=8)


def test_evaluate_scores_all_methods():
    years, values = _series(n=12, growth=0.15)
    steps = rolling_backtest(years, values, [Naive(), LinearTrend()],
                             min_train=8, horizon=1)
    scores = evaluate(steps)
    assert len(scores) == 2
    names = {s.name for s in scores}
    assert names == {"Naive", "Linear"}
    for s in scores:
        assert s.n >= 1
        assert s.smape >= 0.0


def test_evaluate_linear_beats_naive_on_clean_trend():
    # On a perfectly linear series LinearTrend is exact -> sMAPE ~ 0, beating
    # Naive (which lags by one slope step).
    years = list(range(2010, 2024))
    values = [1000.0 + 200 * (y - 2010) for y in years]
    steps = rolling_backtest(years, values, [Naive(), LinearTrend()],
                             min_train=8, horizon=1)
    sc = {s.name: s.smape for s in evaluate(steps)}
    assert sc["Linear"] == pytest.approx(0.0, abs=1e-6)
    assert sc["Linear"] < sc["Naive"]


def test_directional_accuracy_all_correct_on_monotone():
    # strictly increasing series.
    years, values = _series(n=12, growth=0.1)
    steps = rolling_backtest(years, values, [Naive(), LinearTrend()],
                             min_train=8, horizon=1)
    sc = {s.name: s.directional_accuracy for s in evaluate(steps)}
    # LinearTrend has a positive slope -> predicts "up" every step on a
    # strictly increasing series -> 100% direction hits.
    assert sc["Linear"] == pytest.approx(1.0)
    # Naive forecasts "no change" (flat, dir 0) -> never matches the actual
    # up-move, so it scores 0% on direction. Counter-intuitive but honest:
    # Naive carries no directional information.
    assert sc["Naive"] == pytest.approx(0.0)


def test_score_table_renders():
    years, values = _series(n=12, growth=0.15)
    steps = rolling_backtest(years, values, [Naive(), LinearTrend()],
                             min_train=8, horizon=1)
    table = score_table(evaluate(steps))
    assert "sMAPE" in table and "Naive" in table and "Linear" in table


# ---- statsmodels-backed methods (optional) ---------------------------------

def test_holt_and_arima_run_with_statsmodels():
    pytest.importorskip("statsmodels")
    from revenue_model.backtest.methods import HoltLinear, ARIMA
    years, values = _series(n=12, growth=0.2)
    for m in (HoltLinear(), ARIMA()):
        pred = m.fit_predict(years, values, 1)
        assert len(pred) == 1
        assert pred[0] > 0 and math.isfinite(pred[0])
