"""Fictional demo: NovaTech (车载 AI) revenue model.

All data is fabricated for illustration. No real company financials.
"""

from .driver import Driver, BASE, PENETRATION, SHARE, PRICE, LEVEL_A, LEVEL_B, LEVEL_C
from .segment import Segment
from .model import RevenueModel
from .monte_carlo import simulate_model, tornado, scenarios


def build_novatech() -> RevenueModel:
    domestic = Segment(
        name="舱内-国内",
        base=Driver("中国乘用车销量", BASE,
                    {2022: 22.0, 2023: 23.0, 2024: 24.0},
                    level=LEVEL_A, unit="百万辆", source="CAAM",
                    source_url="http://www.caam.org.cn"),
        penetration=Driver("DMS 前装渗透率（国内）", PENETRATION,
                           {2022: 0.04, 2023: 0.06, 2024: 0.09},
                           level=LEVEL_B, unit="小数", source="高工产业研究院",
                           source_url="http://www.gg-ii.com"),
        share=Driver("NovaTech 国内市占率", SHARE,
                     {2022: 0.10, 2023: 0.12, 2024: 0.14},
                     level=LEVEL_C, unit="小数", source="估算"),
        price=Driver("DMS 套件单价（国内）", PRICE,
                     {2022: 600, 2023: 620, 2024: 650},
                     level=LEVEL_C, unit="元", source="参考 Mobileye ASP 平滑",
                     source_url="https://www.mobileye.com"),
    )
    overseas = Segment(
        name="舱内-海外",
        base=Driver("欧洲乘用车销量", BASE,
                    {2022: 15.0, 2023: 15.5, 2024: 16.0},
                    level=LEVEL_A, unit="百万辆", source="ACEA",
                    source_url="https://www.acea.auto"),
        penetration=Driver("DMS 前装渗透率（欧洲，EU GSR 强制）", PENETRATION,
                           {2022: 0.12, 2023: 0.18, 2024: 0.25},
                           level=LEVEL_B, unit="小数", source="Spherical",
                           source_url="https://www.sphericalinsights.com"),
        share=Driver("NovaTech 海外市占率", SHARE,
                     {2022: 0.02, 2023: 0.03, 2024: 0.04},
                     level=LEVEL_C, unit="小数", source="估算"),
        price=Driver("DMS 套件单价（海外）", PRICE,
                     {2022: 700, 2023: 720, 2024: 750},
                     level=LEVEL_C, unit="元", source="海外溢价",
                     source_url="https://www.mobileye.com"),
    )
    return RevenueModel(
        company="NovaTech（虚构示例）",
        segments=[domestic, overseas],
        total_revenue={2022: 110.0, 2023: 215.0, 2024: 410.0},
    )


def print_validation(model: RevenueModel) -> None:
    """对齐校验：Σ(分项) + 差额行 = 总收入，逐年打印告警。"""
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


def print_simulation(model: RevenueModel) -> None:
    """蒙特卡洛收入分布 + Bear/Base/Bull 情景 + tornado 敏感度（基于 NovaTech demo 参数）。"""
    print("=" * 52)
    print("蒙特卡洛：2024 建模收入分布（市占率 ±不确定）")
    print("=" * 52)
    ranges = {
        "NovaTech 国内市占率": (0.10, 0.18),
        "NovaTech 海外市占率": (0.02, 0.06),
    }
    mc = simulate_model(model, 2024, ranges, n=20000, seed=0)
    p = mc.percentiles
    print(f"  均值 {mc.mean:8.1f}   中位 {mc.median:8.1f}   σ {mc.stdev:7.1f}（百万元）")
    print(f"  P5 {p['p5']:8.1f} | P25 {p['p25']:7.1f} | P75 {p['p75']:7.1f} | P95 {p['p95']:7.1f}")
    print(f"  90% 置信区间宽度: {p['p95'] - p['p5']:7.1f}")

    print()
    print("情景（Bear/Base/Bull = 蒙特卡洛分布的 P10/中位/P90）")
    print("-" * 52)
    for sc in scenarios(mc):
        print(f"  {sc.name:5s}: {sc.revenue:8.1f} 百万元  (P{sc.percentile * 100:.0f})")

    print()
    print("敏感度（tornado）：舱内-国内 2024，各 driver 按自身不确定性区间摆动")
    print("-" * 52)
    sens_ranges = {
        "中国乘用车销量": (23.5, 24.5),
        "DMS 前装渗透率（国内）": (0.07, 0.12),
        "NovaTech 国内市占率": (0.10, 0.18),
        "DMS 套件单价（国内）": (620, 680),
    }
    for it in tornado(model.segments[0], 2024, sens_ranges):
        print(f"  {it.driver:30s} swing {it.swing:7.1f}  "
              f"(low {it.low_revenue:7.1f} / high {it.high_revenue:7.1f})")


def main():
    model = build_novatech()
    print_validation(model)
    print_simulation(model)


if __name__ == "__main__":
    main()
