"""Industry profiles demo — NVDA re-run with v0.16: the engine now *knows*
which segment to trust and which to scenario.

Before v0.16, the industry-fit lesson lived in a hand-written backtest script
(the analyst had to know to apply the right method per segment). Now the
knowledge is in the engine:

1. ``list_profiles()``          — the catalog (mechanism → defaults → checks)
2. tag segments                 — Gaming→semiconductor, Data Center→?
3. ``check_segment()``          — the mis-tag teaching moment: DC tagged
   "semiconductor" trips the hypergrowth check → retag regime_shift_tech
4. ``forecast_segment()``       — profile-default forecasts (no hand tuning)
5. verdict                      — strong-fit tracks, weak-fit collapses *and
   says so loudly* (segment_warnings)
6. Monte Carlo close-out        — the Bull tail frames the actual $115B

Same data as ``examples/nvda_demo`` (train FY2019-FY2023, hold out FY2024-25).

Run: ``python industry_demo.py``
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from revenue_model import (
    Driver, Segment, BASE, PENETRATION, SHARE, PRICE, implied_driver,
    simulate_segment, scenarios,
    list_profiles, resolve_industry, forecast_segment,
    check_segment, segment_warnings,
)

TRAIN = [2019, 2020, 2021, 2022, 2023]
HOLDOUT = [2024, 2025]

GAMING = {2019: 6246, 2020: 5559, 2021: 7764, 2022: 12462, 2023: 9067,
          2024: 10447, 2025: 11047}
DC = {2019: 2932, 2020: 2983, 2021: 6696, 2022: 10613, 2023: 15005,
      2024: 47525, 2025: 115186}

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

DC_SCENARIO_RANGES = {   # same honest wide bands as the original demo
    2024: {"accelerator shipments": (2.5, 6.0), "share": (0.80, 0.95), "GPU ASP": (7000, 14000)},
    2025: {"accelerator shipments": (3.0, 12.0), "share": (0.78, 0.95), "GPU ASP": (9000, 22000)},
}


def _build(name, drv, actual, industry, price_label, base_name):
    seg = Segment(name,
        base=Driver(base_name, BASE, drv["base"], level="C",
                    unit="M units", source="estimate"),
        penetration=Driver("penetration", PENETRATION, drv["penetration"],
                           level="C", unit="fraction", source="structural"),
        share=Driver("share", SHARE, drv["share"], level="C",
                     unit="fraction", source="estimate"),
        price=Driver(price_label, PRICE, {}, level="C",
                     unit="$/unit", source="implied"),
        industry=industry)
    for y in TRAIN:
        seg.price.values[y] = implied_driver(seg, y, actual[y], PRICE)
    return seg


def smape(pred, actual):
    return 100.0 * sum(abs(p - a) / (abs(p) + abs(a))
                       for p, a in zip(pred, actual)) / len(pred)


def main():
    print("=" * 74)
    print(" v0.16 industry profiles — the fit matrix, executable")
    print("=" * 74)

    print("\n[1] The catalog — mechanism profiles (GICS aliases accepted too):")
    for key, fit, label in list_profiles():
        print("    {:22s} {:6s}  {}".format(key, "[" + fit + "]", label))

    gaming = _build("Gaming", GAMING_DRV, GAMING, "semiconductor",
                    "GeForce ASP", "PC shipments")
    dc = _build("Data Center", DC_DRV, DC, "semiconductor",   # deliberately wrong first
                "GPU ASP", "accelerator shipments")

    print("\n[2] Mis-tag teaching moment — DC tagged 'semiconductor' (wrong):")
    for w in check_segment(dc):
        print("    CHECK:", w)

    print("\n    -> retag: regime_shift_tech")
    dc.industry = "regime_shift_tech"
    for w in segment_warnings(dc):
        print("    -", w)

    print("\n[3] forecast_segment with profile defaults (no hand tuning):")
    print("    Gaming (semiconductor):")
    g_fc = forecast_segment(gaming, HOLDOUT)
    for d in g_fc.drivers():
        print("      {:12s}[{}] forecast via {}".format(
            d.kind, d.level, d.source))
    print("    Data Center (regime_shift_tech):")
    d_fc = forecast_segment(dc, HOLDOUT)
    for d in d_fc.drivers():
        print("      {:12s}[{}] forecast via {}".format(
            d.kind, d.level, d.source))

    print("\n[4] Hold-out verdict — train FY2019-23, predict FY2024-25:")
    rows = []
    for label, seg, actual in (("Gaming", g_fc, GAMING), ("Data Center", d_fc, DC)):
        preds = [seg.revenue(y) for y in HOLDOUT]
        errs = [(p - actual[y]) / actual[y] for y, p in zip(HOLDOUT, preds)]
        s = smape(preds, [actual[y] for y in HOLDOUT])
        rows.append((label, s))
        print("    {}".format(label))
        print("      predicted ($B): " + "  ".join(
            "FY{}={:.1f}".format(y, p / 1e3) for y, p in zip(HOLDOUT, preds)))
        print("      actual    ($B): " + "  ".join(
            "FY{}={:.1f}".format(y, actual[y] / 1e3) for y in HOLDOUT))
        print("      error:          " + "  ".join(
            "FY{}={:+.0%}".format(y, e) for y, e in zip(HOLDOUT, errs)))
        print("      sMAPE: {:.1f}%".format(s))

    print("\n    -> the strong-fit segment tracked on generic defaults; the weak-")
    print("       fit segment collapsed by ~6x — and the ENGINE flagged it before")
    print("       the hold-out was ever opened (see [2]).")

    print("\n[5] Monte Carlo close-out on Data Center (the weak-fit redirect):")
    for y in HOLDOUT:
        mc = simulate_segment(d_fc, y, DC_SCENARIO_RANGES[y], n=5000, seed=0)
        real = DC[y]
        pctile = 100.0 * sum(1 for v in mc.samples if v < real) / len(mc.samples)
        print("\n    FY{}  actual = ${:.1f}B  (~P{:.0f} of the simulated distribution)".format(
            y, real / 1e3, pctile))
        for s in scenarios(mc):
            tag = "  <-- actual nearest here" if abs(s.revenue - real) / real < 0.20 else ""
            print("       {:5s} (P{:.0f}): ${:6.1f}B{}".format(
                s.name, s.percentile * 100, s.revenue / 1e3, tag))

    print("\n" + "=" * 74)
    print(" Reading")
    print("=" * 74)
    print("  Same company, same data, same engine — the only new input was the")
    print("  industry tag, and it changed everything: which defaults applied,")
    print("  which warnings fired, and which forecast mode (point vs scenarios)")
    print("  is even meaningful. Accuracy is a property of the industry; v0.16")
    print("  makes the engine say so out loud. Docs: docs/industry-fit-analysis.md")


if __name__ == "__main__":
    main()
