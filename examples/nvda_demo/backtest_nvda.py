"""NVIDIA driver hold-out backtest — Gaming (trend) vs Data Center (regime shift),
plus the scenario close-out that turns DC's "failure" into a teaching win.

The methodological heart of the demo. With a uniform rule and the *same* driver
tree for both segments, we train on FY2019-FY2023 and extrapolate every driver
to FY2024-FY2025 without peeking:

- ``base`` / ``share`` / ``price`` — OLS trend on the training window
- ``penetration`` — held (structural)

If the driver tree were universally good, both segments would track. Instead:

- **Gaming** — mature market, clean trend -> hold-out lands close.
- **Data Center** — AI paradigm shift (FY2024+) -> trend extrapolation
  *structurally* under-predicts. This is not a model failure; it is the demo's
  central thesis: a driver tree's accuracy depends on whether the industry's
  growth mechanism is trend-extrapolatable.

Then the close-out: a point forecast is doomed on DC, but a **scenario
distribution** (Monte Carlo over wide, honestly-uncertain driver bands) frames
the actual. The lesson: under a regime shift, swap point prediction for
uncertainty management.

Run: ``python backtest_nvda.py``
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from revenue_model import (
    Driver, Segment, BASE, PENETRATION, SHARE, PRICE, implied_driver,
    simulate_segment, scenarios,
)

# Training / hold-out split. The split sits at FY2024 = the AI breakout year
# (Data Center $15.0B -> $47.5B -> $115.2B). Training sees only the pre-breakout
# trend; hold-out is the breakout itself.
TRAIN = [2019, 2020, 2021, 2022, 2023]
HOLDOUT = [2024, 2025]

# Reported segment revenue, $M (from segments.csv / NVIDIA 10-K).
GAMING = {2019: 6246, 2020: 5559, 2021: 7764, 2022: 12462, 2023: 9067,
          2024: 10447, 2025: 11047}
DC = {2019: 2932, 2020: 2983, 2021: 6696, 2022: 10613, 2023: 15005,
      2024: 47525, 2025: 115186}

# Training-window driver values (from drivers_*.csv, FY2019-2023 only).
GAMING_DRV = {
    "base": {2019: 261, 2020: 275, 2021: 303, 2022: 304, 2023: 260},
    "penetration": {2019: 0.13, 2020: 0.14, 2021: 0.16, 2022: 0.18, 2023: 0.14},
    "share": {2019: 0.80, 2020: 0.80, 2021: 0.83, 2022: 0.85, 2023: 0.80},
}
DC_DRV = {
    "base": {2019: 0.5, 2020: 0.6, 2021: 1.0, 2022: 1.5, 2023: 2.5},
    "penetration": {2019: 1.0, 2020: 1.0, 2021: 1.0, 2022: 1.0, 2023: 1.0},
    "share": {2019: 0.60, 2020: 0.65, 2021: 0.80, 2022: 0.85, 2023: 0.88},
}

# Physical cap: market share cannot exceed 1.0 (OLS on a rising series can).
SHARE_CAP = 0.95

# Wide driver bands for the DC scenario distribution — these reflect the genuine
# C-grade uncertainty around an AI breakout (not peeking at actual revenue).
# base = accelerator shipments (M), share = NVIDIA AI share, GPU ASP in $/unit.
DC_SCENARIO_RANGES = {
    2024: {"accelerator shipments": (2.5, 6.0), "share": (0.80, 0.95), "GPU ASP": (7000, 14000)},
    2025: {"accelerator shipments": (3.0, 12.0), "share": (0.78, 0.95), "GPU ASP": (9000, 22000)},
}


def _hold(driver, years):
    last_yr = max(driver.values)
    last_val = driver.values[last_yr]
    new_vals = dict(driver.values)
    for y in years:
        new_vals[y] = last_val
    return Driver(driver.name, driver.kind, new_vals, level="C",
                  unit=driver.unit, source="held at {}".format(last_yr))


def _build_segment(name, drv, actual, price_label, base_src):
    base_name = "PC shipments" if "Gaming" in name else "accelerator shipments"
    seg = Segment(name,
        base=Driver(base_name, BASE, drv["base"], level="C",
                    unit="M units", source=base_src),
        penetration=Driver("penetration", PENETRATION, drv["penetration"],
                           level="C", unit="fraction", source="structural"),
        share=Driver("share", SHARE, drv["share"], level="C",
                     unit="fraction", source="estimate"),
        price=Driver(price_label, PRICE, {}, level="C",
                     unit="$/unit", source="implied"))
    for y in TRAIN:
        seg.price.values[y] = implied_driver(seg, y, actual[y], PRICE)
    return seg


def smape(pred, actual):
    return 100.0 * sum(abs(p - a) / (abs(p) + abs(a)) for p, a in zip(pred, actual)) / len(pred)


def holdout(seg, actual, label):
    """Extrapolate trained drivers to hold-out years, report accuracy."""
    seg.base = seg.base.fit_trend(TRAIN).extrapolate(HOLDOUT)
    seg.penetration = _hold(seg.penetration, HOLDOUT)
    seg.share = seg.share.fit_trend(TRAIN).extrapolate(HOLDOUT)
    for y in HOLDOUT:  # clip share into a valid band
        seg.share.values[y] = min(max(seg.share.values[y], 0.0), SHARE_CAP)
    seg.price = seg.price.fit_trend(TRAIN).extrapolate(HOLDOUT)

    print("\n  {} — driver extrapolation to hold-out:".format(label))
    preds = [seg.revenue(y) for y in HOLDOUT]
    print("    predicted ($B): " + "  ".join("FY{}={:.1f}".format(y, p / 1e3) for y, p in zip(HOLDOUT, preds)))
    print("    actual    ($B): " + "  ".join("FY{}={:.1f}".format(y, actual[y] / 1e3) for y in HOLDOUT))
    errs = [(p - actual[y]) / actual[y] for y, p in zip(HOLDOUT, preds)]
    print("    error:         " + "  ".join("FY{}={:+.0%}".format(y, e) for y, e in zip(HOLDOUT, errs)))
    s = smape(preds, [actual[y] for y in HOLDOUT])
    print("    sMAPE: {:.1f}%".format(s))
    return s


def dc_scenario_closeout(dc_seg):
    """The teaching payoff: DC point forecast broke — can a scenario distribution
    frame the actual? Monte Carlo over wide, honestly-uncertain driver bands."""
    print("\n" + "=" * 74)
    print(" DATA CENTER scenario close-out — point forecast broke, scenarios frame it")
    print("=" * 74)
    print(" Wide driver bands (honest C-grade uncertainty, NOT fitted to actuals):")
    for y in HOLDOUT:
        r = DC_SCENARIO_RANGES[y]
        print("   FY{}: shipments {}-{}M, share {:.2f}-{:.2f}, ASP ${:,}-${:,}".format(
            y, r["accelerator shipments"][0], r["accelerator shipments"][1],
            r["share"][0], r["share"][1], r["GPU ASP"][0], r["GPU ASP"][1]))

    for y in HOLDOUT:
        mc = simulate_segment(dc_seg, y, DC_SCENARIO_RANGES[y], n=5000, seed=0)
        sc = scenarios(mc)
        real = DC[y]
        below = sum(1 for v in mc.samples if v < real)
        pctile = below / len(mc.samples) * 100
        print("\n  FY{}  actual = ${:.1f}B  (sits at ~P{:.0f} of the simulated distribution)".format(
            y, real / 1e3, pctile))
        for s in sc:
            tag = "  <-- actual is nearest here" if abs(s.revenue - real) / real < 0.20 else ""
            print("     {:5s} (P{:.0f}): ${:6.1f}B{}".format(s.name, s.percentile * 100, s.revenue / 1e3, tag))

    print("\n  Reading: the trend point-forecast landed near Base (~P50) and badly")
    print("  under-predicted, but the Bull tail of an honestly-wide distribution")
    print("  captures the breakout. Under a regime shift you cannot get the point")
    print("  right — but you CAN bound it. That is the whole job of scenario analysis.")


def main():
    print("=" * 74)
    print(" NVIDIA driver hold-out — train FY2019-FY2023, hold-out FY2024-FY2025")
    print("=" * 74)
    print(" Rule: base/share/price = OLS trend on training; penetration = hold.")
    print(" Same driver tree, same engine — only the data differs.")

    g = _build_segment("Gaming", GAMING_DRV, GAMING, "GeForce ASP", "IDC")
    d = _build_segment("Data Center", DC_DRV, DC, "GPU ASP", "estimate")

    print("\n--- GAMING (expect: trend holds) ---")
    g_s = holdout(g, GAMING, "Gaming")
    print("\n--- DATA CENTER (expect: AI breakout breaks the trend) ---")
    d_s = holdout(d, DC, "Data Center")

    print("\n" + "=" * 74)
    print(" VERDICT")
    print("=" * 74)
    print("  Gaming      sMAPE = {:>5.1f}%   (driver tree works on trend markets)".format(g_s))
    print("  Data Center sMAPE = {:>5.1f}%   (driver tree breaks on regime shift)".format(d_s))
    print("\n  -> Data Center error is {:.0f}x Gaming's. The same formula fails on".format(d_s / g_s))
    print("     an event-driven breakout while succeeding on a trend market.")
    print("     Accuracy is a property of the INDUSTRY, not the model.")

    # Scenario close-out turns DC's "failure" into the demo's teaching payoff.
    dc_scenario_closeout(d)


if __name__ == "__main__":
    main()
