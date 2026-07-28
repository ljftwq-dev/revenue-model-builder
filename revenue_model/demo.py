"""Fictional demo: NovaTech (车载 AI) revenue model.

All data is fabricated for illustration. No real company financials.
"""

from .driver import Driver, BASE, PENETRATION, SHARE, PRICE, LEVEL_A, LEVEL_B, LEVEL_C
from .segment import Segment
from .model import RevenueModel


def build_novatech() -> RevenueModel:
    domestic = Segment(
        name="舱内-国内",
        base=Driver("中国乘用车销量", BASE,
                    {2022: 22.0, 2023: 23.0, 2024: 24.0},
                    level=LEVEL_A, unit="百万辆", source="CAAM"),
        penetration=Driver("DMS 前装渗透率（国内）", PENETRATION,
                           {2022: 0.04, 2023: 0.06, 2024: 0.09},
                           level=LEVEL_B, unit="小数", source="高工产业研究院"),
        share=Driver("NovaTech 国内市占率", SHARE,
                     {2022: 0.10, 2023: 0.12, 2024: 0.14},
                     level=LEVEL_C, unit="小数", source="估算"),
        price=Driver("DMS 套件单价（国内）", PRICE,
                     {2022: 600, 2023: 620, 2024: 650},
                     level=LEVEL_C, unit="元", source="参考 Mobileye ASP 平滑"),
    )
    overseas = Segment(
        name="舱内-海外",
        base=Driver("欧洲乘用车销量", BASE,
                    {2022: 15.0, 2023: 15.5, 2024: 16.0},
                    level=LEVEL_A, unit="百万辆", source="ACEA"),
        penetration=Driver("DMS 前装渗透率（欧洲，EU GSR 强制）", PENETRATION,
                           {2022: 0.12, 2023: 0.18, 2024: 0.25},
                           level=LEVEL_B, unit="小数", source="Spherical"),
        share=Driver("NovaTech 海外市占率", SHARE,
                     {2022: 0.02, 2023: 0.03, 2024: 0.04},
                     level=LEVEL_C, unit="小数", source="估算"),
        price=Driver("DMS 套件单价（海外）", PRICE,
                     {2022: 700, 2023: 720, 2024: 750},
                     level=LEVEL_C, unit="元", source="海外溢价"),
    )
    return RevenueModel(
        company="NovaTech（虚构示例）",
        segments=[domestic, overseas],
        total_revenue={2022: 110.0, 2023: 215.0, 2024: 410.0},
    )


def main():
    model = build_novatech()
    print(f"=== {model.company} 收入模型 ===\n")
    for r in model.validate_all():
        print(f"--- {r.year} ---")
        for name, rev in r.segment_revenues.items():
            print(f"  {name:14s}: {rev:9.1f} 百万元")
        print(f"  {'Σ 分项':14s}: {r.segment_sum:9.1f}")
        print(f"  {'差额行':14s}: {r.residual:9.1f}  ({r.residual_ratio:5.1%})")
        print(f"  {'总收入':14s}: {r.total_revenue:9.1f}")
        if r.warnings:
            for w in r.warnings:
                print(f"  [!] {w}")
        else:
            print(f"  [ok] 对齐通过（Σ分项 + 差额 = 总收入）")
        print()


if __name__ == "__main__":
    main()
