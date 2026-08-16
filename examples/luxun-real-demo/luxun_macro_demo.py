"""Luxun Precision (立讯精密, 002475) — macro-driver revision demo.

Extends the historical-alignment demo (``luxun_demo.py``) with the
**event -> driver revision -> re-run loop**:

1. Upstream QESA series (LME copper/aluminum costs, CNY/USD fx) are scanned
   for shocks — *jumps in YoY growth*, not high levels.
2. Each triggered ``MacroBinding`` proposes a revision to a forecast driver,
   carrying the elasticity and transmission lag from the QESA transmission
   study (elasticities are C-grade estimates and say so in the memo).
3. Baseline (hold-forward) vs revised forecast print side by side — every
   revision is a *suggestion with evidence*, not an automatic overwrite.

Data: set ``QESA_DB`` to a live QESA database, or run with the bundled
``sample_qesa.db`` (real FRED data, trimmed) — see ``make_sample_qesa.py``.
Historical-alignment only for 2023-25; 2026-28 forecast is illustrative.
See DISCLAIMER.md.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from revenue_model import (Driver, Segment, BASE, PENETRATION, SHARE, PRICE,
                           LEVEL_C, MacroBinding, RevisionSuggestion,
                           QesaStore, suggest_revisions, apply_revision)

FORECAST_YEARS = [2026, 2027, 2028]

# ---- historical model (same as luxun_demo.py) -----------------------------
YEARS = [2023, 2024, 2025]
TGT = {  # reported segment revenue, 百万元
    "ce":   {2023: 204670, 2024: 233096, 2025: 264266},
    "auto": {2023: 9252, 2024: 13758, 2025: 39255},
    "ai":   {2023: 2780, 2024: 6018, 2025: 10064},
}

CE = Segment("消费电子(含PC)",
    Driver("全球智能手机出货量", BASE, {2023: 1160, 2024: 1220, 2025: 1260},
           level="B", unit="百万部", source="IDC"),
    Driver("苹果全球手机份额", PENETRATION, {2023: 0.189, 2024: 0.189, 2025: 0.189},
           level="B", unit="fraction", source="proxy: iPhone/industry"),
    Driver("立讯苹果供应链份额", SHARE, {2023: 0.30, 2024: 0.31, 2025: 0.33},
           level="C", unit="fraction", source="rising; incl. PC assembly"),
    Driver("单台设备价值", PRICE, {}, level="C", unit="元", source="implied"))

AUTO = Segment("汽车电子",
    Driver("全球新能源车销量", BASE, {2023: 14.65, 2024: 18.24, 2025: 23.54},
           level="B", unit="百万辆", source="EVTank"),
    Driver("新能源车电子配套", PENETRATION, {2023: 1.0, 2024: 1.0, 2025: 1.0},
           level="B", unit="fraction", source="structural 1.0"),
    Driver("立讯汽车份额", SHARE, {2023: 0.045, 2024: 0.045, 2025: 0.12},
           level="C", unit="fraction", source="2025 jump = new platform win"),
    Driver("单车价值", PRICE, {}, level="C", unit="元", source="implied"))

AI = Segment("AI互连(通讯/数据中心)",
    Driver("全球AI服务器出货量", BASE, {2023: 1.18, 2024: 1.72, 2025: 2.20},
           level="B", unit="百万台", source="CAICT/TrendForce"),
    Driver("AI服务器高速互连", PENETRATION, {2023: 1.0, 2024: 1.0, 2025: 1.0},
           level="B", unit="fraction", source="structural 1.0"),
    Driver("立讯AI互连份额", SHARE, {2023: 0.18, 2024: 0.18, 2025: 0.18},
           level="C", unit="fraction", source="top supplier"),
    Driver("单台互连价值", PRICE, {}, level="C", unit="元", source="implied"))

SEGMENTS = [("ce", CE), ("auto", AUTO), ("ai", AI)]

# ---- macro bindings: QESA transmission study elasticities (C-grade) -------
BINDINGS = [
    MacroBinding(
        series_id="PCOPPUSDM", label="LME铜", channel="cost",
        target="单台设备价值", elasticity=0.08, lag_quarters=4,
        window_years=2,
        note="QESA LP: 铜价→PPI成品 β≈0.08 (成本传导至出厂单价, 滞后4季)"),
    MacroBinding(
        series_id="PALUMUSDM", label="LME铝", channel="cost",
        target="单台设备价值", elasticity=0.08, lag_quarters=4,
        window_years=2,
        note="QESA LP: 铝价→PPI成品 β≈0.08 (同上, 结构性金属件成本)"),
    MacroBinding(
        series_id="DEXCHUS", label="人民币汇率", channel="fx",
        target="单台设备价值", elasticity=0.50, lag_quarters=1,
        window_years=2,
        note="CNY贬值→出口美元收入折CNY增加; 弹性=出口占比×敏感度假设(C级)"),
]


def hold_forward(seg: Segment) -> Segment:
    """Baseline: every driver held at its 2025 value through 2028."""
    def hold(d: Driver) -> Driver:
        last = d.values[max(d.values)]
        return Driver(d.name, d.kind, {**d.values, **{y: last for y in FORECAST_YEARS}},
                      level=d.level, unit=d.unit, source=d.source)
    return Segment(seg.name, hold(seg.base), hold(seg.penetration),
                   hold(seg.share), hold(seg.price))


def implied_prices():
    """Back-solve 2025 unit-price drivers from reported revenue (Principle 5)."""
    for key, seg in SEGMENTS:
        rep = TGT[key]
        b = seg.base.get(2025) * seg.penetration.get(2025) * seg.share.get(2025)
        seg.price.values[2025] = rep[2025] / b


def main():
    db = os.environ.get("QESA_DB") or os.path.join(HERE, "sample_qesa.db")
    if not os.path.exists(db):
        sys.exit(f"QESA db not found: {db}\n(run make_sample_qesa.py or set QESA_DB)")
    banner = "" if os.environ.get("QESA_DB") else "  [sample data — set QESA_DB for live]"
    print(f"=== 立讯宏观driver修正 demo{banner} ===\n")

    store = QesaStore(path=db)
    implied_prices()

    print("--- 上游冲击扫描 (YoY 增速跳变 >= 1pp) ---")
    suggestions = suggest_revisions(BINDINGS, store, min_shock_pp=1.0)
    if not suggestions:
        print("  (无触发 — 各上游序列近期 YoY 无 >=1pp 跳变)")
    for s in suggestions:
        print(" ", s.summary())
    store.close()
    print()

    # baseline: hold-forward; revised: apply aggregated suggestions by target
    base_segs = {key: hold_forward(seg) for key, seg in SEGMENTS}
    rev_segs = {key: hold_forward(seg) for key, seg in SEGMENTS}
    by_target = {}
    for s in suggestions:
        by_target.setdefault(s.binding.target, []).append(s)
    for target, sugs in by_target.items():
        agg_pp = sum(s.implied_pp for s in sugs)
        s0 = max(sugs, key=lambda s: abs(s.shock_delta_pp))
        combined = RevisionSuggestion(
            binding=MacroBinding(
                series_id=s0.binding.series_id,
                label=" + ".join(s.binding.label for s in sugs),
                channel=s0.binding.channel, target=target,
                elasticity=(agg_pp / s0.shock_delta_pp
                            if s0.shock_delta_pp else 0.0),
                lag_quarters=s0.binding.lag_quarters,
                window_years=s0.binding.window_years),
            shock_date=s0.shock_date, shock_yoy=s0.shock_yoy,
            shock_delta_pp=s0.shock_delta_pp, implied_pp=agg_pp)
        for key, seg in rev_segs.items():
            for d in seg.drivers():
                if d.name == target:
                    d2 = apply_revision(d, combined, FORECAST_YEARS)
                    setattr(seg, d.kind, d2)   # base/penetration/share/price field
                    print(f"  applied -> {seg.name}.{target}: "
                          f"{agg_pp:+.2f}pp 累计修正 (lands {combined.lands_quarter})")

    print("\n--- 分部收入: 基线(hold-forward) vs 宏观修正 (百万元) ---")
    hdr = f"{'分部':<16}" + "".join(f"{y:>16}" for y in FORECAST_YEARS)
    print(hdr)
    grand_b = {y: 0.0 for y in FORECAST_YEARS}
    grand_r = {y: 0.0 for y in FORECAST_YEARS}
    for key, seg in SEGMENTS:
        row_b = f"{seg.name:<16}"
        row_d = f"{'':<16}"
        for y in FORECAST_YEARS:
            rb = base_segs[key].revenue(y)
            rr = rev_segs[key].revenue(y)
            delta = 100 * (rr - rb) / rb
            row_b += f"{rb:>10,.0f}      "
            row_d += f"{'':>10}  {delta:+5.2f}% "
            grand_b[y] += rb
            grand_r[y] += rr
        print(row_b)
        print(row_d)
    row = f"{'合计':<16}"
    rowd = f"{'':<16}"
    for y in FORECAST_YEARS:
        row += f"{grand_b[y]:>10,.0f}      "
        rowd += f"{'':>10}  {100 * (grand_r[y] - grand_b[y]) / grand_b[y]:+5.2f}% "
    print(row)
    print(rowd)
    print("\n(修正均为 C 级建议: 弹性来自 QESA 传导研究, 落地前需人工复核; 见 DISCLAIMER)")


if __name__ == "__main__":
    main()
