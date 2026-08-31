"""LLM industry panel #1: five companies, one forecast recipe, five scorecards.

Loads run-rate/ARR anchors for Anthropic / OpenAI / Google Cloud / Zhipu /
DeepSeek, prints the mid-2026 revenue ladder, then repeats the same
pre-event forecast -> actual check for every company where an actual exists:

  Zhipu     2026H1 revenue    ARR single-anchor exponential   (see zhipu_arr_forecast)
  OpenAI    2026Q2 GAAP       2025-12 + 2026-03 anchors extrapolation
  Anthropic 2026-07 run-rate  2026-02 + 2026-04 anchors extrapolation (fails: deceleration)
  Google    Q1/Q2 Cloud       sell-side consensus vs GAAP actual (systematic lowball)
  DeepSeek  annualized        no actuals - control group (open-source low-price path)

Run:  python llm_ladder.py   (pure stdlib)
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def load():
    with open(os.path.join(DATA, "llm_runrates.json"), encoding="utf-8") as fh:
        return json.load(fh)


def geo_path(anchor_a, anchor_b, months, n_forecast):
    """Geometric path from anchor_a to anchor_b over `months`, extrapolated
    n_forecast further months. Returns list of monthly run-rates."""
    g = (anchor_b / anchor_a) ** (1.0 / months)
    return [anchor_b * g ** i for i in range(1, n_forecast + 1)]


def main():
    d = load()["companies"]

    print("=" * 74)
    print(" 大模型行业板块①：五家公司 ARR 阶梯（2026 年中）")
    print("=" * 74)

    print("\n① 收入阶梯（年化口径，亿美元）")
    zhipu_arr_usd = d["zhipu"]["arr_jul_usd_b"]
    rows = [
        ("Anthropic", d["anthropic"]["runrate"]["2026-07"], "闭源高价", "媒体报道"),
        ("OpenAI", d["openai"]["runrate"]["2026-08"], "闭源平价规模", "Bloomberg"),
        ("Google Cloud", d["google_cloud"]["gaap_q2_2026"] * 4, "闭源+云捆绑(GAAP×4)", "季报年化"),
        ("智谱", zhipu_arr_usd, "闭源平价(中国)", "官方ARR"),
        ("DeepSeek", d["deepseek"]["annualized_2026_usd_b"], "开源极低价", "媒体估算"),
    ]
    print("   %-14s%14s%18s%12s" % ("公司", "年化($B)", "模式", "口径"))
    for r in rows:
        print("   %-14s%14.1f%18s%12s" % r)

    print("\n② 预测检验：同一流程重复五次")

    # --- Zhipu: M2 single-anchor (compressed from zhipu_arr_forecast) ---
    z = d["zhipu"]
    g_z = z["arr_growth_7m"] ** (1.0 / 6.0)
    path = [z["arr_anchors_cny_yi"]["2026-01"] * g_z ** i / 12.0 for i in range(6)]
    pred_zhipu = sum(path)
    print("\n   [智谱] ARR单锚点指数 → 2026H1")
    print("      预测 %.2f 亿元 vs 实际 %.2f 亿元 → 误差 %+.1f%%"
          % (pred_zhipu, z["actual_h1_2026_yi"], (pred_zhipu / z["actual_h1_2026_yi"] - 1) * 100))

    # --- OpenAI: extrapolate Q2 GAAP from Dec-25 + Mar-26 anchors ---
    o = d["openai"]["runrate"]
    g_o = (o["2026-03"] / o["2025-12"]) ** (1.0 / 2.5)   # per month
    apr, may, jun = [o["2026-03"] * g_o ** (i + 0.5) for i in (1, 2, 3)]
    pred_oa = (apr + may + jun) / 12.0                     # GAAP Q2 = sum of monthly
    act_oa = d["openai"]["gaap_q2_2026"]
    print("\n   [OpenAI] 2025末+3月锚点外推 → 2026Q2 GAAP")
    print("      预测 $%.1fB vs 实际 $%.1fB → 误差 %+.1f%%"
          % (pred_oa, act_oa, (pred_oa / act_oa - 1) * 100))

    # --- Anthropic: extrapolate Jul from Feb + Apr anchors (deceleration test) ---
    a = d["anthropic"]["runrate"]
    pred_a = geo_path(a["2026-02"], a["2026-04"], 2, 3)[-1]
    act_a = a["2026-07"]
    g_real = (a["2026-07"] / a["2026-04"]) ** (1.0 / 3)
    g_fit = (a["2026-04"] / a["2026-02"]) ** (1.0 / 2)
    print("\n   [Anthropic] 2月+4月锚点外推 → 7月 run-rate（减速检验）")
    print("      预测 $%.0fB vs 实际 $%.0fB → 误差 %+.0f%%"
          % (pred_a, act_a, (pred_a / act_a - 1) * 100))
    print("      月环比：拟合段 %.2fx → 实际后段 %.2fx（减速 → 恒定指数高估）"
          % (g_fit, g_real))

    # --- Google: consensus vs actual ---
    gc = d["google_cloud"]
    print("\n   [Google Cloud] 卖方 consensus vs GAAP 实际")
    for q in ("q1", "q2"):
        c, t = gc["consensus_%s" % q], gc["gaap_%s_2026" % q]
        print("      %s: consensus $%.1fB vs 实际 $%.1fB → 低配 %.1f%%"
              % (q.upper(), c, t, (t / c - 1) * 100))
    print("      backlog: $%.0fB → $%.0fB（环比 +%.0f%%）— 收入之外的第二领先指标"
          % (gc["backlog_q1"], gc["backlog_q2"],
             (gc["backlog_q2"] / gc["backlog_q1"] - 1) * 100))

    # --- DeepSeek: control group ---
    ds = d["deepseek"]
    print("\n   [DeepSeek] 对照组：开源极低价路线，无财报可对答案")
    print("      2025-03 理论日收入 $%s → 年化 $%.2fB；2026 年化 ≈$%.1fB（媒体）"
          % ("{:,}".format(ds["theoretical_daily_rev_usd_202503"]),
             ds["theoretical_daily_rev_usd_202503"] * 365 / 1e9,
             ds["annualized_2026_usd_b"]))

    print("\n③ 行业级发现")
    for s in [
        "锚点法：加速期准（智谱-4%/OpenAI+9%），减速段高估（Anthropic+45%）→ 需加衰减项",
        "consensus 系统性低配爆发期 ~10%（Google 连续两季 beat）",
        "三路线分化：闭源高价$65B / 闭源平价$40B / 开源低价$0.5B（高利润率）",
        "backlog（Google $514B）是 ARR 之外的第二领先指标",
    ]:
        print("   - %s" % s)


if __name__ == "__main__":
    main()
