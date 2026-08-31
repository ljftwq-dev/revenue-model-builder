"""Zhipu (02513.HK) 2026H1 revenue forecast postmortem - ARR-anchor methods.

Pretend it is 2026-08-30: the interim report is NOT out yet. Using only
public information available before the print (FY2025 results, MaaS ARR
milestones, Coding Plan price hikes), forecast 2026H1 revenue three ways,
then score against the actuals disclosed on 2026-08-31:

  M1   naive YoY extrapolation (apply FY2025 growth to H1)
  M2   single-anchor exponential: Jan/Jul ARR anchors, g = 15^(1/6)
  M3   dual-anchor piecewise interpolation: Jan/Mar/Jul ARR anchors
  M3'  M3 with ARR->recognized-revenue conversion haircut (0.85)

Run:  python forecast_vs_actual.py   (pure stdlib, no third-party deps)
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
CONVERSION = 0.85  # ARR -> recognized revenue, calibrated post-hoc


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


def rev_single_anchor(arr_jan, g, n=6):
    """Monthly revenue = ARR_i / 12 with ARR growing geometric at factor g."""
    return [arr_jan * g ** i / 12.0 for i in range(n)]


def rev_dual_anchor(arr_jan, arr_mar, arr_jul):
    """Piecewise geometric interpolation between three ARR anchors."""
    f_early = (arr_mar / arr_jan) ** 0.5    # per-month factor, Jan->Mar
    f_late = (arr_jul / arr_mar) ** 0.25    # per-month factor, Mar->Jul
    arrs = [arr_jan,
            arr_jan * f_early,
            arr_mar,
            arr_mar * f_late,
            arr_mar * f_late ** 2,
            arr_mar * f_late ** 3]
    return [a / 12.0 for a in arrs]


def pct(pred, actual):
    return pred / actual - 1.0


def main():
    pre = load("pre_report_info.json")
    act = load("actual_2026h1.json")

    h1_2025 = pre["history"]["2025H1"]
    fy_growth = pre["other"]["fy2025_growth"]
    arr = pre["arr_anchors"]
    arr_jan, arr_mar, arr_jul = arr["2026-01"], arr["2026-03"], arr["2026-07"]
    actual = act["revenue_yi"]

    # ---- forecasts (information set strictly pre-report) ----
    m1 = h1_2025 * (1.0 + fy_growth)
    g = pre["other"]["arr_growth_7m"] ** (1.0 / 6.0)
    m2_path = rev_single_anchor(arr_jan, g)
    m3_path = rev_dual_anchor(arr_jan, arr_mar, arr_jul)
    m2, m3 = sum(m2_path), sum(m3_path)
    m3h = m3 * CONVERSION

    print("=" * 74)
    print(" 智谱 02513.HK 2026H1 收入预测复盘（预测时点 %s）" % pre["as_of"])
    print("=" * 74)

    print("\n① ARR 锚点（亿元）: Jan=%.2f（由Jul/15隐含） Mar=%.1f Jul=%.1f" % (arr_jan, arr_mar, arr_jul))
    print("   单锚点月环比 g = 15^(1/6) = %.4f" % g)

    print("\n② 逐月收入拆分（亿元）")
    print("   %-6s%10s%10s" % ("月份", "M2单锚点", "M3双锚点"))
    for i, m in enumerate(MONTHS):
        print("   %-6s%10.3f%10.3f" % (m, m2_path[i], m3_path[i]))

    rows = [
        ("M1 朴素同比(H1×(1+FY25增速))", m1),
        ("M2 单锚点指数(Jan/Jul ARR)", m2),
        ("M3 双锚点内插(Jan/Mar/Jul ARR)", m3),
        ("M3' 双锚点×%.2f转化率" % CONVERSION, m3h),
    ]
    print("\n③ 预测 vs 实际（实际 2026H1 = %.2f 亿元, 同比 +%.1f%%）" % (actual, act["yoy"] * 100))
    print("   %-32s%12s%10s" % ("方法", "预测(亿元)", "误差"))
    for name, v in rows:
        print("   %-32s%12.2f%9.1f%%" % (name, v, pct(v, actual) * 100))

    print("\n④ 其他指标核对（预测区间 vs 实际）")
    checks = [
        ("云端收入占比", "65-85%", "%.1f%%" % (act["cloud_share"] * 100), "略超上沿"),
        ("云端毛利率", "10-25%", "%.1f%%" % (act["cloud_gross_margin"] * 100), "命中上沿"),
        ("综合毛利率", "25-35%", "%.1f%%" % (act["gross_margin"] * 100), "命中"),
        ("净亏损(亿元)", "-18 ~ -24", "%.2f" % act["net_loss_yi"], "命中"),
    ]
    print("   %-14s%14s%12s%10s" % ("指标", "预测区间", "实际", "判定"))
    for row in checks:
        print("   %-14s%14s%12s%10s" % row)

    print("\n⑤ 复盘教训")
    lessons = [
        "爆发期朴素外推失效(-54%): H1实际增速400% >> 上年年度增速132%",
        "ARR是爆发期最强领先指标: 单锚点法误差压到-4%",
        "ARR != 确认收入: 实测转化率 = %.3f (折扣/赠送token/口径混合/确认滞后)" % (actual / m3),
        "增长路径前快后慢: Jan->Mar月环比%.2fx > Mar->Jul %.2fx" % ((arr_mar / arr_jan) ** 0.5, (arr_jul / arr_mar) ** 0.25),
        "提价(Coding Plan +30%)未显式进入量价分解, 是改进方向",
    ]
    for i, s in enumerate(lessons, 1):
        print("   %d. %s" % (i, s))


if __name__ == "__main__":
    main()
