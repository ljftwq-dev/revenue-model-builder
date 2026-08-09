"""NVIDIA (NVDA) driver demo — build Gaming vs Data Center revenue models.

The second real-company demo for ``revenue-model-builder``, and the first
*U.S. equity* one. NVIDIA is deliberately a two-faced case for the driver-tree
method:

- **Gaming** — mature, trend-extrapolatable market. Driver tree should track.
- **Data Center** — AI paradigm shift (FY2024+). Trend extrapolation should
  badly under-predict, which is *the point*: it shows where driver trees break
  and why scenario thinking takes over.

This script only does the **historical build** (FY2019-FY2025): reads segment
revenue + driver CSVs, back-solves price to tie each segment to its reported
revenue, and validates alignment. Hold-out backtesting lives in
``backtest_nvda.py``; charts in ``plot_results.py``.

Unit convention (kept consistent with the Luxun demo): all money is stored in
**$ millions** internally; ``base`` is in **millions of units**; therefore a
back-solved ``price`` value comes out in **$ per unit** ($M / M units = $/unit).

Run: ``python build_model.py``
"""
import os
import sys
import csv

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from revenue_model import (
    Driver, Segment, RevenueModel,
    BASE, PENETRATION, SHARE, PRICE, implied_driver,
)

DATA = os.path.join(HERE, "data")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_nvda():
    seg_rows = _read(os.path.join(DATA, "segments.csv"))
    g_drv = {int(r["year"]): r for r in _read(os.path.join(DATA, "drivers_gaming.csv"))}
    d_drv = {int(r["year"]): r for r in _read(os.path.join(DATA, "drivers_datacenter.csv"))}

    years = [int(r["fiscal_year"]) for r in seg_rows]
    total = {int(r["fiscal_year"]): float(r["total"]) for r in seg_rows}          # $M
    gaming_rev = {int(r["fiscal_year"]): float(r["gaming"]) for r in seg_rows}    # $M
    dc_rev = {int(r["fiscal_year"]): float(r["dc"]) for r in seg_rows}            # $M

    gaming = Segment(
        "Gaming",
        base=Driver("Global PC shipments", BASE,
                    {y: float(g_drv[y]["base"]) for y in years},
                    level="B", unit="M units", source="IDC (approx)"),
        penetration=Driver("dGPU attach rate", PENETRATION,
                           {y: float(g_drv[y]["penetration"]) for y in years},
                           level="C", unit="fraction", source="estimate"),
        share=Driver("NVIDIA dGPU share", SHARE,
                     {y: float(g_drv[y]["share"]) for y in years},
                     level="B", unit="fraction", source="JPR"),
        price=Driver("GeForce ASP", PRICE, {}, level="C",
                     unit="$/unit", source="implied"),
    )
    dc = Segment(
        "Data Center",
        base=Driver("Accelerator shipments", BASE,
                    {y: float(d_drv[y]["base"]) for y in years},
                    level="C", unit="M units", source="estimate"),
        penetration=Driver("AI penetration", PENETRATION,
                           {y: float(d_drv[y]["penetration"]) for y in years},
                           level="C", unit="fraction", source="structural"),
        share=Driver("NVIDIA AI share", SHARE,
                     {y: float(d_drv[y]["share"]) for y in years},
                     level="C", unit="fraction", source="estimate"),
        price=Driver("GPU ASP", PRICE, {}, level="C",
                     unit="$/unit", source="implied"),
    )

    # Back-solve price to tie each segment to its reported revenue (Principle 1).
    for y in years:
        gaming.price.values[y] = round(implied_driver(gaming, y, gaming_rev[y], PRICE), 1)
        dc.price.values[y] = round(implied_driver(dc, y, dc_rev[y], PRICE), 1)

    return RevenueModel("NVIDIA", [gaming, dc], total_revenue=dict(total)), years


def main():
    model, years = build_nvda()
    print("NVIDIA driver demo — historical build (FY2019-FY2025)")
    print("=" * 70)
    for seg in model.segments:
        print("\n[{}]".format(seg.name))
        for d in seg.drivers():
            print("  {:14s}[{}] {}".format(d.kind_label(), d.level, dict(d.values)))
        print("  revenue ($B):", end="")
        for yr in years:
            print("  FY{}={:.1f}".format(yr, seg.revenue(yr) / 1e3), end="")
        print()

    print("\n" + "=" * 70)
    print("validate_all — segment sum vs reported total (residual = 'other' segs):")
    for r in model.validate_all():
        print("  FY{}: gaming+dc={:.1f}B  total={:.1f}B  residual={:.1%}".format(
            r.year, r.segment_sum / 1e3, model.total_revenue[r.year] / 1e3, r.residual_ratio))

    print("\nback-solved ASPs (the data-honesty check):")
    for seg in model.segments:
        print("  {}: ".format(seg.name) + "  ".join(
            "FY{}=${:,.0f}".format(y, v) for y, v in sorted(seg.price.values.items())))


if __name__ == "__main__":
    main()
