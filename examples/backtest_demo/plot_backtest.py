"""Plot the ten-company backtest comparison from the cached JSON summary.

Reads ``data/backtest_summary.json`` (produced by backtest_ten_companies.py)
and writes two PNGs next to this script:

  * heatmap_smape.png — company × method grid, color = sMAPE (greener = better)
  * ranking.png       — average sMAPE (ranked) + per-method win count

Headless (Agg) so it runs without a display. Reuses the viz module's CJK-font
convention so Chinese company names render.

Run:  python plot_backtest.py
Needs: pip install -e ".[viz]"  (matplotlib)
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei",
                                   "Noto Sans CJK SC", "PingFang SC"]
plt.rcParams["axes.unicode_minus"] = False

_C_BASE = "#3b6ea8"
_C_GOOD = "#4f9d69"
_C_BAD = "#d9534f"


def main():
    with open(os.path.join(HERE, "data", "backtest_summary.json"),
              encoding="utf-8") as fh:
        summary = json.load(fh)
    companies = summary["companies"]
    methods = summary["methods"]
    labels = [c["name"] for c in companies]

    # ---- Fig 1: heatmap company x method ----
    M = np.array([[c["smape"][m] * 100 for m in methods] for c in companies])
    fig, ax = plt.subplots(figsize=(10, 6))
    im = ax.imshow(M, cmap="RdYlGn_r", aspect="auto", vmin=0, vmax=60)
    ax.set_xticks(range(len(methods)), methods, fontsize=11)
    ax.set_yticks(range(len(labels)), labels, fontsize=11)
    ax.set_xlabel("预测方法", fontsize=11)
    ax.set_title("十家A股 · 各方法 sMAPE(%) 热力图（越绿越准）", fontsize=13,
                 fontweight="bold")
    for i in range(len(labels)):
        for j in range(len(methods)):
            v = M[i, j]
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=9,
                    color="white" if v > 42 else "#1a1a1a", fontweight="bold")
    fig.colorbar(im, ax=ax, label="sMAPE (%)", shrink=0.85)
    fig.tight_layout()
    p1 = os.path.join(HERE, "heatmap_smape.png")
    fig.savefig(p1, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"saved: {p1}")

    # ---- Fig 2: average sMAPE (ranked) + win count ----
    avg = {m: float(np.mean([c["smape"][m] for c in companies])) * 100
           for m in methods}
    wins = {m: 0 for m in methods}
    for c in companies:
        wins[min(methods, key=lambda x: c["smape"][x])] += 1

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    ax = axes[0]
    order = sorted(methods, key=lambda x: avg[x])
    colors = [_C_GOOD if avg[m] == min(avg.values()) else
              (_C_BAD if avg[m] == max(avg.values()) else _C_BASE)
              for m in order]
    bars = ax.barh(order, [avg[m] for m in order], color=colors, alpha=0.85)
    for b, m in zip(bars, order):
        ax.text(b.get_width() + 0.4, b.get_y() + b.get_height() / 2,
                f"{avg[m]:.1f}%", va="center", fontsize=10)
    ax.set_xlabel("跨公司平均 sMAPE (%)", fontsize=11)
    ax.set_title("① 平均精度排名（越低越好）", fontsize=12, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)

    ax = axes[1]
    won = sorted(methods, key=lambda x: -wins[x])
    bars = ax.barh(won, [wins[m] for m in won], color=_C_GOOD, alpha=0.85)
    for b, m in zip(bars, won):
        ax.text(b.get_width() + 0.08, b.get_y() + b.get_height() / 2,
                f"{wins[m]} / {len(companies)} 家", va="center", fontsize=10)
    ax.set_xlabel("单家最优次数", fontsize=11)
    ax.set_title("② 各方法'赢'的次数", fontsize=12, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)

    fig.suptitle("十家A股收入预测回测 · 方法对比", fontsize=14,
                 fontweight="bold", y=1.02)
    fig.tight_layout()
    p2 = os.path.join(HERE, "ranking.png")
    fig.savefig(p2, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"saved: {p2}")


if __name__ == "__main__":
    main()
