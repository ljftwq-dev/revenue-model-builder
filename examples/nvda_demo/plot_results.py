"""NVDA Gaming vs Data Center — actual vs driver-extrapolated forecast chart.

Produces a 1x2 panel that is the single most persuasive artifact of the demo:

- Left  — Gaming: actual vs trend-extrapolated hold-out. They overlap.
- Right — Data Center: actual vs trend-extrapolated hold-out (huge gap) PLUS
          the Bear-Bull scenario band that frames the breakout.

Same build/extrapolate logic as ``backtest_nvda.py`` (factored here without the
printing). Headless (Agg), so it runs in CI and on any box without a display.

Run: ``python plot_results.py``  (needs ``pip install -e ".[viz]"``)
"""
import os
import sys
import csv

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from revenue_model import (
    Driver, Segment, BASE, PENETRATION, SHARE, PRICE, implied_driver,
    simulate_segment, scenarios,
)

DATA = os.path.join(HERE, "data")
TRAIN = [2019, 2020, 2021, 2022, 2023]
HOLDOUT = [2024, 2025]
SHARE_CAP = 0.95

DC_SCENARIO_RANGES = {
    2024: {"accelerator shipments": (2.5, 6.0), "share": (0.80, 0.95), "GPU ASP": (7000, 14000)},
    2025: {"accelerator shipments": (3.0, 12.0), "share": (0.78, 0.95), "GPU ASP": (9000, 22000)},
}


def _read(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _hold(driver, years):
    last_yr = max(driver.values)
    val = driver.values[last_yr]
    return Driver(driver.name, driver.kind, {**driver.values, **{y: val for y in years}},
                  level="C", unit=driver.unit, source="held")


def _build(name, drv, actual, price_label):
    base_name = "PC shipments" if "Gaming" in name else "accelerator shipments"
    seg = Segment(name,
        base=Driver(base_name, BASE, drv["base"], level="C", unit="M units", source=""),
        penetration=Driver("penetration", PENETRATION, drv["penetration"], level="C", unit="fraction", source=""),
        share=Driver("share", SHARE, drv["share"], level="C", unit="fraction", source=""),
        price=Driver(price_label, PRICE, {}, level="C", unit="$/unit", source=""))
    for y in TRAIN:
        seg.price.values[y] = implied_driver(seg, y, actual[y], PRICE)
    return seg


def _extrapolate(seg):
    seg.base = seg.base.fit_trend(TRAIN).extrapolate(HOLDOUT)
    seg.penetration = _hold(seg.penetration, HOLDOUT)
    seg.share = seg.share.fit_trend(TRAIN).extrapolate(HOLDOUT)
    for y in HOLDOUT:
        seg.share.values[y] = min(max(seg.share.values[y], 0.0), SHARE_CAP)
    seg.price = seg.price.fit_trend(TRAIN).extrapolate(HOLDOUT)
    return seg


def main():
    rows = _read(os.path.join(DATA, "segments.csv"))
    years = [int(r["fiscal_year"]) for r in rows]
    gaming_actual = {int(r["fiscal_year"]): float(r["gaming"]) for r in rows}
    dc_actual = {int(r["fiscal_year"]): float(r["dc"]) for r in rows}

    g_drv = {k: {int(y): v for y, v in val.items()} for k, val in {
        "base": {"2019": 261, "2020": 275, "2021": 303, "2022": 304, "2023": 260},
        "penetration": {"2019": 0.13, "2020": 0.14, "2021": 0.16, "2022": 0.18, "2023": 0.14},
        "share": {"2019": 0.80, "2020": 0.80, "2021": 0.83, "2022": 0.85, "2023": 0.80},
    }.items()}
    d_drv = {k: {int(y): v for y, v in val.items()} for k, val in {
        "base": {"2019": 0.5, "2020": 0.6, "2021": 1.0, "2022": 1.5, "2023": 2.5},
        "penetration": {"2019": 1.0, "2020": 1.0, "2021": 1.0, "2022": 1.0, "2023": 1.0},
        "share": {"2019": 0.60, "2020": 0.65, "2021": 0.80, "2022": 0.85, "2023": 0.88},
    }.items()}

    g = _extrapolate(_build("Gaming", g_drv, gaming_actual, "GeForce ASP"))
    d = _extrapolate(_build("Data Center", d_drv, dc_actual, "GPU ASP"))

    g_pred = {y: g.revenue(y) for y in HOLDOUT}
    d_pred = {y: d.revenue(y) for y in HOLDOUT}

    # DC scenario band (Bear/Bull) for the hold-out years.
    d_band = {}
    for y in HOLDOUT:
        mc = simulate_segment(d, y, DC_SCENARIO_RANGES[y], n=5000, seed=0)
        sc = {s.name: s.revenue for s in scenarios(mc)}
        d_band[y] = (sc["Bear"], sc["Bull"])

    fig, (ax_g, ax_d) = plt.subplots(1, 2, figsize=(13, 5.2))
    billions = FuncFormatter(lambda x, _: "${:.0f}B".format(x))

    def _panel(ax, actual, pred, title, subtitle):
        yr_all = sorted(actual)
        ax.plot(yr_all, [actual[y] / 1e3 for y in yr_all], "o-", color="#2c3e50",
                lw=2, ms=5, label="actual", zorder=3)
        ax.plot(HOLDOUT, [pred[y] / 1e3 for y in HOLDOUT], "s--", color="#e74c3c",
                lw=1.8, ms=7, label="driver extrapolation", zorder=3)
        ax.axvline(2023.5, color="gray", ls=":", lw=1)
        ax.text(2023.5, ax.get_ylim()[1] * 0.95, "  train | hold-out", color="gray", fontsize=8, va="top")
        ax.set_title(title, fontweight="bold")
        ax.set_xlabel("NVIDIA fiscal year")
        ax.set_ylabel("segment revenue")
        ax.yaxis.set_major_formatter(billions)
        ax.grid(alpha=0.25)
        ax.legend(loc="upper left", fontsize=9)
        ax.text(0.5, -0.18, subtitle, transform=ax.transAxes, ha="center", fontsize=9, style="italic", color="#555")

    _panel(ax_g, gaming_actual, g_pred, "Gaming — trend market",
           "Extrapolation tracks: hold-out lands within ~4% (sMAPE 1.0%)")

    # DC panel adds the scenario band.
    yr_all = sorted(dc_actual)
    ax_d.plot(yr_all, [dc_actual[y] / 1e3 for y in yr_all], "o-", color="#2c3e50", lw=2, ms=5, label="actual", zorder=3)
    ax_d.plot(HOLDOUT, [d_pred[y] / 1e3 for y in HOLDOUT], "s--", color="#e74c3c", lw=1.8, ms=7, label="driver extrapolation", zorder=3)
    bx = HOLDOUT + list(reversed(HOLDOUT))
    by = [d_band[y][0] / 1e3 for y in HOLDOUT] + [d_band[y][1] / 1e3 for y in reversed(HOLDOUT)]
    ax_d.fill(bx, by, color="#27ae60", alpha=0.18, label="Bear-Bull scenario band", zorder=1)
    ax_d.axvline(2023.5, color="gray", ls=":", lw=1)
    ax_d.text(2023.5, ax_d.get_ylim()[1] * 0.95, "  train | hold-out", color="gray", fontsize=8, va="top")
    ax_d.set_title("Data Center — AI regime shift", fontweight="bold")
    ax_d.set_xlabel("NVIDIA fiscal year")
    ax_d.set_ylabel("segment revenue")
    ax_d.yaxis.set_major_formatter(billions)
    ax_d.grid(alpha=0.25)
    ax_d.legend(loc="upper left", fontsize=9)
    ax_d.text(0.5, -0.18,
              "Extrapolation misses by 60-84%; but the scenario band frames the breakout",
              transform=ax_d.transAxes, ha="center", fontsize=9, style="italic", color="#555")

    fig.suptitle("NVIDIA: same driver tree, two outcomes — accuracy is a property of the industry",
                 fontweight="bold", fontsize=12.5, y=1.02)
    fig.tight_layout()
    out = os.path.join(HERE, "nvda_backtest.png")
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print("chart -> {}".format(out))


if __name__ == "__main__":
    main()
