"""Track B runner: profile-default vs naive per-driver trend, warning
ledger, and MC scenario coverage for weak-fit trees. FY2025 is touched
exactly once, here, as-is (pre-registered protocol section 4).

Run:  python run_track_b.py
Out:  data/track_b_results.txt, data/track_b_summary.csv
"""
import csv
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from revenue_model import (  # noqa: E402
    forecast_segment, check_segment, segment_warnings, simulate_segment,
    scenarios,
)
from track_b_trees import build_trees, MC_RANGES, smape  # noqa: E402

DATA = os.path.join(HERE, "data")


def ols_forecast(years, values, target_years):
    """Pure-stdlib OLS trend extrapolation (the naive per-driver mode)."""
    n = len(years)
    mx = sum(years) / n
    my = sum(values) / n
    sxx = sum((x - mx) ** 2 for x in years)
    slope = sum((x - mx) * (y - my) for x, y in zip(years, values)) / sxx if sxx else 0.0
    intercept = my - slope * mx
    return {y: intercept + slope * y for y in target_years}


def naive_forecast(seg, test_years):
    """Naive mode: linear-trend every driver, multiply out."""
    parts = {}
    for kind in ("base", "penetration", "share", "price"):
        d = getattr(seg, kind)
        yrs = sorted(d.values)
        parts[kind] = ols_forecast(yrs, [d.values[y] for y in yrs], test_years)
    return {y: parts["base"][y] * parts["penetration"][y]
            * parts["share"][y] * parts["price"][y] for y in test_years}, parts


def main():
    trees = build_trees()
    out = []
    rows = []
    warn_ledger = []

    out.append("TRACK B -- DRIVER-LAYER RESULTS (v0.16 API, hand-built trees)")
    out.append("test year touched once; NVDA trees use their legacy FY24-25 split\n")

    for key, t in trees.items():
        seg = t["segment"]
        ty = t["test_years"]
        out.append("=" * 84)
        out.append(f" {key}  [{t['profile']} / {t['fit']}]  -- {t['note']}")
        out.append("=" * 84)

        # 1) warnings BEFORE the test is opened
        checks = list(check_segment(seg))
        warns = list(segment_warnings(seg))
        # H3 alarm = weak-redirect text (point forecast declared unreliable);
        # adapt/strong profiles also emit ADVISORY notes (method guidance) --
        # those are not alarms and do not count as false positives.
        def _is_alarm(msgs):
            return any(("weak fit" in m or "unreliable" in m) for m in msgs)
        alarm = _is_alarm(warns) or _is_alarm(checks)
        if t["fit"] == "weak":
            warn_ledger.append((key, t["fit"], "warned", alarm))
        else:
            warn_ledger.append((key, t["fit"], "false-alarm", alarm))
        for w in checks:
            out.append(f"   CHECK : {w}")
        for w in warns:
            out.append(f"   WARN  : {w}")
        if not checks and not warns:
            out.append("   (no checks/warnings fired)")

        # 2) forecasts
        fc = forecast_segment(seg, ty)
        pred_profile = [fc.revenue(y) for y in ty]
        pred_naive, naive_parts = naive_forecast(seg, ty)
        actual = [t["actual_test"][y] for y in ty]

        s_profile = smape(pred_profile, actual)
        s_naive = smape([pred_naive[y] for y in ty], actual)

        out.append(f"   {'year':>6} {'actual':>12} {'profile':>12} "
                   f"{'naive-trend':>12}")
        for y, a in zip(ty, actual):
            out.append(f"   {y:>6} {a:>12,.1f} {fc.revenue(y):>12,.1f} "
                       f"{pred_naive[y]:>12,.1f}")
        out.append(f"   sMAPE: profile-default {s_profile:5.1f}%   "
                   f"naive per-driver trend {s_naive:5.1f}%")

        # driver attribution (profile mode)
        out.append("   profile-mode drivers: " + "  ".join(
            f"{k}[{getattr(fc, k).values.get(y, float('nan')):,.3g}]"
            for k in ("base", "penetration", "share", "price")
            for y in ty[-1:]))
        out.append("   naive-mode drivers:    " + "  ".join(
            f"{k}[{naive_parts[k][ty[-1]]:,.3g}]"
            for k in ("base", "penetration", "share", "price")))

        # 3) MC coverage for weak-fit trees
        for y in ty:
            rng = MC_RANGES.get((key, y))
            if rng and t["fit"] == "weak":
                mc = simulate_segment(fc, y, rng, n=5000, seed=0)
                real = t["actual_test"][y]
                pct = 100.0 * sum(1 for v in mc.samples if v < real) / len(mc.samples)
                ss = sorted(mc.samples)
                p10 = ss[int(0.10 * len(ss))]
                p90 = ss[int(0.90 * len(ss))]
                covered = p10 <= real <= p90
                out.append(f"   MC FY{y}: P10={p10:,.1f} P50={mc.percentiles['p50'] if 'p50' in mc.percentiles else mc.median:,.1f} "
                           f"P90={p90:,.1f} | actual {real:,.1f} = P{pct:.0f} "
                           f"-> {'COVERED' if covered else 'OUTSIDE P10-P90'}")
                rows.append(dict(tree=key, profile=t["profile"], fit=t["fit"],
                                 year=y, mode="mc_p10", value=p10))
                rows.append(dict(tree=key, profile=t["profile"], fit=t["fit"],
                                 year=y, mode="mc_p90", value=p90))

        for y, a in zip(ty, actual):
            rows.append(dict(tree=key, profile=t["profile"], fit=t["fit"],
                             year=y, mode="actual", value=a))
            rows.append(dict(tree=key, profile=t["profile"], fit=t["fit"],
                             year=y, mode="profile", value=fc.revenue(y)))
            rows.append(dict(tree=key, profile=t["profile"], fit=t["fit"],
                             year=y, mode="naive", value=pred_naive[y]))
        rows.append(dict(tree=key, profile=t["profile"], fit=t["fit"],
                         year=0, mode="smape_profile", value=round(s_profile, 2)))
        rows.append(dict(tree=key, profile=t["profile"], fit=t["fit"],
                         year=0, mode="smape_naive", value=round(s_naive, 2)))
        out.append("")

    # warning ledger
    out.append("=" * 84)
    out.append(" WARNING LEDGER (H3: the engine must say so in advance)")
    out.append(" alarm = weak-redirect text; adapt/strong advisory notes are")
    out.append(" method guidance, not alarms")
    out.append("=" * 84)
    weak_total = weak_hit = 0
    strong_total = strong_fa = 0
    for key, fit, kind, fired in warn_ledger:
        out.append(f" {key:14s} [{fit:5s}] {kind:12s} : {'YES' if fired else 'no'}")
        if fit == "weak":
            weak_total += 1
            weak_hit += int(fired)
        else:
            strong_total += 1
            strong_fa += int(fired)
    out.append(f" warning hit rate (weak warned): {weak_hit}/{weak_total}")
    out.append(f" false-alarm rate (strong/adapt warned): {strong_fa}/{strong_total}")

    text = "\n".join(out)
    path = os.path.join(DATA, "track_b_results.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    with open(os.path.join(DATA, "track_b_summary.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["tree", "profile", "fit", "year",
                                          "mode", "value"])
        w.writeheader()
        w.writerows(rows)
    print(text)
    print(f"-> {path}")


if __name__ == "__main__":
    main()
