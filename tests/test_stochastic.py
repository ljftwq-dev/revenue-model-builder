"""Tests for the stochastic layer — validate numerics against analytic solutions.

These tests are the whole point of using stochastic processes: they prove the
Euler-Maruyama paths converge to the known closed-form means/variances, the
logit-OU stays bounded, and Cholesky induces the requested correlation. Pure
stdlib, no network, fixed seeds.
"""
import math
import statistics

from revenue_model.stochastic import (
    GBMDriver, OUDriver, LogitOUDriver, CorrelatedBundle, simulate_revenue,
    randn, cholesky, sigmoid, logit,
)
from revenue_model.demo import build_novatech

import random


# ----------------------------- primitives --------------------------------- #

def test_randn_is_standard_normal():
    rng = random.Random(0)
    xs = [randn(rng) for _ in range(100000)]
    assert abs(statistics.fmean(xs)) < 0.02          # mean ~ 0
    assert abs(statistics.pstdev(xs) - 1.0) < 0.02    # std ~ 1


def test_cholesky_factors_spd_matrix():
    A = [[4.0, 2.0], [2.0, 3.0]]
    L = cholesky(A)
    assert abs(L[0][0] - 2.0) < 1e-9
    assert abs(L[1][0] - 1.0) < 1e-9
    assert abs(L[1][1] - math.sqrt(2.0)) < 1e-9
    # reconstruct A = L Lᵀ
    LLt = [[sum(L[i][k] * L[j][k] for k in range(2)) for j in range(2)] for i in range(2)]
    for i in range(2):
        for j in range(2):
            assert abs(LLt[i][j] - A[i][j]) < 1e-9


def test_cholesky_rejects_non_spd():
    try:
        cholesky([[1.0, 2.0], [2.0, 1.0]])            # indefinite
    except ValueError:
        return
    raise AssertionError("expected ValueError for non-positive-definite matrix")


def test_sigmoid_logit_roundtrip():
    for p in (0.1, 0.3, 0.5, 0.7, 0.95):
        assert abs(sigmoid(logit(p)) - p) < 1e-12


def test_sigmoid_bounded():
    assert 0.0 <= sigmoid(-1000) < 1e-9
    assert 1.0 - 1e-9 < sigmoid(1000) <= 1.0


# ------------------------------- GBM -------------------------------------- #

def test_gbm_mean_matches_closed_form():
    # E[S_T] = S0 * exp(mu * T)  for geometric Brownian motion
    d = GBMDriver("price", S0=100.0, mu=0.05, sigma=0.20, T=1.0, dt=0.005)
    xs = d.sample(20000, random.Random(1))
    expected = 100.0 * math.exp(0.05 * 1.0)
    assert abs(statistics.fmean(xs) - expected) / expected < 0.08


def test_gbm_log_variance_matches_closed_form():
    # Var[ln S_T] = sigma^2 * T
    d = GBMDriver("price", S0=100.0, mu=0.05, sigma=0.20, T=1.0, dt=0.005)
    xs = d.sample(20000, random.Random(2))
    log_xs = [math.log(x) for x in xs if x > 0.0]
    assert abs(statistics.pvariance(log_xs) - 0.20 ** 2 * 1.0) / (0.20 ** 2) < 0.20


def test_gbm_stays_nonnegative():
    d = GBMDriver("price", S0=100.0, mu=0.0, sigma=0.50, T=2.0, dt=0.01)
    xs = d.sample(5000, random.Random(3))
    assert all(x >= 0.0 for x in xs)


# ------------------------------- OU --------------------------------------- #

def test_ou_stationary_mean_and_variance():
    # Long run: E[x] -> mu, Var[x] -> sigma^2 / (2*theta)
    d = OUDriver("x", x0=0.5, theta=2.0, mu=0.15, sigma=0.10, T=10.0, dt=0.01)
    xs = d.sample(20000, random.Random(4))
    assert abs(statistics.fmean(xs) - 0.15) < 0.02
    expected_var = 0.10 ** 2 / (2 * 2.0)
    assert abs(statistics.pvariance(xs) - expected_var) / expected_var < 0.35


def test_ou_reverts_to_mean():
    # start above mu, large theta -> pulled down toward mu
    d = OUDriver("x", x0=0.9, theta=5.0, mu=0.2, sigma=0.02, T=2.0, dt=0.01)
    xs = d.sample(5000, random.Random(5))
    mean = statistics.fmean(xs)
    assert mean < 0.9                        # pulled down from 0.9
    assert 0.15 < mean < 0.30                # reverts to near mu=0.2, no large overshoot


# ----------------------------- LogitOU ------------------------------------ #

def test_logitou_always_in_unit_interval():
    d = LogitOUDriver("p", p0=0.1, theta=2.0, mu_bar=logit(0.2),
                      sigma=0.4, T=2.0, dt=0.01)
    xs = d.sample(20000, random.Random(6))
    assert all(0.0 < x < 1.0 for x in xs)


def test_logitou_reverts_toward_target():
    # start low (0.05), target 0.3, low noise -> mean should climb well above p0
    d = LogitOUDriver("p", p0=0.05, theta=3.0, mu_bar=logit(0.3),
                      sigma=0.05, T=4.0, dt=0.01)
    xs = d.sample(10000, random.Random(7))
    assert statistics.fmean(xs) > 0.15


def test_logitou_output_is_probability_like():
    # high mu_bar (logit(0.9)) + strong reversion -> mean near 0.9
    d = LogitOUDriver("p", p0=0.5, theta=4.0, mu_bar=logit(0.9),
                      sigma=0.05, T=6.0, dt=0.01)
    xs = d.sample(10000, random.Random(8))
    assert statistics.fmean(xs) > 0.75


# -------------------------- CorrelatedBundle ------------------------------ #

def _pearson(xs, ys):
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sx = statistics.pstdev(xs)
    sy = statistics.pstdev(ys)
    if sx == 0 or sy == 0:
        return 0.0
    n = len(xs)
    return sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / (n * sx * sy)


def test_correlated_bundle_induces_rho():
    a = GBMDriver("a", S0=100.0, mu=0.03, sigma=0.20, T=1.0, dt=0.01)
    b = GBMDriver("b", S0=50.0, mu=0.02, sigma=0.15, T=1.0, dt=0.01)
    bundle = CorrelatedBundle([a, b], rho=[[1.0, 0.6], [0.6, 1.0]], T=1.0, dt=0.01)
    out = bundle.sample(20000, random.Random(9))
    r = _pearson(out["a"], out["b"])
    assert abs(r - 0.6) < 0.08


def test_correlated_bundle_rejects_bad_shape():
    a = GBMDriver("a", S0=100.0, mu=0.0, sigma=0.1)
    b = GBMDriver("b", S0=50.0, mu=0.0, sigma=0.1)
    try:
        CorrelatedBundle([a, b], rho=[[1.0, 0.5], [0.5]])   # ragged
    except ValueError:
        return
    raise AssertionError("expected ValueError for ragged rho")


def test_correlated_bundle_rejects_non_unit_diagonal():
    a = GBMDriver("a", S0=100.0, mu=0.0, sigma=0.1)
    try:
        CorrelatedBundle([a], rho=[[0.9]])
    except ValueError:
        return
    raise AssertionError("expected ValueError for non-unit diagonal")


# ------------------------- simulate_revenue ------------------------------- #

def test_simulate_revenue_returns_distribution():
    seg = build_novatech().segments[0]   # 舱内-国内
    price = GBMDriver("DMS 套件单价（国内）", S0=650.0, mu=0.0, sigma=0.10, T=1.0, dt=0.02)
    share = LogitOUDriver("NovaTech 国内市占率", p0=0.14, theta=2.0,
                          mu_bar=logit(0.14), sigma=0.10, T=1.0, dt=0.02)
    mc = simulate_revenue(seg, 2024, {"DMS 套件单价（国内）": price,
                                      "NovaTech 国内市占率": share},
                          n=10000, seed=0)
    # deterministic 2024 revenue of this segment: 24.0 * 0.09 * 0.14 * 650 = 196.56
    det = 24.0 * 0.09 * 0.14 * 650.0
    assert all(v > 0.0 for v in mc.samples)
    # mean should be in the same ballpark as the deterministic revenue
    assert 0.4 * det < mc.mean < 2.0 * det
    # spread exists (it's a distribution, not a point)
    assert mc.stdev > 0.0
    assert mc.percentiles["p95"] > mc.percentiles["p5"]


def test_simulate_revenue_rejects_unknown_driver():
    seg = build_novatech().segments[0]
    price = GBMDriver("no-such-driver", S0=650.0, mu=0.0, sigma=10.0)
    try:
        simulate_revenue(seg, 2024, {"no-such-driver": price}, n=100, seed=0)
    except KeyError:
        return
    raise AssertionError("expected KeyError for unknown driver name")
