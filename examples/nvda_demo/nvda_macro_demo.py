"""NVDA data-center — macro *demand*-channel revision demo (illustrative).

Companion to ``luxun_macro_demo.py`` (which demonstrates cost + fx channels).
This one demonstrates the **demand channel** of the event -> driver revision
-> re-run loop for a data-center business:

- Upstream: durable-goods orders (DGORDER) — the demand indicator whose
  sector-level leading relationship survived the QESA FDR screen
  (AMD × DGORDER beta = +4.98 @1q, q = 0.032, prior-consistent).
- The elasticity is **borrowed from a sector peer** and the demo says so:
  single-firm regressions are noisy; treat as C-grade until validated.
- Segment financials here are ILLUSTRATIVE (rounded, calendar-mapped) — this
  demo shows the *mechanics of the loop*, not a forecast of NVIDIA.
  See DISCLAIMER.md.

Run: ``python nvda_macro_demo.py`` (bundled ../luxun-real-demo/sample_qesa.db
works; set QESA_DB for a live QESA store).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from revenue_model import (Driver, Segment, BASE, PENETRATION, SHARE, PRICE,
                           MacroBinding, RevisionSuggestion, QesaStore,
                           suggest_revisions, apply_revision)

FORECAST_YEARS = [2026, 2027, 2028]

# illustrative, rounded, calendar-mapped — NOT a forecast of NVIDIA
DC_REV = {2023: 47.0, 2024: 115.0, 2025: 175.0}   # $B, company filings rounded
DC = Segment("数据中心(illustrative)",
    Driver("全球AI服务器出货量", BASE, {2023: 1.18, 2024: 1.72, 2025: 2.20},
           level="B", unit="百万台", source="CAICT/TrendForce (rounded)"),
    Driver("NVDA平台搭载率", PENETRATION, {2023: 1.0, 2024: 1.0, 2025: 1.0},
           level="B", unit="fraction", source="structural 1.0"),
    Driver("NVDA DC份额", SHARE, {2023: 0.85, 2024: 0.88, 2025: 0.88},
           level="C", unit="fraction", source="est, illustrative"),
    Driver("单台价值", PRICE, {}, level="C", unit="千美元", source="implied"))

BINDINGS = [
    MacroBinding(
        series_id="DGORDER", label="耐用品订单", channel="demand",
        target="全球AI服务器出货量", elasticity=4.98, lag_quarters=1,
        window_years=2,
        note="QESA公司层FDR存活: AMD×DGORDER β=+4.98@1q (q=0.032); "
             "同板块借用, 单公司回归噪声大 → C级"),
]


def hold_forward(seg: Segment) -> Segment:
    def hold(d: Driver) -> Driver:
        last = d.values[max(d.values)]
        return Driver(d.name, d.kind, {**d.values, **{y: last for y in FORECAST_YEARS}},
                      level=d.level, unit=d.unit, source=d.source)
    return Segment(seg.name, hold(seg.base), hold(seg.penetration),
                   hold(seg.share), hold(seg.price))


def main():
    db = (os.environ.get("QESA_DB")
          or os.path.join(HERE, "..", "luxun-real-demo", "sample_qesa.db"))
    db = os.path.abspath(db)
    if not os.path.exists(db):
        sys.exit(f"QESA db not found: {db}\n(set QESA_DB, or build the sample "
                 "via examples/luxun-real-demo/make_sample_qesa.py)")
    banner = "" if os.environ.get("QESA_DB") else "  [sample data]"
    print(f"=== NVDA DC 宏观需求修正 demo{banner} ===\n")

    # implied 2025 unit price from illustrative revenue
    b = DC.base.get(2025) * DC.penetration.get(2025) * DC.share.get(2025)
    DC.price.values[2025] = DC_REV[2025] / b   # $B / M units = $K/unit

    store = QesaStore(path=db)
    print("--- 上游需求信号扫描 (YoY 增速跳变 >= 1pp) ---")
    suggestions = []
    for sug in suggest_revisions(BINDINGS, store, min_shock_pp=1.0):
        suggestions.append(sug)
    if not suggestions:
        print("  (无触发 — 耐用品订单 YoY 近期无 >=1pp 跳变, 基线不变)")
    for s in suggestions:
        print(" ", s.summary())
    store.close()
    print()

    base_seg = hold_forward(DC)
    rev_seg = hold_forward(DC)
    for s in suggestions:
        d = rev_seg.base
        setattr(rev_seg, d.kind, apply_revision(d, s, FORECAST_YEARS))
        print(f"  applied -> {rev_seg.name}.{s.binding.target}: "
              f"{s.implied_pp:+.2f}pp/yr (lands {s.lands_quarter})")

    print("\n--- DC 收入: 基线 vs 需求修正 ($B, illustrative) ---")
    print(f"{'':<24}" + "".join(f"{y:>12}" for y in FORECAST_YEARS))
    rb = [base_seg.revenue(y) for y in FORECAST_YEARS]
    rr = [rev_seg.revenue(y) for y in FORECAST_YEARS]
    print(f"{'基线(hold-forward)':<24}" + "".join(f"{v:>12.1f}" for v in rb))
    print(f"{'宏观修正':<24}" + "".join(f"{v:>12.1f}" for v in rr))
    print(f"{'Δ':<24}" + "".join(
        f"{100 * (a - c) / c:>+11.2f}%" for a, c in zip(rr, rb)))
    print("\n(需求渠道系数为同板块借用、C级建议; 落地前需人工复核; 见 DISCLAIMER)")
    print("量级检验: 修正pp应对照分部历史增速 — 本illustrative段2024年实际+145%,")
    print("          +52pp/yr在其量级内; 若同一系数落到成熟低增速分部则应拒绝或打折。")


if __name__ == "__main__":
    main()
