"""Luxun Precision (立讯精密, 002475) — real A-share historical-alignment demo.

The first *real-company* demo for ``revenue-model-builder``: proves the engine
builds a driver-based revenue model from **public annual-report data** and
aligns it to reported historical totals — not just the fictional NovaTech.

Design (every driver carries an A/B/C credibility grade):
- ``base``     — B-grade industry data (IDC / EVTank / CAICT)
- ``penetration`` — B-grade (structural / proxy)
- ``share``    — C-grade estimate
- ``price``    — back-solved via ``implied_driver`` to tie to reported segment
                 revenue (C-grade). Per Principle 1, penetration is never
                 back-solved.

Historical alignment only — no forecast, no recommendation. See DISCLAIMER.md.
Run: ``python luxun_demo.py``  (needs ``pip install -e ".[excel]"``)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from revenue_model import (Driver, Segment, RevenueModel,
                           BASE, PENETRATION, SHARE, PRICE, implied_driver)
from revenue_model.excel_builder import build_excel

YEARS = [2023, 2024, 2025]
TOTAL = {2023: 231905, 2024: 268795, 2025: 332344}  # reported total, 百万元
TGT = {  # reported segment revenue, 百万元
    "ce":   {2023: 204670, 2024: 233096, 2025: 264266},  # consumer electronics (incl. PC from 2025)
    "auto": {2023:   9252, 2024:  13758, 2025:  39255},  # automotive electronics
    "comm": {2023:  14538, 2024:  18360, 2025:  24568},  # comms & datacenter
}


def build_luxun() -> RevenueModel:
    ce = Segment("消费电子(含电脑)",
        base=Driver("全球智能手机出货量", BASE, {2023:1160,2024:1220,2025:1260},
                    level="B", unit="百万部", source="IDC"),
        penetration=Driver("苹果全球手机份额", PENETRATION, {2023:0.189,2024:0.189,2025:0.189},
                    level="B", unit="fraction", source="proxy for main customer"),
        share=Driver("立讯苹果供应链份额", SHARE, {2023:0.30,2024:0.31,2025:0.33},
                    level="C", unit="fraction", source="rising; incl. PC (2025 caliber change)"),
        price=Driver("单台设备价值", PRICE, {}, level="C", unit="元", source="implied"))
    auto = Segment("汽车电子",
        base=Driver("全球新能源车销量", BASE, {2023:14.65,2024:18.24,2025:23.54},
                    level="B", unit="百万辆", source="EVTank"),
        penetration=Driver("新能源车电子配套", PENETRATION, {2023:1.0,2024:1.0,2025:1.0},
                    level="B", unit="fraction", source="structural"),
        share=Driver("立讯汽车份额", SHARE, {2023:0.045,2024:0.045,2025:0.12},
                    level="C", unit="fraction", source="2025 jump = Leoni acquisition"),
        price=Driver("单车价值", PRICE, {}, level="C", unit="元", source="implied"))
    comm = Segment("通讯及数据中心",
        base=Driver("全球AI服务器出货量", BASE, {2023:1.18,2024:1.72,2025:2.20},
                    level="B", unit="百万台", source="CAICT/TrendForce"),
        penetration=Driver("AI服务器高速互连", PENETRATION, {2023:1.0,2024:1.0,2025:1.0},
                    level="B", unit="fraction", source="structural"),
        share=Driver("立讯AI互连份额", SHARE, {2023:0.18,2024:0.18,2025:0.18},
                    level="C", unit="fraction", source="top supplier estimate"),
        price=Driver("单台互连价值", PRICE, {}, level="C", unit="元", source="implied"))

    # Back-solve price to tie each segment to its reported revenue (Principle 1).
    for seg, key in [(ce, "ce"), (auto, "auto"), (comm, "comm")]:
        for yr, tgt in TGT[key].items():
            seg.price.values[yr] = round(implied_driver(seg, yr, tgt, PRICE), 1)
    return RevenueModel("立讯精密", [ce, auto, comm], total_revenue=TOTAL)


FORECAST_YEARS = [2026, 2027, 2028]


def _trend_ext(driver, years):
    """Replace a driver with its OLS-trend extrapolation (C-grade, sourced)."""
    return driver.fit_trend(driver.years()).extrapolate(years)


def _hold(driver, years):
    """Hold the last historical value into forecast years — for structural
    drivers, or ones distorted by a one-off (e.g. an acquisition)."""
    last_yr = max(driver.values)
    last_val = driver.values[last_yr]
    new_vals = dict(driver.values)
    for y in years:
        new_vals[y] = last_val
    return Driver(driver.name, driver.kind, new_vals, level="C",
                  unit=driver.unit, source=f"held at {last_yr} value (no clean trend)")


def add_forecast(model):
    """Fill 2026-2028E drivers via Principle-3 extrapolation.

    - ``base`` (market size): OLS trend — the market follows its path.
    - ``penetration``: held (structural).
    - ``share``/``price``: trend where history is a clean trend; held where a
      one-off (Luxun's 2025 Leoni acquisition) distorts the series.
    """
    for seg in model.segments:
        seg.base = _trend_ext(seg.base, FORECAST_YEARS)
        seg.penetration = _hold(seg.penetration, FORECAST_YEARS)
    ce, auto, comm = model.segments
    # consumer: share & price both on a clean rising trend
    ce.share = _trend_ext(ce.share, FORECAST_YEARS)
    ce.price = _trend_ext(ce.price, FORECAST_YEARS)
    # automotive: Leoni acquisition (2025) is a one-off -> hold share & price
    auto.share = _hold(auto.share, FORECAST_YEARS)
    auto.price = _hold(auto.price, FORECAST_YEARS)
    # comms: share stable, price volatile (no clean trend) -> hold
    comm.share = _hold(comm.share, FORECAST_YEARS)
    comm.price = _hold(comm.price, FORECAST_YEARS)


def main():
    model = build_luxun()
    add_forecast(model)
    print("Luxun Precision (002445) — historical alignment + forecast")
    print("=" * 64)
    for seg in model.segments:
        print(f"\n[{seg.name}]")
        for d in seg.drivers():
            print(f"  {d.kind_label():12s}[{d.level}] {dict(d.values)}")
            print(f"               — {d.source}")
        print("  revenue:", end="")
        for yr in YEARS + FORECAST_YEARS:
            tag = "E" if yr in FORECAST_YEARS else ""
            print(f"  {yr}{tag}={seg.revenue(yr)/100:.0f}亿", end="")
        print()
    print("\n" + "=" * 64 + "\nvalidate_all (history only):")
    for r in model.validate_all():
        print(f"  {r.year}: Σ={r.segment_sum/100:.0f}亿  residual={r.residual_ratio:.1%}  ({len(r.warnings)} warning)")
    print("\nforecast revenue (driver-driven, no reported total to align):")
    for yr in FORECAST_YEARS:
        total = sum(seg.revenue(yr) for seg in model.segments)
        print(f"  {yr}E: Σ segments = {total/100:.0f}亿")
    out = os.path.join(HERE, "立讯精密_收入模型.xlsx")
    build_excel(model, out, forecast_years=FORECAST_YEARS)
    print(f"\nExcel -> {out}  (2026-2028E columns now filled)")


if __name__ == "__main__":
    main()
