"""Track A battery: 8 methods x 244 companies x 3 forecast years (2023-25).

Protocol (pre-registered in docs/proposal-profile-validation.md):
- expanding window, horizon 1: to forecast year Y, fit on all data <= Y-1
  (train segment <= FY2022, per the split);
- years 2023-2024 = VALIDATION (method selection happens here);
- year 2025 = TEST — computed once, reported as-is;
- per (company, year, method): sMAPE + YoY-direction hit;
- pooled by fit class / by profile.

Run:  python run_battery.py
Out:  data/battery_results.csv, console summary tables
"""
import csv
import os
import sys
import warnings
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from revenue_model.backtest import (
    Naive, LinearTrend, LogLinearCAGR, HoltLinear, ARIMA,
)
from revenue_model.backtest.metrics import smape
from profile_methods import profile_method_set

DATA = os.path.join(HERE, "data")
VALID_YEARS = (2023, 2024)
TEST_YEAR = 2025


def load_panel():
    with open(os.path.join(DATA, "revenue_panel.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    series = defaultdict(dict)      # ticker -> {fy: rev}
    meta = {}
    for r in rows:
        t = r["ticker"]
        series[t][int(r["fy"])] = float(r["revenue_usd"])
        meta[t] = (r["profile"], r["fit"])
    return series, meta


def run():
    warnings.filterwarnings("ignore")   # statsmodels ConvergenceWarnings
    series, meta = load_panel()
    methods = ([Naive(), LinearTrend(), LogLinearCAGR(), HoltLinear(), ARIMA()]
               + profile_method_set())
    print(f"companies {len(series)} | methods {[m.name for m in methods]}")

    results = []
    for t, rev in sorted(series.items()):
        years = sorted(rev)
        for y in (*VALID_YEARS, TEST_YEAR):
            train_y = [yy for yy in years if yy <= y - 1]
            if len(train_y) < 5 or y not in rev:
                continue
            train_v = [rev[yy] for yy in train_y]
            prev = rev[y - 1] if (y - 1) in rev else train_v[-1]
            actual = rev[y]
            for m in methods:
                try:
                    pred = m.fit_predict(train_y, train_v, 1)[0]
                except Exception:
                    continue
                if pred is None or pred != pred:      # NaN guard
                    continue
                s = smape([actual], [pred])
                dir_hit = int((pred - prev) * (actual - prev) > 0)
                results.append(dict(ticker=t, profile=meta[t][0],
                                    fit=meta[t][1], year=y, method=m.name,
                                    smape=s, dir_hit=dir_hit))

    out = os.path.join(DATA, "battery_results.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)
    print(f"rows {len(results)} -> {out}\n")

    def table(years, title):
        print("=" * 86)
        print(f" {title}")
        print("=" * 86)
        sub = [r for r in results if r["year"] in years]
        # median sMAPE per method x fit
        by_mf = defaultdict(list)
        for r in sub:
            by_mf[(r["method"], r["fit"])].append(r["smape"])
        fits = ["strong", "adapt", "weak"]
        print(f" {'method':12s}" + "".join(f"{f:>14s}" for f in fits)
              + f"{'all':>14s}")
        methods_order = [m.name for m in methods]
        for mn in methods_order:
            cells = []
            for f in fits + ["__all__"]:
                vals = by_mf.get((mn, f), []) if f != "__all__" else \
                    [r["smape"] for r in sub if r["method"] == mn]
                cells.append(f"{_median(vals):13.1f}%"
                             if vals else f"{'--':>14s}")
            print(f" {mn:12s}" + "".join(cells))
        print()

    def _median(vals):
        v = sorted(vals)
        n = len(v)
        if n == 0:
            return float("nan")
        return 100 * (v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2]))

    table(VALID_YEARS, f"VALIDATION {VALID_YEARS} (method selection here)")
    table((TEST_YEAR,), f"TEST FY{TEST_YEAR} (touched once, as-is)")

    # win counts on validation, per fit class
    print("=" * 86)
    print(" VALIDATION win counts (per fit class: #companies where method is best)")
    print("=" * 86)
    sub = [r for r in results if r["year"] in VALID_YEARS]
    per_co = defaultdict(dict)
    for r in sub:
        per_co[(r["ticker"], r["fit"], r["year"])][r["method"]] = r["smape"]
    wins = defaultdict(lambda: defaultdict(int))
    for (t, f, y), d in per_co.items():
        best = min(d, key=d.get)
        wins[f][best] += 1
    for f in ("strong", "adapt", "weak"):
        total = sum(wins[f].values())
        top = sorted(wins[f].items(), key=lambda kv: -kv[1])[:4]
        pretty = ", ".join(f"{k}:{v}" for k, v in top)
        print(f" {f:8s} n={total:4d}  {pretty}")


if __name__ == "__main__":
    run()
