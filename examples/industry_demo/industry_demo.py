"""Industry profiles demo — NVDA re-run with v0.16: the engine now *knows*
which segment to trust and which to scenario.

Before v0.16, the industry-fit lesson lived in a hand-written backtest script
(the analyst had to know to apply the right method per segment). Now the
knowledge is in the engine:

1. ``list_profiles()``          — the catalog (mechanism → defaults → checks)
1b. ``suggest_profile()``       — v0.19: no tag yet? a ranked shortlist with
   evidence, before you commit to a profile
2. tag segments                 — Gaming→semiconductor, Data Center→?
2b. ``benchmark_warnings()``    — v0.18: growth reads vs Damodaran bands,
   citation inside the warning text (in-band = silent)
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
    list_profiles, forecast_segment,
    check_segment, benchmark_warnings, segment_warnings,
    suggest_profile,
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

    gaming = _build("Gaming", GAMING_DRV, GAMING, "",       # v0.19: untagged first
                    "GeForce ASP", "PC shipments")
    dc = _build("Data Center", DC_DRV, DC, "",              # untagged first
                "GPU ASP", "accelerator shipments")

    print("\n[1b] v0.19 suggest_profile — don't know the industry yet? ask:")
    for s in suggest_profile(gaming):
        print("    {:24s} score {:4.1f}".format(s.key, s.score))
        for r in s.reasons[:2]:
            print("        -", r)
    print("    -> the analyst accepts the top candidate and tags Gaming")
    gaming.industry = "semiconductor"

    print("\n[2] Mis-tag teaching moment — DC tagged 'semiconductor' (wrong).")
    print("    (v0.19 could have prevented it: the untagged shortlist leads")
    print("     with the regime-shift warning — we ignore it on purpose.)")
    for s in suggest_profile(dc)[:1]:
        print("    untagged suggestion #1: {} score {:.1f}".format(s.key, s.score))
        for r in s.reasons[-1:]:
            print("        -", r)
    dc.industry = "semiconductor"   # deliberately wrong
    for w in check_segment(dc):
        print("    CHECK:", w)

    print("\n[2b] v0.18 citation layer — the same reads, now with evidence")
    print("     (segment growth vs Damodaran industry bands, in-band = silent):")
    print("     Gaming (a TRUE semiconductor segment, but growing below the")
    print("     cluster band — NVDA Gaming underperformed its industry):")
    for w in benchmark_warnings(gaming):
        print("    BENCH:", w)
    print("     Data Center (the mis-tag — the band check fires ABOVE with")
    print("     the full citation in the warning text):")
    for w in benchmark_warnings(dc):
        print("    BENCH:", w)
    print("     -> v0.16 checks said 'that's rare'; v0.18 says 'the industry")
    print("        historical band is 9.8-10.7%/yr across 97 firms — yours is")
    print("        far outside, cite why'. Same soft philosophy: evidence,")
    print("        not roadblocks.")

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
    print("  is even meaningful. And since v0.19 you don't even need to know")
    print("  the tag up front: the shortlist carries the evidence, you make")
    print("  the call (wrong-tag caught [2] / right-tag suggested [1b] — two")
    print("  halves of one loop). Accuracy is a property of the industry;")
    print("  v0.16-v0.19 make the engine say so out loud.")
    print("  Docs: docs/industry-fit-analysis.md")


if __name__ == "__main__":
    main()
