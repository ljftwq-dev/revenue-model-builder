"""PLTR demo — auto_pipeline end-to-end on real public disclosure (v0.20a).

One call, two gates, one report. Data: PLTR FY2021-FY2024 10-K segment
disclosure (Government / Commercial revenue; commercial customer count;
ARPU derived). FY2025-26 are the forecast years — nothing is fetched; this
demo runs fully offline.

Teaching beats baked in:

1. Government tagged explicitly (semiconductor = pure trend family; a
   budget-cycle contracts approximation — the citation check then flags
   its +19%/yr ABOVE the semi band, which is exactly what a wrong-family
   proxy should look like).
2. Commercial tagged "auto": gate 1 adopts the battery's top candidate
   *loudly*. The interesting bit: the business prior says "SaaS", but the
   data fingerprint says subscriber-family (telecom — customers × ARPU is
   its native tree, mechanism-equivalent to SaaS at this stage), because
   the customer count is still accelerating (207 -> 382, +23%/yr).
3. Soft defaults in action: telecom's default net_growth knobs (a mature
   carrier's 5% gross / 3.5% churn) forecast Commercial at ~+1%/yr —
   visibly wrong for AIP-era PLTR. The demo then overrides the base by
   hand (analyst-first, always) and re-forecasts. The pipeline gives you a
   starting point and evidence, not a verdict.
4. Gate 2: both segments read ABOVE their bands — the pipeline refuses to
   ship silently and requires stories, which the demo files.

Run: ``python pltr_demo.py`` (writes PLTR_revenue_model.docx).
Education/research use only — see DISCLAIMER.md. Not investment advice.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from revenue_model import auto_pipeline   # noqa: E402

# FY2021-FY2024 10-K disclosure ($M). See data/sources.md.
GOV_REVENUE = {2021: 920.0, 2022: 1100.0, 2023: 1222.0, 2024: 1570.0}
COMM_CUSTOMERS = {2021: 207.0, 2022: 225.0, 2023: 280.0, 2024: 382.0}
COMM_ARPU = {2021: 3.00, 2022: 3.58, 2023: 3.58, 2024: 3.40}   # $M/customer
TOTAL = {2021: 1542.0, 2022: 1906.0, 2023: 2225.0, 2024: 2866.0}
YEARS = [2025, 2026]


def main():
    result = auto_pipeline(
        company="Palantir (education demo)",
        segments={
            "Government": {"base": dict(GOV_REVENUE)},
            "Commercial": {"base": dict(COMM_CUSTOMERS),
                           "price": dict(COMM_ARPU)},
        },
        total_revenue=dict(TOTAL),
        years=YEARS,
        tags={"Government": "semiconductor",      # explicit: trend-family proxy
              "Commercial": "auto"},               # gate 1: adopt + record
        stories={
            "Government":
                "budget-cycle expansion + new allied-government contracts "
                "compound above the semiconductor trend proxy's band — the "
                "proxy is for the tree shape, not the growth level.",
            "Commercial":
                "AIP-driven customer expansion (+23%/yr customers) compounds "
                "above the software cluster band; watch cohort ARPU as small-"
                "customer onboarding dilutes the average (2024 ARPU dipped).",
        },
        report=os.path.join(HERE, "PLTR_revenue_model.docx"),
    )

    print("[suggested] shortlists (top of each):")
    for name, sugg in result.suggestions.items():
        top = sugg[0] if sugg else None
        print(f"    {name:12s} -> {top.key if top else '(history too short)'}"
              + (f"  [{result.tags_used[name]}]" if name in result.tags_used else ""))
    print(f"[gate-1]    auto-adopted: {result.auto_tagged or '—'}"
          f"   pending: {result.gate1_pending or '—'}")
    print("[checked]")
    for name, warns in result.warnings.items():
        for w in warns:
            print(f"    {name:12s} {w[:118]}")
    print(f"[gate-2]    story required for: {result.gate2_pending or '— (all filed)'}")
    if result.model:
        print("[assembled] forecast ($M):")
        for seg in result.segments:
            print(f"    {seg.name:12s} "
                  + "  ".join(f"{y}: {seg.revenue(y):8.0f}" for y in YEARS))
        print(f"    report -> {result.report_path}")

    # -- soft-default override: telecom's mature-carrier knobs (~+1%/yr)
    #    are visibly wrong for AIP-era PLTR; the analyst overrides the base
    #    by hand and re-forecasts. Overrides always win (v0.16 rule).
    comm = next(s for s in result.segments if s.name == "Commercial")
    comm.base = comm.base.fit_trend(sorted(comm.base.values)).extrapolate(YEARS)
    print("\n[override]   Commercial base re-forecast by hand (linear trend "
          "on customers):")
    print("    "
          + "  ".join(f"{y}: {comm.revenue(y):8.0f}" for y in YEARS)
          + "   ($M, drivers product)")
    print("    -> defaults got you a defensible floor; the override is the "
          "analyst's call. That division of labor is the product.")


if __name__ == "__main__":
    main()
