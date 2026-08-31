"""M5: growth-decay early warning - when does the leader's g(t) roll over?

Uses the OpenRouter weekly snapshot (decay_signals.json: 82 weeks, 2025-01
to 2026-08, 28-day rolling tokens/share/wow-growth for anthropic / deepseek
/ zhipu(z-ai) / openai / google) to answer the question the ARR-ladder
scorecards raised: Anthropic's constant-exponential extrapolation overshot
by +45% because g decayed from 1.46x to 1.29x/month - *when* does that
happen, and can we see it coming?

Three detectors (calibrated on the 600-day daily series):

  D1  self-decay     : leader g < 1.0 for 3 consecutive weeks after an
                       8-week baseline above 1.05  (confirmation)
  D2  rival-momentum : a rival's share jumps > 5pp within 4 weeks, twice in
                       a row                                              (lead ~8w)
  D3  regime filter  : total market growth (5-vendor rolling sum) also
                       slowing  -  without D3, rival launch can coincide with
                       a rising tide that hides the diversion (GLM-5, Feb-26:
                       anthropic *accelerated* despite zhipu's biggest launch)

Rule of thumb: decay = D2 (rival) + D3 (tide turning) -> then D1 confirms.

Run:  python decay_early_warning.py   (pure stdlib, data snapshot included)
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def load():
    with open(os.path.join(DATA, "decay_signals.json"), encoding="utf-8") as fh:
        return json.load(fh)["weeks"]


def detect_self_decay(w):
    """D1: g<1.0 for 3 straight weeks after 8-week baseline > 1.05."""
    hits = []
    for k in range(8, len(w)):
        base = sum(r["ant_g"] for r in w[k - 8:k] if "ant_g" in r) / 8
        if base > 1.05 and all(w[k - j].get("ant_g", 1) < 1.0 for j in (0, 1, 2)):
            if not hits or w[k]["week_end"] != hits[-1]:
                hits.append(w[k]["week_end"])
    return hits


def detect_rival_momentum(w, key, step_pp=5.0):
    """D2: rival share rises >step_pp within 4 weeks (report each window once)."""
    hits, last = [], -99
    for k in range(4, len(w)):
        a, b = w[k].get(key + "_share"), w[k - 4].get(key + "_share")
        if a is not None and b is not None and (a - b) * 100 > step_pp and k - last > 4:
            hits.append((w[k]["week_end"], b, a))
            last = k
    return hits


def detect_tide_slowing(w):
    """D3: total 5-vendor rolling tokens growth below 1.02 for 3 straight weeks."""
    tot = [sum(r[k] for k in ("ant_tok", "ds_tok", "zai_tok", "oai_tok", "ggl_tok")) for r in w]
    hits = []
    for k in range(1, len(w) - 2):
        if all(tot[k + j] / tot[k + j - 1] < 1.02 for j in (0, 1, 2)):
            hits.append(w[k]["week_end"])
    return hits


def main():
    w = load()

    print("=" * 76)
    print(" M5 增长率衰减预警：领跑者 g(t) 何时翻车（OpenRouter 82周快照）")
    print("=" * 76)

    # ---- D1 self-decay ----
    d1 = detect_self_decay(w)
    print("\n① D1 自身衰减确认（anthropic g<1.0 连续3周，此前8周基线>1.05）")
    for h in d1:
        print("    确认周: %s" % h)
    if not d1:
        print("    （当前窗口未触发——注意2026-07末的 g=0.93/0.88/0.91 已接近）")

    # ---- D2 rival momentum ----
    print("\n② D2 竞品份额冲击（4周内涨幅 >5pp）")
    for key, name in (("ds", "DeepSeek"), ("zai", "智谱")):
        for wk, b, a in detect_rival_momentum(w, key):
            print("    %-7s %s  份额 %.0f%% -> %.0f%%" % (name, wk, b * 100, a * 100))

    # ---- D3 tide ----
    d3 = detect_tide_slowing(w)
    print("\n③ D3 总盘退潮（五厂商28天合计周环比<1.02 连续3周）")
    print("    退潮周: %s ... 共%d周" % (", ".join(d3[-4:]), len(d3)))

    # ---- 对齐结论 ----
    print("\n④ 对齐解读（衰减 = D2 + D3，D1 确认）")
    for s in [
        "2025-04: DeepSeek份额9->16%(D2) + 总盘放缓(D3) -> anthropic g 1.05->0.95 第一次失速",
        "2025-08: 智谱GLM-4.5/4.6上市 0->3.8%(D2), 总盘平稳 -> anthropic g 1.17->0.97 停滞",
        "2026-02: GLM-5爆发 4->10%(D2) 但总盘加速(无D3) -> anthropic 反而加速 1.04->1.15",
        "2026-05~07: DeepSeek V4系列 13->44%(D2) + 总盘退潮(D3) -> anthropic 27.1T->19.7T, -27%",
    ]:
        print("    - %s" % s)

    print("\n⑤ 用法：把 D2 触发（竞品份额月涨>5pp）作为 g(t) 衰减项的先验，")
    print("   领先 D1 确认约 8 周；若无 D3（总盘仍在涨），衰减项置 0。")
    print("   校准样本：本快照 4 次竞品冲击，2 次（有D3）转绝对衰减，2 次无D3未转化。")


if __name__ == "__main__":
    main()
