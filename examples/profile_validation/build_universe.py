"""Build the Track-A universe: S&P 500 constituents as of 2023-12-31,
each mapped to a v0.16 mechanism profile via GICS sub-industry.

Anti-survivorship: the ticker list comes from the *historical* file
(sp_500_history.csv, last row <= 2023-12-31), never from the current list.
GICS sector/sub-industry comes from the current list where the company is
still a member; for companies that left the index 2024-2026 (and for
renamed tickers) we fall back to SEC SIC via companyfacts — with a small
hand SIC map. Every exclusion is recorded in the audit trail.

Run:  python build_universe.py   (after download_raw.py)
Out:  data/universe_2023.csv, data/universe_audit.txt
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from revenue_model import sec_adapter
from revenue_model.industry import INDUSTRY_PROFILES

RAW = os.path.join(HERE, "data_raw")
DATA = os.path.join(HERE, "data")
ANCHOR = "2023-12-31"

# known ticker renames 2022-2026 (old-at-anchor -> current symbol)
RENAMES = {
    "FB": "META", "FISV": "FI", "TWX": "WBD", "DISCA": "WBD",
    "DISCK": "WBD", "PKI": "RVTY", "SIVB": "SIVBQ", "GME": "GME",
}

# GICS sub-industry (2023-revision names, as they appear in sp500_current.csv)
# -> mechanism profile. CONSERVATIVE by design: sub-industries whose mechanism
# is genuinely absent from the 10 v0.16 profiles map to None and are excluded
# (health care, real estate, utilities, branded staples manufacturing, payment
# networks, exchanges, IT consulting, apparel brands...). Every None shows up
# in universe_audit.txt with its reason.
SUB_INDUSTRY_MAP = {
    # --- Information Technology ---
    "Semiconductors": "semiconductor",
    "Semiconductor Materials & Equipment": "semiconductor",
    "Technology Hardware, Storage & Peripherals": "consumer_electronics",
    "Electronic Equipment & Instruments": "consumer_electronics",
    "Communications Equipment": "consumer_electronics",
    "Electronic Manufacturing Services": "consumer_electronics",
    "Application Software": "saas_subscription",
    "Systems Software": "saas_subscription",
    "Interactive Home Entertainment": "saas_subscription",
    "IT Consulting & Other Services": None,             # people-days, not shipped
    "Internet Services & Infrastructure": None,         # mixed mechanisms
    "Technology Distributors": "retail_store",
    # --- Communication Services ---
    "Interactive Media & Services": "advertising",      # META, GOOGL
    "Movies & Entertainment": "saas_subscription",     # NFLX et al. streaming subs
    "Publishing": "saas_subscription",                  # NYT-class subscriptions
    "Integrated Telecommunication Services": "telecom_subscriber",
    "Wireless Telecommunication Services": "telecom_subscriber",
    # --- Consumer Discretionary ---
    "Hotels, Resorts & Cruise Lines": "retail_store",  # rooms x RevPAR = store x sales/store
    "Restaurants": "retail_store",
    "Casinos & Gaming": "retail_store",                # property network
    "Automotive Retail": "retail_store",
    "Other Specialty Retail": "retail_store",
    "Specialty Retail": "retail_store",
    "Department Stores": "retail_store",
    "Broadline Retail": "retail_store",
    "General Merchandise Stores": "retail_store",
    "Homefurnishing Retail": "retail_store",
    "Apparel Retail": "retail_store",
    "Computer & Electronics Retail": "retail_store",
    "Automobile Manufacturers": "industrial_capacity",
    "Automobile Components": "industrial_capacity",
    "Automotive Parts & Equipment": "industrial_capacity",
    "Homebuilding": "industrial_capacity",             # starts x ASP, backlog-driven
    "Household Durables": "consumer_electronics",
    "Consumer Electronics": "consumer_electronics",
    "Leisure Products": "consumer_electronics",
    "Apparel, Accessories & Luxury Goods": None,        # brand economics
    "Textiles, Apparel & Luxury Goods": None,
    "Travel Services": None,                           # take-rate on 3rd-party volume
    "Human Resource & Employment Services": None,
    "Diversified Consumer Services": None,
    "Specialized Consumer Services": None,
    "Interactive Media & Services ": "advertising",    # defensive trailing space
    # --- Consumer Staples ---
    "Consumer Staples Merchandise Retail": "retail_store",
    "Food Retail": "retail_store",
    "Drug Retail": "retail_store",
    "Packaged Foods & Meats": None,
    "Soft Drinks & Non-alcoholic Beverages": None,
    "Beverages": None,
    "Tobacco": None,
    "Personal Care Products": None,
    "Personal Products": None,
    "Household Products": None,
    # --- Financials ---
    "Regional Banks": "financial_interest",
    "Diversified Banks": "financial_interest",
    "Investment Banking & Brokerage": "financial_interest",
    "Asset Management & Custody Banks": "financial_interest",   # market-cycle weak bucket
    "Insurance Brokers": "financial_interest",
    "Life & Health Insurance": "financial_interest",
    "Property & Casualty Insurance": "financial_interest",
    "Multi-line Insurance": "financial_interest",
    "Reinsurance": "financial_interest",
    "Insurance": "financial_interest",
    "Multi-Sector Holdings": "financial_interest",
    "Consumer Finance": "financial_interest",          # lending = interest
    "Commercial & Residential Mortgage Finance": "financial_interest",
    "Financial Exchanges & Data": None,                # volume-fee + data subs mixed
    "Transaction & Payment Processing Services": None, # V/MA fee-on-volume
    "Diversified Support Services": None,
    "Specialized Finance": None,
    # --- Energy (whole sector per v0.16 alias table) ---
    "Integrated Oil & Gas": "commodity_cyclical",
    "Oil & Gas Exploration & Production": "commodity_cyclical",
    "Oil & Gas Equipment & Services": "commodity_cyclical",
    "Oil & Gas Refining & Marketing": "commodity_cyclical",
    "Oil & Gas Storage & Transportation": "commodity_cyclical",
    "Coal & Consumable Fuels": "commodity_cyclical",
    # --- Materials ---
    "Specialty Chemicals": "commodity_cyclical",
    "Commodity Chemicals": "commodity_cyclical",
    "Fertilizers & Agricultural Chemicals": "commodity_cyclical",
    "Industrial Gases": "industrial_capacity",         # take-or-pay volumes
    "Construction Materials": "commodity_cyclical",
    "Steel": "commodity_cyclical",
    "Metal & Glass & Plastic Containers": "industrial_capacity",
    "Metal, Glass & Plastic Containers": "industrial_capacity",
    "Paper & Plastic Packaging Products & Materials": "industrial_capacity",
    "Aluminum": "commodity_cyclical",
    "Copper": "commodity_cyclical",
    "Gold": "commodity_cyclical",
    "Precious Metals & Minerals": "commodity_cyclical",
    "Diversified Metals & Mining": "commodity_cyclical",
    "Nonmetallic Minerals": "commodity_cyclical",
    "Forest Products": "commodity_cyclical",
    "Paper Products": "commodity_cyclical",
    # --- Industrials ---
    "Aerospace & Defense": "industrial_capacity",
    "Industrial Machinery & Supplies & Components": "industrial_capacity",
    "Construction Machinery & Heavy Transportation Equipment": "industrial_capacity",
    "Electrical Components & Equipment": "industrial_capacity",
    "Heavy Electrical Equipment": "industrial_capacity",
    "Building Products": "industrial_capacity",
    "Construction & Engineering": "industrial_capacity",
    "Industrial Conglomerates": "industrial_capacity",
    "Passenger Airlines": "industrial_capacity",       # capacity x load factor
    "Rail Transportation": "industrial_capacity",
    "Air Freight & Logistics": "industrial_capacity",
    "Passenger Ground Transportation": "industrial_capacity",
    "Marine Transportation": "commodity_cyclical",     # freight rates = cycle
    "Trading Companies & Distributors": "retail_store",
    "Environmental & Facilities Services": None,       # service mix
    "Research & Consulting Services": None,
    "Commercial Printing Services": None,
    "Diversified Holding Companies": None,
}

# SEC SIC fallback for index leavers without a current-list row.
# (sic_prefix -> profile). Conservative; unmatched SICs -> excluded.
SIC_MAP = [
    (3480, "consumer_electronics"),  # ordnance/accessories - coarse
    (3570, "consumer_electronics"),  # computer hardware
    (3670, "semiconductor"),         # electronic components/semis
    (7372, "saas_subscription"),     # prepackaged software
    (6199, "financial_interest"),    # finance services
    (6020, "financial_interest"),    # commercial banks
    (6022, "financial_interest"),
    (6331, "financial_interest"),    # fire/casualty insurance
    (6311, "financial_interest"),    # life insurance
    (6351, "financial_interest"),
    (1311, "commodity_cyclical"),    # crude oil & gas extraction
    (2911, "commodity_cyclical"),    # petroleum refining
    (1000, "commodity_cyclical"),    # metal mining
    (1020, "commodity_cyclical"),
    (3330, "commodity_cyclical"),    # primary metals
    (3350, "commodity_cyclical"),
    (2800, "commodity_cyclical"),    # chemicals
    (2860, "commodity_cyclical"),
    (3550, "industrial_capacity"),   # special industry machinery
    (3560, "industrial_capacity"),
    (3710, "industrial_capacity"),   # highway vehicles
    (3720, "industrial_capacity"),   # aircraft
    (3800, "consumer_electronics"),  # instruments
    (4813, "telecom_subscriber"),    # telephone communications
    (4899, "telecom_subscriber"),
    (7389, None),                    # services-nec: too mixed (GOOGL-class) -> exclude
    (5900, "retail_store"),          # retail-nec
    (5411, "retail_store"),          # grocery
    (5812, "retail_store"),          # eating places
    (5912, "retail_store"),          # drug stores
]


def sic_to_profile(sic):
    if not sic:
        return None
    try:
        sic = int(sic)
    except (TypeError, ValueError):
        return None
    for prefix, prof in SIC_MAP:
        if prefix <= sic < prefix + 10:
            return prof
    return None


def _cik_via_edgar_search(ticker: str):
    """Fallback CIK lookup for retired tickers (acquired/renamed companies):
    EDGAR's browse-edgar keeps old-ticker -> CIK mappings. Atom output."""
    import re
    import urllib.request
    from revenue_model.sec_adapter import DEFAULT_UA
    url = (f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
           f"&ticker={ticker}&type=10-K&output=atom")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", errors="replace")
        m = re.search(r"<cik>\s*(\d+)", body)
        if not m:
            m = re.search(r"edgar/data/(\d+)", body, re.IGNORECASE)
        if not m:
            return None
        return int(m.group(1))
    except Exception:
        return None


def anchor_tickers():
    best_date, best = None, None
    with open(os.path.join(RAW, "sp500_history.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["date"] <= ANCHOR:
                if best_date is None or row["date"] >= best_date:
                    best_date, best = row["date"], row["tickers"]
    return best_date, [t for t in best.split(",") if t]


def current_table():
    with open(os.path.join(RAW, "sp500_current.csv"), encoding="utf-8") as f:
        return {r["symbol"]: r for r in csv.DictReader(f)}


def main():
    as_of, tickers = anchor_tickers()
    cur = current_table()
    print(f"anchor row: {as_of}  constituents: {len(tickers)}")

    rows, audit = [], []
    cur_hits = leaver_hits = excluded = 0
    for t in tickers:
        sym = RENAMES.get(t, t)
        rec = cur.get(sym)
        if rec is None and t in cur:
            rec = cur[t]
        if rec is not None:
            cur_hits += 1
            sub = rec["gics sub-industry"].strip()
            profile = SUB_INDUSTRY_MAP.get(sub, None) if sub else None
            sector = rec["gics sector"].strip()
            if profile is None:
                # sub-industry not in our map (or mapped None) -> excluded
                if sub in SUB_INDUSTRY_MAP:
                    excluded += 1
                    audit.append(f"EXCLUDED(staples/none) {t}: sub={sub!r} maps to None")
                else:
                    excluded += 1
                    audit.append(f"EXCLUDED(unmapped sub) {t}: sector={sector!r} sub={sub!r}")
                continue
            rows.append(dict(ticker=t, symbol=sym, cik=rec["cik"],
                             sector=sector, sub_industry=sub, profile=profile,
                             fit=INDUSTRY_PROFILES[profile].fit,
                             source="current_list"))
        else:
            # leaver: CIK via SEC (current tickers file, then EDGAR old-ticker
            # search for acquired/renamed names), then SIC via companyfacts
            try:
                cik, title = sec_adapter.fetch_cik(t)
            except Exception:
                cik = _cik_via_edgar_search(t)
                title = "leaver"
            if cik is None:
                excluded += 1
                audit.append(f"EXCLUDED(no cik) {t}: not in tickers file nor EDGAR search")
                continue
            sic = None
            try:
                sub = sec_adapter._get(
                    f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
                sic = sub.get("sic")
            except Exception:
                pass
            profile = sic_to_profile(sic)
            if profile is None:
                excluded += 1
                audit.append(f"EXCLUDED(leaver sic unmapped) {t}: cik={cik} sic={sic}")
                continue
            leaver_hits += 1
            rows.append(dict(ticker=t, symbol=t, cik=cik,
                             sector=f"sic:{sic}", sub_industry="", profile=profile,
                             fit=INDUSTRY_PROFILES[profile].fit,
                             source="sec_sic_fallback"))
            audit.append(f"LEAVER->profile {t}: cik={cik} sic={sic} -> {profile}")

    os.makedirs(DATA, exist_ok=True)
    out = os.path.join(DATA, "universe_2023.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(DATA, "universe_audit.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(audit))

    from collections import Counter
    by_profile = Counter(r["profile"] for r in rows)
    by_fit = Counter(r["fit"] for r in rows)
    print(f"included {len(rows)} (current-list {cur_hits_mapped(cur_hits, rows)}, "
          f"sic-fallback {leaver_hits}) | excluded {excluded}")
    print("by profile:", dict(sorted(by_profile.items())))
    print("by fit:", dict(by_fit))


def cur_hits_mapped(cur_hits, rows):
    return sum(1 for r in rows if r["source"] == "current_list")


if __name__ == "__main__":
    main()
