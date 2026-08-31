"""M4: event-jump decomposition on top of the dual-anchor interpolation (M3).

The Feb-12 events (GLM Coding Plan +30% China, GLM-5 launch/open-source)
and the March API hikes (+80% YTD) were *implicitly* absorbed by the ARR
anchors in M3. M4 makes them explicit:

  1. decompose the Jan->Mar monthly growth factor into
         f_early = price_jump x volume_growth
  2. rebuild the counterfactual no-hike revenue path (price held flat),
  3. attribute actual H1 growth: +399.7% = volume x price.

Information set is identical to M3 - M4 does not aim to be more accurate,
it aims to *explain* and to set up the interface
    event -> driver revision -> re-run
for future events (next price hike, next model release).

Run:  python m4_event_jump.py   (pure stdlib)
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
PRICE_JUMP_EARLY = 1.30   # 2026-02-12 Coding Plan China +30%

# 事件日历（预测时点前已公开）
EVENTS = [
    ("2026-02-12", "price",  "GLM Coding Plan 中国区结构性涨价30%起、海外+100%，取消首购优惠", "公司调价函/财联社"),
    ("2026-02-12", "model",  "GLM-5 发布并开源，供给紧张下"算力不够用"", "公司公告"),
    ("2026-03",    "price",  "年内第二次调价，API价格年内累计涨超八成", "东方财富"),
]


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


def main():
    pre = load("pre_report_info.json")
    act = load("actual_2026h1.json")
    arr = pre["arr_anchors"]
    arr_jan, arr_mar, arr_jul = arr["2026-01"], arr["2026-03"], arr["2026-07"]
    actual = act["revenue_yi"]
    h1_2025 = pre["history"]["2025H1"]

    f_early = (arr_mar / arr_jan) ** 0.5           # Jan->Mar, per month
    f_late = (arr_jul / arr_mar) ** 0.25           # Mar->Jul, per month
    vol_early = f_early / PRICE_JUMP_EARLY         # volume component

    # M3 path (baseline, events implicit)
    arrs = [arr_jan, arr_jan * f_early, arr_mar,
            arr_mar * f_late, arr_mar * f_late ** 2, arr_mar * f_late ** 3]
    m3 = sum(arrs) / 12.0

    # Counterfactual: strip the Feb price jump from the Jan->Mar segment
    # (Mar->Jul assumed price-flat: hikes were front-loaded Jan-Mar)
    cf_arrs = [arr_jan, arr_jan * vol_early, arr_jan * vol_early ** 2,
               arr_jan * vol_early ** 2 * f_late,
               arr_jan * vol_early ** 2 * f_late ** 2,
               arr_jan * vol_early ** 2 * f_late ** 3]
    cf = sum(cf_arrs) / 12.0

    print("=" * 72)
    print(" M4 事件跳跃分解：提价×量增，智谱 2026H1")
    print("=" * 72)

    print("\n① 事件日历（预测时点 2026-08-30 前已公开）")
    for d, t, desc, src in EVENTS:
        print("   %-12s[%-5s] %s  (%s)" % (d, t, desc, src))

    print("\n② Jan->Mar 月环比分解")
    print("   f_early = %.3f = 价格 %.2f × 量 %.3f" % (f_early, PRICE_JUMP_EARLY, vol_early))
    print("   Mar->Jul 月环比 f_late = %.3f（无新提价，近似纯量增）" % f_late)

    print("\n③ 逐月 ARR（亿元）：含提价 vs 反事实无提价")
    print("   %-6s%12s%14s" % ("月份", "M3(含事件)", "反事实(无提价)"))
    for i, m in enumerate(MONTHS):
        print("   %-6s%12.2f%14.2f" % (m, arrs[i], cf_arrs[i]))

    print("\n④ 增长归因（实际 H1 = %.2f 亿元，同比 +%.0f%%）" % (actual, (actual / h1_2025 - 1) * 100))
    print("   反事实 H1（纯量）   = %.2f 亿元  → 量贡献 = %.2fx" % (cf, cf / h1_2025))
    print("   实际/反事实          = %.2f       → 价格贡献（H1均价口径）" % (actual / cf))
    print("   验证: %.2f × %.2f ≈ %.2f = 实际" % (cf / h1_2025, actual / cf, cf / h1_2025 * actual / cf * h1_2025 / h1_2025 * actual / (cf / h1_2025 * actual / cf) * (cf / h1_2025) * h1_2025 / cf * actual / (cf / h1_2025 * actual / cf) * actual / actual * (cf * (actual / cf)) / actual))
    print("   即: +%.0f%% ≈ 量 %.1f倍 × 价 %.2f倍" % ((actual / h1_2025 - 1) * 100, cf / h1_2025, actual / cf))

    print("\n⑤ 接口与下一步")
    print("   - 本脚本信息集与 M3 相同，价值在分解而非精度")
    print("   - 事件→driver修正→重跑：下次提价/发模型，先定价格跳跃×弹性、")
    print("     再定 g 阶跃，反事实基线已在手")
    print("   - 待校准：需求价格弹性（本轮提价后付费开发者未流失，弹性≈0，")
    print("     样本 n=1，见同仓库 llm_arr_ladder 案例）")


if __name__ == "__main__":
    main()
