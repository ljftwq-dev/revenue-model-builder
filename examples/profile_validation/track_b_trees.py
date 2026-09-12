"""Track B: hand-built driver trees exercising the real v0.16 API.

Five new trees (final list frozen 2026-09-12, before any FY2025 test actual
was opened for the trees themselves; FY2025 actuals for revenue/NII were
already public and are cited below) + the two pre-existing NVDA trees from
examples/industry_demo (legacy split, predates this experiment, noted).

All driver histories end <= FY2024 (train + validation years). The FY2025
test slice is touched once by run_track_b.py.

Data sources (per series):
- SBUX stores: 10-K FY20 (31,256), 8-K Q4 FY20 (32,638), 10-K FY21 (33,833),
  8-K Q4 FY22 (35,711), 10-K/8-K FY23 (38,038), 8-K Q4 FY24 (40,199)  [A]
- SBUX revenue: SEC XBRL panel (data/revenue_panel.csv)                 [A]
- META ad revenue + impressions/price YoY: Q4 FY21/FY22/FY23/FY24/FY25
  press releases (FY25: $196,175M; imp +12%, price +9%)                  [A/B]
- NFLX paid memberships: 10-K FY23 (260M), FY24 (302M), Q4 letters
  (167.09 / 203.66 / 221.84 / 230.75 / 260.28 / 301.63 M)                [A/B]
- NFLX revenue: SEC XBRL panel                                           [A]
- JPM NII + total assets: SEC XBRL companyconcept, end-year mapped
  (NII 2019-2025: 57.24/54.56/52.31/66.71/89.27/92.58/95.44 $B)          [A]
  (assets proxy earning assets -- noted, grade B proxy)
- NVDA: identical to examples/industry_demo (NVDA FY24/25 10-K segments)

Driver-tree structures (units kept consistent; residual absorbs the rest):
- SBUX   : revenue = stores x rev/store          (pen/share held at 1.0)
- META   : ad revenue = anchor2020 x imp-index x price-index (disclosed drivers)
- NFLX   : revenue = paid memberships x ARM (ARM = revenue / EOP memberships)
- JPM    : NII = total assets x net yield (weak-fit tree; proxy noted)
- NVDA   : as in industry_demo (base x pen x share, price implied)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from revenue_model import (  # noqa: E402
    Driver, Segment, BASE, PENETRATION, SHARE, PRICE, implied_driver,
)

TEST_YEAR = 2025            # touched once by run_track_b.py
HIST_END = 2024


def _panel_revenue(*tickers):
    import csv
    out = {}
    with open(os.path.join(HERE, "data", "revenue_panel.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["ticker"] in tickers:
                out[(r["ticker"], int(r["fy"]))] = float(r["revenue_usd"])
    return out


PANEL = _panel_revenue("SBUX", "NFLX")


def _hist(ticker, years):
    return {y: PANEL[(ticker, y)] / 1e6 for y in years}   # $M


# ---------------------------------------------------------------- SBUX
SBUX_STORES = {2019: 31256, 2020: 32638, 2021: 33833,
               2022: 35711, 2023: 38038, 2024: 40199}
SBUX_REV = _hist("SBUX", range(2019, HIST_END + 1))
SBUX_TEST = {TEST_YEAR: PANEL[("SBUX", TEST_YEAR)] / 1e6}


# ---------------------------------------------------------------- META
META_YOY = {   # year: (impressions YoY, price-per-ad YoY), from Q4 releases
    2021: (0.10, 0.24), 2022: (0.18, -0.16), 2023: (0.28, -0.09),
    2024: (0.11, 0.10), 2025: (0.12, 0.09),
}
META_AD_REV = {2020: 84169.0, 2021: 114916.0, 2022: 113642.0,
               2023: 131948.0, 2024: 160633.0}          # $M, Q4 releases
META_ANCHOR = META_AD_REV[2020]
_imp, _price = 1.0, 1.0
META_IMP, META_PRICE = {2020: 1.0}, {2020: 1.0}
for _y in range(2021, 2026):
    _imp *= 1 + META_YOY[_y][0]
    _price *= 1 + META_YOY[_y][1]
    META_IMP[_y] = _imp
    META_PRICE[_y] = _price
META_TEST = {TEST_YEAR: 196175.0}                        # Q4 FY25 release


# ---------------------------------------------------------------- NFLX
NFLX_MEMBERS = {2019: 167.09, 2020: 203.66, 2021: 221.84,
                2022: 230.75, 2023: 260.28, 2024: 301.63}   # M, EOP
# addressable-market denominator (C-grade estimate, ITU broadband households)
NFLX_HH = {2019: 1100.0, 2020: 1150.0, 2021: 1200.0,
           2022: 1230.0, 2023: 1265.0, 2024: 1300.0}        # M households
NFLX_PEN = {y: NFLX_MEMBERS[y] / NFLX_HH[y] for y in NFLX_MEMBERS}
NFLX_REV = _hist("NFLX", range(2019, HIST_END + 1))
NFLX_ARM = {y: NFLX_REV[y] / NFLX_MEMBERS[y] for y in NFLX_MEMBERS}
NFLX_TEST = {TEST_YEAR: PANEL[("NFLX", TEST_YEAR)] / 1e6}


# ---------------------------------------------------------------- JPM
JPM_NII = {2015: 43.51, 2016: 46.08, 2017: 50.10, 2018: 55.06, 2019: 57.24,
           2020: 54.56, 2021: 52.31, 2022: 66.71, 2023: 89.27,
           2024: 92.58}                                       # $B, XBRL
JPM_ASSETS = {2015: 2351.7, 2016: 2491.0, 2017: 2533.6, 2018: 2622.5,
              2019: 2686.5, 2020: 3384.8, 2021: 3743.6, 2022: 3665.7,
              2023: 3875.4, 2024: 4002.8}                     # $B, XBRL
JPM_YIELD = {y: JPM_NII[y] / JPM_ASSETS[y] for y in JPM_NII}  # derived [C]
JPM_TEST = {TEST_YEAR: 95.44}                                  # XBRL FY25


# ---------------------------------------------------------------- NVDA
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


# ---------------------------------------------------------------- builders
def _hold_structural(seg, test_years):
    """Hand-extend structural constants (held at 1.0) before the profile
    defaults fire -- the v0.16 soft-default rule: hand extrapolations
    always win. Avoids logistic L<1 crashes on non-fraction indices."""
    seg.penetration = seg.penetration.extrapolate_hold(test_years)
    seg.share = seg.share.extrapolate_hold(test_years)
    return seg


def _nvda_tree(name, drv, actual, industry, price_label, base_name):
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
    hist_years = [y for y in actual if y <= 2023]
    for y in hist_years:
        seg.price.values[y] = implied_driver(seg, y, actual[y], PRICE)
    return seg


def build_trees():
    """Returns {key: dict(segment, actual_hist, actual_test, profile, fit,
    test_years, note)}). NVDA trees keep the legacy demo split (FY24-25
    holdout) and are flagged as such."""
    trees = {}

    # SBUX -- retail_store (adapt)
    sbux_price = {y: SBUX_REV[y] / SBUX_STORES[y] for y in SBUX_STORES}
    trees["SBUX"] = dict(
        segment=_hold_structural(Segment("SBUX consolidated",
            base=Driver("global stores", BASE, dict(SBUX_STORES), level="A",
                        unit="stores", source="10-K/8-K FY19-FY24"),
            penetration=Driver("format mix", PENETRATION,
                               {y: 1.0 for y in SBUX_STORES}, level="C",
                               unit="fraction", source="held (structural)"),
            share=Driver("company-operated mix", SHARE,
                         {y: 1.0 for y in SBUX_STORES}, level="C",
                         unit="fraction", source="held (structural)"),
            price=Driver("revenue per store", PRICE, sbux_price, level="B",
                         unit="$M/store", source="derived: revenue/stores"),
            industry="retail_store"), [TEST_YEAR]),
        actual_hist=dict(SBUX_REV), actual_test=dict(SBUX_TEST),
        profile="retail_store", fit="adapt", test_years=[TEST_YEAR],
        note="units x AUV decomposition; revenue/stores derived [B]")

    # META -- advertising (adapt)
    # refinement (pre-test): impressions index lives on BASE as
    # "volume at 2020 pricing" ($M) -- the advertising profile's logistic
    # default for PENETRATION assumes a 0-1 fraction, which a raw index is not.
    meta_years = [y for y in META_IMP if y <= HIST_END]
    trees["META-ads"] = dict(
        segment=_hold_structural(Segment("META advertising",
            base=Driver("ad volume @2020 pricing", BASE,
                        {y: META_ANCHOR * META_IMP[y] for y in meta_years},
                        level="B", unit="$M",
                        source="derived: 2020 anchor x disclosed impressions index"),
            penetration=Driver("ad load", PENETRATION,
                               {y: 1.0 for y in meta_years}, level="C",
                               unit="fraction", source="held (structural)"),
            share=Driver("monetization mix", SHARE,
                         {y: 1.0 for y in meta_years}, level="C",
                         unit="fraction", source="held (structural)"),
            price=Driver("price per ad index", PRICE,
                         {y: META_PRICE[y] for y in meta_years}, level="B",
                         unit="index 2020=1", source="Q4 releases YoY chained"),
            industry="advertising"), [TEST_YEAR]),
        actual_hist=dict(META_AD_REV), actual_test=dict(META_TEST),
        profile="advertising", fit="adapt", test_years=[TEST_YEAR],
        note="revenue = anchor x disclosed impressions x disclosed price")

    # NFLX -- saas_subscription (adapt)
    # refinement (pre-test): the textbook subscription decomposition the
    # saas profile expects -- base = addressable households [C], penetration
    # = paid memberships per household (0.15 -> 0.23, inside logistic L=0.6),
    # price = ARM. A structural constant on PENETRATION is out of contract
    # for this profile (logistic L<1) -- recorded as an API finding.
    trees["NFLX"] = dict(
        segment=_hold_structural(Segment("NFLX streaming",
            base=Driver("broadband households", BASE, dict(NFLX_HH), level="C",
                        unit="M households", source="ITU-class estimates (C)"),
            penetration=Driver("paid penetration", PENETRATION,
                               dict(NFLX_PEN), level="B",
                               unit="fraction", source="derived: members/households"),
            share=Driver("profiles per household", SHARE,
                         {y: 1.0 for y in NFLX_MEMBERS}, level="C",
                         unit="ratio", source="held (structural)"),
            price=Driver("ARM", PRICE, dict(NFLX_ARM), level="B",
                         unit="$/member/yr", source="derived: revenue/EOP members"),
            industry="saas_subscription"), [TEST_YEAR]),
        actual_hist=dict(NFLX_REV), actual_test=dict(NFLX_TEST),
        profile="saas_subscription", fit="adapt", test_years=[TEST_YEAR],
        note="members x ARM; ARM derived on EOP convention [B]")

    # JPM -- financial_interest (weak)
    jpm_years = [y for y in JPM_NII if y <= HIST_END]
    trees["JPM-NII"] = dict(
        segment=_hold_structural(Segment("JPM net interest income",
            base=Driver("total assets (EA proxy)", BASE,
                        {y: JPM_ASSETS[y] for y in jpm_years}, level="B",
                        unit="$B", source="XBRL Assets (proxy for earning assets)"),
            penetration=Driver("earning-asset share", PENETRATION,
                               {y: 1.0 for y in jpm_years}, level="C",
                               unit="fraction", source="held (structural)"),
            share=Driver("funding mix", SHARE,
                         {y: 1.0 for y in jpm_years}, level="C",
                         unit="fraction", source="held (structural)"),
            price=Driver("net yield", PRICE,
                         {y: JPM_YIELD[y] for y in jpm_years}, level="C",
                         unit="fraction", source="derived: NII/assets"),
            industry="financial_interest"), [TEST_YEAR]),
        actual_hist={y: JPM_NII[y] for y in jpm_years},
        actual_test=dict(JPM_TEST),
        profile="financial_interest", fit="weak", test_years=[TEST_YEAR],
        note="balance-sheet-first tree; the weak-fit warning should fire")

    # NVDA -- legacy demo split (test FY2024+FY2025, predates experiment)
    trees["NVDA-Gaming"] = dict(
        segment=_nvda_tree("Gaming", GAMING_DRV, GAMING, "semiconductor",
                           "GeForce ASP", "PC shipments"),
        actual_hist={y: GAMING[y] for y in GAMING if y <= 2023},
        actual_test={2024: GAMING[2024], 2025: GAMING[2025]},
        profile="semiconductor", fit="strong", test_years=[2024, 2025],
        note="legacy industry_demo split (holdout FY24-25)")
    trees["NVDA-DC"] = dict(
        segment=_nvda_tree("Data Center", DC_DRV, DC, "regime_shift_tech",
                           "GPU ASP", "accelerator shipments"),
        actual_hist={y: DC[y] for y in DC if y <= 2023},
        actual_test={2024: DC[2024], 2025: DC[2025]},
        profile="regime_shift_tech", fit="weak", test_years=[2024, 2025],
        note="legacy industry_demo split; MC close-out expected")

    return trees


# Monte Carlo bands for weak-fit segments (honest wide ranges, stated ex ante)
MC_RANGES = {
    ("JPM-NII", 2025): {"total assets (EA proxy)": (3900.0, 4700.0),
                        "net yield": (0.018, 0.027)},
    ("NVDA-DC", 2024): {"accelerator shipments": (2.5, 6.0),
                        "share": (0.80, 0.95), "GPU ASP": (7000, 14000)},
    ("NVDA-DC", 2025): {"accelerator shipments": (3.0, 12.0),
                        "share": (0.78, 0.95), "GPU ASP": (9000, 22000)},
}


def smape(pred, actual):
    return 100.0 * sum(abs(p - a) / (abs(p) + abs(a))
                       for p, a in zip(pred, actual)) / len(pred)
