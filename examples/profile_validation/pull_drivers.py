"""One-shot data verification pull for Track B driver histories.

Fixes the JPM XBRL year mapping (companyconcept `fy` is the filing's fiscal
year, not the fact period -- use `end` dates on ~365-day durations instead),
then verifies Netflix paid-membership counts and Starbucks store counts
straight from 10-K documents (SEC EDGAR, cached by sec_adapter).

Run:  python pull_drivers.py
Out:  data/drivers_verified.json  (+ console log)
"""
import json
import os
import re
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from revenue_model.sec_adapter import _get, DEFAULT_UA  # noqa: E402

DATA = os.path.join(HERE, "data")


def annual_concept(cik, tag, unit_hint=None):
    """10-K facts with ~annual durations, keyed by end-year (calendar FY)."""
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{tag}.json"
    d = _get(url)
    out = {}
    for unit, vals in d["units"].items():
        if unit_hint and unit != unit_hint:
            continue
        for v in vals:
            if v.get("form") != "10-K":
                continue
            s = date.fromisoformat(v["start"])
            e = date.fromisoformat(v["end"])
            days = (e - s).days
            if not (340 <= days <= 380):
                continue
            # annual period ending in Jan-Feb counts as prior calendar year
            fy = e.year - 1 if e.month <= 2 else e.year
            val = v["val"]
            if fy not in out or v.get("filed", "") > out[fy][1]:
                out[fy] = (val, v.get("filed", ""))
    return {k: v[0] for k, v in sorted(out.items())}


def instant_concept(cik, tag):
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{tag}.json"
    d = _get(url)
    out = {}
    for unit, vals in d["units"].items():
        for v in vals:
            if v.get("form") != "10-K":
                continue
            e = date.fromisoformat(v["end"])
            fy = e.year - 1 if e.month <= 2 else e.year
            val = v["val"]
            if fy not in out or v.get("filed", "") > out[fy][1]:
                out[fy] = (val, v.get("filed", ""))
    return {k: v[0] for k, v in sorted(out.items())}


def latest_10k_docs(cik, n=4):
    sub = _get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    recent = sub["filings"]["recent"]
    docs = []
    for form, acc, doc, fdate in zip(recent["form"], recent["accessionNumber"],
                                     recent["primaryDocument"],
                                     recent["filingDate"]):
        if form == "10-K":
            acc_nodash = acc.replace("-", "")
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{doc}"
            docs.append((fdate, url))
        if len(docs) >= n:
            break
    return docs


def grep(url, patterns):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read().decode("utf-8", errors="replace")
    text = re.sub(r"<[^>]+>", " ", body)
    text = re.sub(r"&#8209;|&#8211;", "-", text)
    res = {}
    for name, pat in patterns.items():
        m = re.findall(pat, text)
        res[name] = m[:12]
    return res


def main():
    out = {}

    # --- JPM: NII + total assets, end-year mapped ---
    nii = annual_concept(19617, "InterestIncomeExpenseNet")
    assets = instant_concept(19617, "Assets")
    out["jpm"] = {"nii_reported_b": {str(k): round(v / 1e9, 2) for k, v in nii.items() if k >= 2015},
                  "total_assets_b": {str(k): round(v / 1e9, 1) for k, v in assets.items() if k >= 2015}}
    print("JPM NII (reported, $B):", out["jpm"]["nii_reported_b"])
    print("JPM assets ($B):", out["jpm"]["total_assets_b"])

    # --- NFLX: paid memberships from 10-K text ---
    nflx_hits = {}
    for fdate, url in latest_10k_docs(1065280, n=3):
        print(f"NFLX 10-K filed {fdate}: {url}")
        try:
            res = grep(url, {"memberships": r"([\d,]{3,4}\.?\d*)\s*million\s*paid memberships"})
        except Exception as ex:
            print("  fetch failed:", ex)
            continue
        nflx_hits[fdate] = res["memberships"]
        print("  mentions:", res["memberships"][:6])
    out["nflx_10k_membership_mentions"] = nflx_hits

    # --- SBUX: store counts from FY2021 10-K (covers FY19-21) ---
    sbux_hits = {}
    for fdate, url in latest_10k_docs(829224, n=6):
        print(f"SBUX 10-K filed {fdate}: {url}")
        try:
            res = grep(url, {"stores": r"(3[0-9],\d{3})"})
        except Exception as ex:
            print("  fetch failed:", ex)
            continue
        sbux_hits[fdate] = sorted(set(res["stores"]))
        print("  store counts found:", sbux_hits[fdate][:10])
        if len(sbux_hits) >= 3:
            break
    out["sbux_10k_store_mentions"] = sbux_hits

    path = os.path.join(DATA, "drivers_verified.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print("->", path)


if __name__ == "__main__":
    main()
