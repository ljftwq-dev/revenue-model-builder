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


def main():
    model = build_luxun()
    print("Luxun Precision (002475) — real historical alignment 2023-2025")
    print("=" * 64)
    for seg in model.segments:
        print(f"\n[{seg.name}]")
        for d in seg.drivers():
            print(f"  {d.kind_label():12s}[{d.level}] {dict(d.values)}  — {d.source}")
        for yr in YEARS:
            print(f"  {yr}: {seg.revenue(yr)/100:.1f}亿", end="  ")
        print()
    print("\n" + "=" * 64 + "\nvalidate_all:")
    for r in model.validate_all():
        print(f"  {r.year}: Σ={r.segment_sum/100:.0f}亿  residual={r.residual_ratio:.1%}  ({len(r.warnings)} warning)")
    out = os.path.join(HERE, "立讯精密_收入模型.xlsx")
    build_excel(model, out, forecast_years=[2026, 2027, 2028])
    print(f"\nExcel -> {out}")


if __name__ == "__main__":
    main()
