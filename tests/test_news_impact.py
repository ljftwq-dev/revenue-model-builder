"""Tests for news_impact — stdlib statistics + honest study aggregation.

Reference p-values were computed with scipy (documented constants; scipy is
NOT imported here — the library core stays zero-dependency).
"""
import math
from datetime import date, datetime

import pytest

from revenue_model.news_impact import (
    MWUResult, WelchResult, align_first_after, bonferroni_alpha,
    event_study, mann_whitney_u, welch_test, _t_sf_two_sided)


# ---- Welch t ----------------------------------------------------------------

def test_welch_matches_scipy_reference():
    a = [0.05, -0.02, 0.11, 0.03, 0.07, -0.04, 0.09, 0.02, 0.06, -0.01,
         0.08, 0.04]
    b = [0.01, 0.00, 0.02, -0.01, 0.015, 0.03, -0.005, 0.012, 0.02, 0.005,
         -0.002, 0.018, 0.025, 0.008]
    r = welch_test(a, b)
    assert r.t == pytest.approx(2.161110, abs=1e-5)
    assert r.p == pytest.approx(0.05118313, abs=1e-7)


def test_welch_identical_samples_give_zero_t():
    r = welch_test([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    assert r.t == pytest.approx(0.0)
    assert r.p == pytest.approx(1.0)


def test_welch_rejects_degenerate_input():
    with pytest.raises(ValueError):
        welch_test([1.0], [1.0, 2.0])
    with pytest.raises(ValueError):
        welch_test([5.0, 5.0], [5.0, 5.0])  # both constant -> zero variance


def test_t_sf_known_constants():
    assert _t_sf_two_sided(2.0, 10) == pytest.approx(0.0733880, abs=1e-6)
    assert _t_sf_two_sided(1.0, 1) == pytest.approx(0.5, abs=1e-9)
    assert _t_sf_two_sided(2.5, 3.7) == pytest.approx(0.071822, abs=1e-5)


# ---- Mann-Whitney U -----------------------------------------------------------

def test_mwu_matches_scipy_reference():
    a = [0.05, -0.02, 0.11, 0.03, 0.07, -0.04, 0.09, 0.02, 0.06, -0.01,
         0.08, 0.04]
    b = [0.01, 0.00, 0.02, -0.01, 0.015, 0.03, -0.005, 0.012, 0.02, 0.005,
         -0.002, 0.018, 0.025, 0.008]
    r = mann_whitney_u(a, b)
    assert r.u == pytest.approx(45.0)
    assert r.p == pytest.approx(0.04745010, abs=1e-7)


def test_mwu_handles_ties():
    a = [1, 1, 2, 2, 3, 3, 4, 5, 6] * 2
    b = [2, 2, 2, 3, 3, 4, 4, 4, 5] * 2
    r = mann_whitney_u(a, b)
    assert r.u == pytest.approx(140.0)
    assert r.p == pytest.approx(0.48625606, abs=1e-7)


def test_mwu_completely_separated_samples():
    r = mann_whitney_u([10.0] * 8, [1.0] * 8)
    assert r.u == pytest.approx(0.0)
    assert r.p < 0.001


# ---- alignment -----------------------------------------------------------------

def test_align_first_after_basic():
    series = {date(2024, 3, 31): 0.1, date(2024, 6, 30): 0.2,
              date(2024, 9, 30): 0.3}
    assert align_first_after(date(2024, 1, 15), series) == 0.1
    assert align_first_after(date(2024, 4, 2), series) == 0.2
    # strictly after: an event ON the quarter end maps to the NEXT quarter
    assert align_first_after(date(2024, 3, 31), series) == 0.2


def test_align_first_after_mixed_date_datetime():
    series = {datetime(2024, 3, 31): 0.1, date(2024, 6, 30): 0.2}
    assert align_first_after(datetime(2024, 2, 1), series) == 0.1


def test_align_first_after_event_beyond_series():
    assert align_first_after(date(2030, 1, 1), {date(2024, 3, 31): 0.1}) is None


# ---- multiplicity + pooled study ---------------------------------------------

def test_bonferroni_alpha():
    assert bonferroni_alpha(1) == 0.05
    assert bonferroni_alpha(10) == pytest.approx(0.005)
    assert bonferroni_alpha(0) == 0.05  # degenerate: no correction


def _sample(seed: int, n: int):
    import random
    rng = random.Random(seed)
    return [rng.gauss(0.0, 1.0) for _ in range(n)]


def test_event_study_pools_across_samples():
    evs = {"A": [(date(2024, 1, 10), "Earnings")] * 5,
           "B": [(date(2024, 2, 10), "Earnings")] * 5}
    outs = {"A": {date(2024, 3, 31): 1.0, date(2024, 6, 30): 1.1,
                  date(2024, 9, 30): 0.9, date(2024, 12, 31): 1.2},
            "B": {date(2024, 3, 31): 0.5, date(2024, 6, 30): 0.4,
                  date(2024, 9, 30): 0.6, date(2024, 12, 31): 0.5}}
    res = event_study(evs, outs, min_n=8)
    row = next(r for r in res.rows if r.category == "Earnings")
    assert row.n == 10
    assert res.n_tests == 1
    assert res.bonferroni_alpha == pytest.approx(0.05)
    assert row.welch_p is not None and 0.0 <= row.welch_p <= 1.0


def test_event_study_small_category_reported_without_test():
    evs = {"A": [(date(2024, 1, 10), "M&A")]}
    outs = {"A": {date(2024, 3, 31): 1.0}}
    res = event_study(evs, outs, min_n=8)
    row = res.rows[0]
    assert row.n == 1
    assert row.welch_p is None and row.mwu_p is None
    assert "n < 8" in row.note
    assert res.n_tests == 0  # small categories never inflate the family


def test_event_study_bonferroni_flags():
    """A borderline nominal p survives alpha but not the family correction."""
    evs = {"A": [(date(2024, 1, 10), f"cat{i}") for i in range(20)]}
    outs = {"A": {date(2024, 3, 31): 1.0}}
    res = event_study(evs, outs, min_n=1)
    assert res.n_tests == 20
    assert res.bonferroni_alpha == pytest.approx(0.05 / 20)


def test_event_study_explicit_baseline():
    evs = {"A": [(date(2024, 1, 10), "Earnings")] * 8}
    outs = {"A": {date(2024, 3, 31): 5.0, date(2024, 6, 30): 1.0}}
    base = {"A": [1.0, 1.1, 0.9, 1.05]}
    res = event_study(evs, outs, baseline_by_sample=base, min_n=8)
    row = res.rows[0]
    assert row.baseline_mean == pytest.approx(1.0125)
    assert row.mean == pytest.approx(5.0)
    assert row.significant  # 5.0 vs ~1.0 baseline is clearly different


def test_event_study_ignores_nan_outcomes():
    evs = {"A": [(date(2024, 1, 10), "Earnings")] * 8}
    outs = {"A": {date(2024, 3, 31): float("nan")}}
    res = event_study(evs, outs, min_n=8)
    # the only outcome is NaN -> nothing pools -> category never materializes
    assert res.rows == []
    assert res.n_tests == 0
