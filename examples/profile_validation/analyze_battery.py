"""Track A statistical analysis (pre-registered spec section 5).

Reads data/battery_results.csv (already computed; test year touched once)
 and produces the inference layer:

- pooled median sMAPE by fit class, per method (validation vs test);
- directional accuracy (YoY sign hit rate);
- method win counts per profile (does the profile-implied family win?);
- paired Wilcoxon signed-rank (pure stdlib, normal approximation with
  tie/continuity correction): each method vs Naive on its target bucket,
  plus profile-implied champion vs Naive per profile;
- Bonferroni over the 10-profile family; effect sizes (rank-biserial r)
  reported alongside p-values -- annual data = tiny n, effects over stars.

Profile-implied champions (from v0.16 driver defaults, revenue-layer
translation recorded in profile_methods.py):
- strong bucket: trend family (Linear/CAGR/Holt)  -> test LinearTrend vs Naive
- adapt bucket:   damped family                    -> test Damped vs Naive
- weak bucket:    Naive (point fc is the baseline the engine redirects from)
- saas_subscription   : DecelCAGR vs Naive
- industrial_capacity : Damped vs Naive
- commodity_cyclical  : GrowthRevert vs Naive

Run:  python analyze_battery.py
Out:  data/analysis_summary.txt (findings file, cited by the report)
"""
import csv
import math
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
VALID_YEARS = (2023, 2024)
TEST_YEAR = 2025

METHODS = ["Naive", "Linear", "CAGR", "Holt", "ARIMA",
           "Damped", "DecelCAGR", "GrowthRevert"]
FITS = ["strong", "adapt", "weak"]

# profile-implied champions (method -> the profiles whose defaults it came from)
PROFILE_CHAMPION = {
    "saas_subscription": "DecelCAGR",
    "industrial_capacity": "Damped",
    "commodity_cyclical": "GrowthRevert",
    "telecom_subscriber": "DecelCAGR",   # logistic/hold family (secondary)
}


def load():
    with open(os.path.join(DATA, "battery_results.csv"), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def median(v):
    v = sorted(v)
    n = len(v)
    return float("nan") if n == 0 else (v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2]))


def p90(v):
    v = sorted(v)
    return v[min(len(v) - 1, int(math.ceil(0.90 * len(v))) - 1)] if v else float("nan")


def mean(v):
    return sum(v) / len(v) if v else float("nan")


# ---------------- pure-stdlib Wilcoxon signed-rank ----------------

def _norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def wilcoxon(diffs):
    """Two-sided Wilcoxon signed-rank, normal approx with tie correction +
    continuity correction. Returns (n, z, p, rank_biserial_r)."""
    d = [x for x in diffs if x != 0.0]
    n = len(d)
    if n < 5:
        return n, float("nan"), float("nan"), float("nan")
    # ranks of |d| with average ties
    order = sorted(range(n), key=lambda i: abs(d[i]))
    ranks = [0.0] * n
    i = 0
    tie_term = 0.0
    while i < n:
        j = i
        while j + 1 < n and abs(d[order[j + 1]]) == abs(d[order[i]]):
            j += 1
        m = j - i + 1
        avg = (i + 1 + j + 1) / 2.0
        tie_term += m ** 3 - m
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    w_plus = sum(r for r, x in zip(ranks, d) if x > 0)
    w_minus = sum(r for r, x in zip(ranks, d) if x < 0)
    mu = n * (n + 1) / 4.0
    var = n * (n + 1) * (2 * n + 1) / 24.0 - tie_term / 48.0
    if var <= 0:
        return n, float("nan"), float("nan"), float("nan")
    z = (w_plus - mu - 0.5 * math.copysign(1.0, w_plus - mu)) / math.sqrt(var)
    p = 2.0 * min(_norm_sf(z), _norm_sf(-z))
    r_rb = (w_plus - w_minus) / (w_plus + w_minus)   # rank-biserial, in [-1,1]
    return n, z, p, r_rb


# --------------------------------------------------------------------

def per_group(rows, key):
    g = defaultdict(list)
    for r in rows:
        g[key(r)].append(r)
    return g


def table_median(rows, title, out):
    by_mf = defaultdict(list)
    for r in rows:
        by_mf[(r["method"], r["fit"])].append(float(r["smape"]))
    lines = ["=" * 88, f" {title}", "=" * 88,
             f" {'method':12s}" + "".join(f"{f + ' med':>13s}" for f in FITS)
             + f"{'all med':>13s}{'P90 all':>10s}{'dir%':>7s}"]
    dir_by_m = defaultdict(list)
    for r in rows:
        dir_by_m[r["method"]].append(int(r["dir_hit"]))
    for mn in METHODS:
        cells = []
        for f in FITS:
            v = by_mf.get((mn, f), [])
            cells.append(f"{100 * median(v):12.1f}%" if v else f"{'--':>13s}")
        allv = [float(r["smape"]) for r in rows if r["method"] == mn]
        d = dir_by_m.get(mn, [])
        lines.append(f" {mn:12s}" + "".join(cells)
                     + f"{100 * median(allv):12.1f}%{100 * p90(allv):9.1f}%"
                     + (f"{100 * mean(d):6.0f}%" if d else "    --"))
    out.extend(lines + [""])


def win_table(rows, title, out):
    per_co = defaultdict(dict)
    for r in rows:
        per_co[(r["ticker"], r["year"])][r["method"]] = float(r["smape"])
    wins = defaultdict(lambda: defaultdict(int))
    for (t, y), d in per_co.items():
        best = min(d, key=d.get)
        wins[(rows_meta[t],)][best] += 0  # placeholder no-op (profile via rows)
    # simpler: recompute with profile
    per_co2 = defaultdict(dict)
    meta = {}
    for r in rows:
        meta[r["ticker"]] = (r["profile"], r["fit"])
        per_co2[(r["ticker"], r["year"])][r["method"]] = float(r["smape"])
    wins2 = defaultdict(lambda: defaultdict(int))
    for (t, y), d in per_co2.items():
        best = min(d, key=d.get)
        wins2[meta[t][0]][best] += 1
    lines = ["=" * 88, f" {title}", "=" * 88]
    for prof in sorted(wins2):
        total = sum(wins2[prof].values())
        top = sorted(wins2[prof].items(), key=lambda kv: -kv[1])[:3]
        champ = PROFILE_CHAMPION.get(prof)
        champ_n = wins2[prof].get(champ, 0) if champ else 0
        pretty = ", ".join(f"{k}:{v}" for k, v in top)
        mark = f"  [champion {champ}={champ_n}/{total}]" if champ else ""
        lines.append(f" {prof:22s} n={total:4d}  {pretty}{mark}")
    out.extend(lines + [""])


rows_meta = {}


def wilcoxon_tests(rows, label, out, bonferroni=10):
    """Paired tests: per hypothesis, method A vs Naive on its target bucket."""
    def pairs(method, fit=None, profile=None):
        sel = [r for r in rows if r["method"] == "Naive"]
        a = {(r["ticker"], r["year"]): float(r["smape"]) for r in rows
             if r["method"] == method
             and ((fit is None or r["fit"] == fit)
                  and (profile is None or r["profile"] == profile))}
        b = {(r["ticker"], r["year"]): float(r["smape"]) for r in sel
             if (fit is None or r["fit"] == fit)
             and (profile is None or r["profile"] == profile)}
        keys = sorted(set(a) & set(b))
        return [a[k] for k in keys], [b[k] for k in keys]

    tests = [
        ("H1 strong: LinearTrend vs Naive", "Linear", dict(fit="strong")),
        ("H1 strong: CAGR vs Naive", "CAGR", dict(fit="strong")),
        ("H2 adapt: Damped vs Naive", "Damped", dict(fit="adapt")),
        ("H2 adapt: DecelCAGR vs Naive", "DecelCAGR", dict(fit="adapt")),
        ("saas: DecelCAGR vs Naive", "DecelCAGR", dict(profile="saas_subscription")),
        ("industrial: Damped vs Naive", "Damped", dict(profile="industrial_capacity")),
        ("commodity: GrowthRevert vs Naive", "GrowthRevert", dict(profile="commodity_cyclical")),
        ("telecom: DecelCAGR vs Naive", "DecelCAGR", dict(profile="telecom_subscriber")),
    ]
    lines = ["=" * 88, f" {label}  (Wilcoxon signed-rank vs Naive, two-sided;"
             f" Bonferroni x{bonferroni}; r = rank-biserial)", "=" * 88]
    for name, m, kw in tests:
        a, b = pairs(m, **kw)
        if not a:
            lines.append(f" {name:42s}  n=0  --")
            continue
        diffs = [x - y for x, y in zip(a, b)]
        med_impr = median(diffs)
        n, z, p, r_rb = wilcoxon(diffs)
        p_b = min(1.0, p * bonferroni) if p == p else float("nan")
        flag = "*" if p_b < 0.05 else " "
        lines.append(f" {name:42s} n={n:4d} med diff={100 * med_impr:+6.2f}pp"
                     f"  p={p:.4f} p_adj={p_b:.4f}{flag}  r={r_rb:+.2f}")
    out.extend(lines + [""])


def main():
    rows = load()
    for r in rows:
        rows_meta[r["ticker"]] = r["profile"]
    valid = [r for r in rows if int(r["year"]) in VALID_YEARS]
    test = [r for r in rows if int(r["year"]) == TEST_YEAR]
    out = []
    out.append("PROFILE VALIDATION -- TRACK A ANALYSIS SUMMARY")
    out.append(f"rows: {len(rows)} (validation {len(valid)}, test {len(test)});"
               " generated by analyze_battery.py; test year as-is per spec\n")

    table_median(valid, f"VALIDATION {VALID_YEARS} (method selection here)", out)
    table_median(test, f"TEST FY{TEST_YEAR} (touched once, reported as-is)", out)
    win_table(valid, "VALIDATION win counts per profile (#company-years where method is best)", out)
    win_table(test, f"TEST FY{TEST_YEAR} win counts per profile", out)
    wilcoxon_tests(valid, "VALIDATION inference", out)
    wilcoxon_tests(test, "TEST inference (confirmatory)", out)

    # validation-selected champion per fit class -> its test-year median
    out.extend(["=" * 88, " Protocol-exact readout: select on validation, read on test",
                "=" * 88])
    by_mf_v = defaultdict(list)
    for r in valid:
        by_mf_v[(r["fit"], r["method"])].append(float(r["smape"]))
    by_mf_t = defaultdict(list)
    for r in test:
        by_mf_t[(r["fit"], r["method"])].append(float(r["smape"]))
    for f in FITS:
        meds = {m: median(by_mf_v.get((f, m), [])) for m in METHODS
                if by_mf_v.get((f, m))}
        if not meds:
            continue
        best_v = min(meds, key=meds.get)
        t_med = median(by_mf_t.get((f, best_v), []))
        t_naive = median(by_mf_t.get((f, "Naive"), []))
        out.append(f" {f:8s} validation winner = {best_v:12s}"
                   f" ({100 * meds[best_v]:.1f}% med sMAPE)"
                   f" -> FY2025 test: {100 * t_med:.1f}% vs Naive {100 * t_naive:.1f}%")
    out.append("")

    text = "\n".join(out)
    path = os.path.join(DATA, "analysis_summary.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)
    print(f"-> {path}")


if __name__ == "__main__":
    main()
