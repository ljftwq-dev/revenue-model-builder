"""Pull the Track-A revenue panel: FY2015-FY2025 annual revenue per universe
company via SEC XBRL (sec_adapter.fetch_revenues, disk-cached).

Filter: companies need >=8 annual points spanning at least FY2019-FY2024
(train + valid + test coverage); drops recent-IPO gaps and broken filers.

Run:  python pull_revenue.py     (~280 calls, SEC-cached after first run)
Out:  data/revenue_panel.csv  (ticker, symbol, profile, fit, fy, revenue_usd)
      data/pull_stats.txt
"""
import csv
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from datetime import datetime
from revenue_model import sec_adapter

DATA = os.path.join(HERE, "data")
YEARS = range(2015, 2026)          # FY2015..FY2025 (FY = calendar year of FY END)


def merged_annual_revenue(cik: int) -> dict:
    """Concept-switch-proof annual revenue: both revenue concepts merged per
    period (sec_adapter._revenue_periods_merged), true-annual periods only
    (340-390 days — annual-length XBRL periods come from 10-Ks), keyed by the
    calendar year of the period end (NVDA FY2025 ends 2025-01 -> 2025)."""
    facts = sec_adapter.fetch_company_facts(cik)
    gaap = facts.get("facts", {}).get("us-gaap", {})
    merged = sec_adapter._revenue_periods_merged(gaap)
    out = {}
    for (s, e), v in merged.items():
        if not s or not e:
            continue
        days = (datetime.fromisoformat(e) - datetime.fromisoformat(s)).days
        if not 340 <= days <= 390:
            continue
        fy = datetime.fromisoformat(e).year
        # first-listed concept wins per period; across periods keep the
        # latest-tagged value for a given fiscal year (restatements > older)
        out[fy] = v
    return out


def main():
    with open(os.path.join(DATA, "universe_2023.csv"), encoding="utf-8") as f:
        universe = list(csv.DictReader(f))
    print(f"universe: {len(universe)}")

    rows, dropped = [], []
    for i, u in enumerate(universe, 1):
        cik = int(u["cik"])
        try:
            rev = merged_annual_revenue(cik)
        except Exception as e:
            dropped.append((u["ticker"], f"fetch error: {e}"))
            continue
        pts = {y: v for y, v in rev.items() if y in YEARS and v and v > 0}
        yrs = sorted(pts)
        # need the spine of the experiment: enough train (<=2022), both valid
        # years (2023-24), and the test year (2025)
        if not (2019 in pts and 2022 in pts and 2023 in pts and 2024 in pts
                and 2025 in pts):
            dropped.append((u["ticker"], f"missing spine years; have {yrs}"))
            continue
        if len(yrs) < 8:
            dropped.append((u["ticker"], f"too few points {yrs}"))
            continue
        for y in yrs:
            rows.append(dict(ticker=u["ticker"], symbol=u["symbol"],
                             profile=u["profile"], fit=u["fit"],
                             fy=y, revenue_usd=pts[y]))
        if i % 40 == 0:
            print(f"  ..{i}/{len(universe)}  kept so far {sum(1 for r in rows if r['fy']==2015)}")
        time.sleep(0.15)   # SEC rate politeness (cache makes reruns instant)

    out = os.path.join(DATA, "revenue_panel.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "symbol", "profile", "fit",
                                          "fy", "revenue_usd"])
        w.writeheader()
        w.writerows(rows)

    kept = sorted({r["ticker"] for r in rows})
    with open(os.path.join(DATA, "pull_stats.txt"), "w", encoding="utf-8") as f:
        f.write(f"universe {len(universe)} | kept {len(kept)} | dropped {len(dropped)}\n")
        for t, why in dropped:
            f.write(f"DROP {t}: {why}\n")

    from collections import Counter
    prof = Counter(r["profile"] for r in rows if r["fy"] == 2025)
    fit = Counter(r["fit"] for r in rows if r["fy"] == 2025)
    print(f"kept {len(kept)} companies | dropped {len(dropped)}")
    print("by profile (FY2025):", dict(sorted(prof.items())))
    print("by fit (FY2025):", dict(fit))


if __name__ == "__main__":
    main()
