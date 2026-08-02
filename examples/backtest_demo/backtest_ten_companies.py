"""Ten A-share companies backtest — cross-company method comparison.

Loads real annual revenue for ten names spanning distinct growth regimes
(high-growth / steady / mature / cyclical / financial / utility), runs the
same rolling backtest on each, and reports:

  * per-company sMAPE across all five methods,
  * the cross-company average sMAPE per method (headline ranking),
  * how often each method *won* (lowest sMAPE) on a single company.

Run:  python backtest_ten_companies.py
Needs: pip install -e ".[backtest]"  and  pip install akshare
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from revenue_model.backtest import (
    Naive, LinearTrend, LogLinearCAGR, HoltLinear, ARIMA,
    rolling_backtest, evaluate,
)
from revenue_model.backtest.data import load_annual_revenue

DATA_DIR = os.path.join(ROOT, "examples", "backtest_demo", "data")

# Ten names chosen to span growth regimes, so the comparison is not biased to
# one style of revenue path.
COMPANIES = [
    ("002475", "立讯精密"),   # high-growth, supply chain
    ("002594", "比亚迪"),     # high-growth, NEV
    ("300750", "宁德时代"),   # high-growth, battery
    ("600519", "贵州茅台"),   # steady premium growth
    ("000333", "美的集团"),   # mature steady
    ("600276", "恒瑞医药"),   # steady pharma
    ("002415", "海康威视"),   # mature tech
    ("000002", "万科A"),      # cyclical, declining
    ("601318", "中国平安"),   # financial, huge scale
    ("600900", "长江电力"),   # utility, ultra-stable
]

MIN_TRAIN = 8
HORIZON = 1


def main():
    methods = [Naive(), LinearTrend(), LogLinearCAGR(), HoltLinear(), ARIMA()]
    names = [m.name for m in methods]

    results = []
    print("加载真实数据 + 逐家滚动回测 (min_train=%d, horizon=%d)...\n" % (MIN_TRAIN, HORIZON))
    header = "  公司           区间(年数)     " + "  ".join(f"{n:>7}" for n in names)
    print(header)
    print("  " + "-" * (len(header) - 2))
    for sym, name in COMPANIES:
        try:
            yrs, vals, _ = load_annual_revenue(sym, name=name, cache_dir=DATA_DIR)
        except Exception as e:
            print(f"  [FAIL] {name}({sym}): {e}")
            continue
        steps = rolling_backtest(yrs, vals, methods,
                                 min_train=MIN_TRAIN, horizon=HORIZON)
        scores = {s.name: s for s in evaluate(steps)}
        results.append({"symbol": sym, "name": name,
                        "years": yrs, "scores": scores})
        row = "  ".join(f"{scores[n].smape * 100:6.1f}%" for n in names)
        span = f"{yrs[0]}-{yrs[-1]}({len(yrs)})"
        print(f"  {name:<12}{span:<16}{row}")

    import json
    _summary = {
        "methods": names,
        "min_train": MIN_TRAIN,
        "horizon": HORIZON,
        "companies": [
            {"symbol": r["symbol"], "name": r["name"],
             "span": [r["years"][0], r["years"][-1]],
             "n_years": len(r["years"]),
             "smape": {n: r["scores"][n].smape for n in names},
             "diracc": {n: r["scores"][n].directional_accuracy for n in names}}
            for r in results
        ],
    }
    _jp = os.path.join(DATA_DIR, "backtest_summary.json")
    with open(_jp, "w", encoding="utf-8") as fh:
        json.dump(_summary, fh, ensure_ascii=False, indent=2)

    if not results:
        print("\n没有公司成功，终止。")
        return

    # ---- cross-company aggregate ----
    print("\n" + "=" * 70)
    print(" 跨公司汇总 (共 %d 家)" % len(results))
    print("=" * 70)

    avg = {}
    for n in names:
        s = [r["scores"][n].smape for r in results]
        avg[n] = sum(s) / len(s)

    print("\n  ① 平均 sMAPE (越低越好) — 主排名:")
    for n in sorted(names, key=lambda x: avg[x]):
        bar = "#" * int(avg[n] * 50)
        print(f"     {n:<8}{avg[n] * 100:6.1f}%  {bar}")

    print("\n  ② 各方法'单家最优'次数 (该公司 sMAPE 最低):")
    wins = {n: 0 for n in names}
    for r in results:
        best = min(names, key=lambda x: r["scores"][x].smape)
        wins[best] += 1
    for n in sorted(names, key=lambda x: -wins[x]):
        print(f"     {n:<8}{wins[n]:>2} / {len(results)} 家")

    print("\n  ③ 各方法方向命中率 (跨公司平均, DirAcc):")
    for n in names:
        d = [r["scores"][n].directional_accuracy for r in results]
        ad = sum(d) / len(d)
        print(f"     {n:<8}{ad * 100:6.1f}%")

    print("\n  解读要点:")
    print("  - 看①平均sMAPE: 哪个方法在'多增长模式'下最稳.")
    print("  - 看②赢的次数: 是否存在'一家独大'还是各有所长(因公司而异).")
    print("  - 万科(周期下滑)/长江电力(超稳)是趋势法的'难样本', 看谁扛得住.")


if __name__ == "__main__":
    main()
