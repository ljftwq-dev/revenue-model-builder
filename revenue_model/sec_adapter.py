"""sec_adapter — US-equity (SEC EDGAR) data source adapter.

Positioned as the project's "financial facts layer" (design Principle 1), the
US-market counterpart to ``tushare_adapter``: auto-fills ``total_revenue`` with
real historical anchors from SEC EDGAR's XBRL companyconcept API, and seeds
intelligent-driving segment drivers from a US-flavored industry template
(name/unit/source/source_url pre-filled, values 0.0 placeholders for a human).

Why SEC EDGAR (not Yahoo): Yahoo's financials endpoint is rate-limited /
heavily scraped, returning empty frames; SEC is the authoritative .gov source
with a stable JSON API and no rate-limit trouble (needs only a User-Agent).

Design choices:
- **Pure stdlib** (``urllib``). No SDK.
- **No token / key.** SEC EDGAR is fully public. A ``User-Agent`` identifying
  the caller is the only requirement (SEC policy); pass ``user_agent=`` or set
  the default. Never impersonate.
- **``http_get`` injectable** (``url, timeout -> dict``) for offline tests / CI.
"""
import json
import urllib.request
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from .driver import Driver, BASE, PENETRATION, SHARE, PRICE, LEVEL_C
from .segment import Segment
from .model import RevenueModel

SEC_API = "https://data.sec.gov"
SEC_WWW = "https://www.sec.gov"
DEFAULT_UA = "revenue-model-builder research contact@example.com"

# Two us-gaap revenue elements: try Revenues first, fall back to the ASC 606
# element many issuers use instead.
_REVENUE_CONCEPTS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
)

_TICKERS_KEY = "sec_tickers"  # cache key for the company_tickers.json mapping

# US-flavored intelligent-driving template (global / US data sources; price in
# USD so segment revenue stays in million-USD, matching the anchor's unit).
_INTEL_DRIVING_US = {
    "Intelligent Driving": {
        BASE: ("million units", "Global light-vehicle sales", "OICA / Marklines", ""),
        PENETRATION: ("fraction", "L2+ ADAS penetration rate", "S&P Global Mobility", ""),
        SHARE: ("fraction", "{company} ADAS market share", "estimate", ""),
        PRICE: ("USD", "ADAS system ASP", "estimate", ""),
    },
    "Intelligent Cockpit": {
        BASE: ("million units", "Global light-vehicle sales", "OICA / Marklines", ""),
        PENETRATION: ("fraction", "digital-cockpit penetration rate", "S&P Global Mobility", ""),
        SHARE: ("fraction", "{company} cockpit market share", "estimate", ""),
        PRICE: ("USD", "cockpit system ASP", "estimate", ""),
    },
}


def _get(url: str, *, http_get: Optional[Callable] = None,
         user_agent: str = DEFAULT_UA, timeout: int = 30) -> dict:
    if http_get is not None:
        return http_get(url, timeout)
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def fetch_cik(ticker: str, *, http_get: Optional[Callable] = None,
              user_agent: str = DEFAULT_UA, timeout: int = 30,
              use_cache: bool = True, refresh: bool = False) -> Tuple[int, str]:
    """ticker -> (CIK, company title) via SEC's company_tickers.json mapping.

    The full ticker mapping is cached (key ``sec_tickers``) so repeat calls
    don't re-download it; ``refresh=True`` forces a re-fetch. Injected
    ``http_get`` bypasses the cache.
    """
    from . import cache
    if use_cache and http_get is None:
        hit, tk = cache.cache_get(_TICKERS_KEY, refresh)
        if not hit:
            tk = _get(f"{SEC_WWW}/files/company_tickers.json",
                      http_get=http_get, user_agent=user_agent, timeout=timeout)
            cache.cache_set(_TICKERS_KEY, tk)
    else:
        tk = _get(f"{SEC_WWW}/files/company_tickers.json",
                  http_get=http_get, user_agent=user_agent, timeout=timeout)
    up = ticker.upper()
    for v in tk.values():
        if v.get("ticker", "").upper() == up:
            return v["cik_str"], v["title"]
    raise ValueError(f"ticker {ticker!r} not found in SEC company_tickers.json")


def _is_annual(unit: dict) -> bool:
    """A true annual figure: form 10-K AND the period spans ~a full year
    (filters out the Q4-only and 3-month rows that also carry form=10-K)."""
    if unit.get("form") != "10-K":
        return False
    start, end = unit.get("start"), unit.get("end")
    if not start or not end:
        return False
    try:
        days = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days
    except ValueError:
        return False
    return days >= 350


def fetch_revenues(cik: int, *, http_get: Optional[Callable] = None,
                   user_agent: str = DEFAULT_UA, timeout: int = 30,
                   use_cache: bool = True, refresh: bool = False) -> Dict[int, float]:
    """CIK -> {fiscal_year: revenue_in_USD} from SEC XBRL (annual 10-K only).

    Tries ``Revenues`` first, then the ASC 606 contract-revenue element; keeps
    whichever yields annual data. Returns ``{}`` if neither has annual rows.
    Cached by CIK (key ``sec_rev_{cik}``) when the default getter is used;
    ``refresh=True`` re-fetches. Injected ``http_get`` bypasses the cache.
    """
    from . import cache
    cache_enabled = use_cache and http_get is None
    key = cache.cache_key("sec_rev", cik)
    if cache_enabled:
        hit, cached = cache.cache_get(key, refresh)
        if hit:
            return {int(k): v for k, v in cached.items()}  # json keys are str
    cik10 = f"{cik:010d}"
    for concept in _REVENUE_CONCEPTS:
        try:
            d = _get(f"{SEC_API}/api/xbrl/companyconcept/CIK{cik10}/us-gaap/{concept}.json",
                     http_get=http_get, user_agent=user_agent, timeout=timeout)
        except Exception:
            continue
        annual: Dict[int, float] = {}
        for u in d.get("units", {}).get("USD", []):
            if _is_annual(u):
                fy = u.get("fy") or datetime.fromisoformat(u["end"]).year
                annual[int(fy)] = float(u["val"])
        if annual:
            if cache_enabled:
                cache.cache_set(key, annual)
            return annual
    return {}


def _intel_driving_us_segments(company: str, years: List[int]) -> List[Segment]:
    segments: List[Segment] = []
    for seg_name, tmpl in _INTEL_DRIVING_US.items():
        d: Dict[str, Driver] = {}
        for kind, (unit, name, source, url) in tmpl.items():
            d[kind] = Driver(
                name=name.format(company=company),
                kind=kind,
                values={y: 0.0 for y in years},
                level=LEVEL_C,
                unit=unit,
                source=f"[adapter] {source} - fill value",
                source_url=url,
            )
        segments.append(Segment(
            name=seg_name, base=d[BASE], penetration=d[PENETRATION],
            share=d[SHARE], price=d[PRICE]))
    return segments


def build_model_from_sec(
    ticker: str,
    *,
    http_get: Optional[Callable] = None,
    years: Optional[List[int]] = None,
    user_agent: str = DEFAULT_UA,
    timeout: int = 30,
    use_cache: bool = True,
    refresh: bool = False,
) -> RevenueModel:
    """Build a ``RevenueModel`` for a US-listed company from SEC EDGAR.

    ``total_revenue`` is auto-filled from SEC XBRL (annual 10-K revenue,
    converted to million USD). Segment drivers use a US intelligent-driving
    template (placeholders, tagged ``[adapter]``). No token/key needed; a
    descriptive ``user_agent`` is the only SEC requirement.
    """
    cik, name = fetch_cik(ticker, http_get=http_get, user_agent=user_agent,
                          timeout=timeout, use_cache=use_cache, refresh=refresh)
    rev = fetch_revenues(cik, http_get=http_get, user_agent=user_agent,
                         timeout=timeout, use_cache=use_cache, refresh=refresh)
    if not rev:
        raise ValueError(
            f"SEC EDGAR returned no annual revenue for {ticker!r} (CIK {cik}); "
            f"the issuer may not file us-gaap Revenues")
    yrs = sorted(rev)
    if years:
        yrs = [y for y in yrs if y in years] or yrs
    total = {y: rev[y] / 1e6 for y in yrs}  # USD -> million USD
    segments = _intel_driving_us_segments(name, yrs)
    return RevenueModel(company=name, segments=segments, total_revenue=total)


# ============================================================================
# Extended financial statements — full three statements + quarterly (v0.8)
#
# Augments ``fetch_revenues`` (single concept, annual-only) with complete
# multi-concept income / balance / cashflow at annual AND quarterly granularity,
# including single-quarter derivation for flow items. Powers richer driver
# calibration (R&D intensity, cash runway, margin trends) beyond the top line.
# ============================================================================

# statement -> [(display_name, [candidate us-gaap concepts], unit)]
# unit: "USD" monetary, "shares" counts, "USD/shares" per-share.
# Concept lists use the first element the issuer actually files.
_STATEMENT_CONCEPTS: Dict[str, List[Tuple[str, List[str], str]]] = {
    "income": [
        ("Revenue", ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"], "USD"),
        ("Cost of Revenue", ["CostOfRevenueAndOperatingExpense", "CostOfGoodsAndServicesSold", "CostOfRevenue"], "USD"),
        ("Gross Profit", ["GrossProfit"], "USD"),
        ("R&D Expense", ["ResearchAndDevelopmentExpense"], "USD"),
        ("SG&A Expense", ["GeneralAndAdministrativeExpense", "SellingGeneralAndAdministrativeExpense"], "USD"),
        ("Operating Income", ["OperatingIncomeLoss"], "USD"),
        ("Net Income", ["NetIncomeLoss"], "USD"),
        ("EPS Diluted", ["EarningsPerShareDiluted"], "USD/shares"),
    ],
    "balance": [
        ("Cash & Equivalents", ["CashAndCashEquivalentsAtCarryingValue"], "USD"),
        ("Total Current Assets", ["AssetsCurrent"], "USD"),
        ("Total Assets", ["Assets"], "USD"),
        ("Total Current Liabilities", ["LiabilitiesCurrent"], "USD"),
        ("Total Liabilities", ["Liabilities"], "USD"),
        ("Stockholders' Equity", ["StockholdersEquity"], "USD"),
        ("Shares Outstanding", ["CommonStockSharesOutstanding"], "shares"),
    ],
    "cashflow": [
        ("Net Income", ["NetIncomeLoss"], "USD"),
        ("Stock-based Comp", ["ShareBasedCompensation"], "USD"),
        ("Operating CF", ["NetCashProvidedByUsedInOperatingActivities"], "USD"),
        ("CapEx", ["PaymentsToAcquirePropertyPlantAndEquipment", "CapitalExpenditure"], "USD"),
        ("Investing CF", ["NetCashProvidedByUsedInInvestingActivities"], "USD"),
        ("Financing CF", ["NetCashProvidedByUsedInFinancingActivities"], "USD"),
    ],
}


def fetch_company_facts(cik: int, *, http_get: Optional[Callable] = None,
                        user_agent: str = DEFAULT_UA, timeout: int = 30,
                        use_cache: bool = True, refresh: bool = False) -> dict:
    """CIK -> full companyfacts JSON from SEC EDGAR's XBRL API.

    One call returns ALL us-gaap concepts for the issuer (every reported
    number across every form). Heavier than ``fetch_revenues`` (~1 MB for a
    mid-cap) but cache-backed, and the basis for ``fetch_statement`` which
    pulls many concepts in one round-trip instead of N. Cached by CIK
    (key ``sec_facts_{cik}``) when the default getter is used.
    """
    from . import cache
    cache_enabled = use_cache and http_get is None
    key = cache.cache_key("sec_facts", cik)
    if cache_enabled:
        hit, cached = cache.cache_get(key, refresh)
        if hit:
            return cached
    cik10 = f"{cik:010d}"
    facts = _get(f"{SEC_API}/api/xbrl/companyfacts/CIK{cik10}.json",
                 http_get=http_get, user_agent=user_agent, timeout=timeout)
    if cache_enabled:
        cache.cache_set(key, facts)
    return facts


def _dedupe_by_period(points: List[dict]) -> Dict[Tuple[str, str], dict]:
    """Deduplicate XBRL points by actual ``(start, end)`` period, latest-filed.

    The same fact often appears multiple times (re-filed as a comparative in a
    later 10-K, or tagged under a different fy/fp). The actual period — not the
    fy/fp label — is the reliable key. ``start`` may be ``None`` for instant
    items (balance sheet); those key on ``end`` alone (``start`` normalized to
    ``""``).
    """
    best: Dict[Tuple[str, str], dict] = {}
    for p in points:
        s = p.get("start") or ""
        e = p.get("end")
        if not e:
            continue
        k = (s, e)
        if k not in best or p.get("filed", "") > best[k].get("filed", ""):
            best[k] = p
    return best


def _period_from_end(end_str: str, fiscal_year_end_month: int = 12
                     ) -> Tuple[int, str]:
    """End date -> ``(fiscal_year, period_label)``. Calendar-year default.

    ``"2024-12-31"`` -> ``(2024, "FY")``; ``"2024-03-31"`` -> ``(2024, "Q1")``.
    Issuers with non-calendar fiscal years pass ``fiscal_year_end_month``.
    """
    d = datetime.fromisoformat(end_str)
    m = d.month
    if m == fiscal_year_end_month:
        return d.year, "FY"
    qmap = {3: "Q1", 6: "Q2", 9: "Q3"}
    return d.year, qmap.get(m, f"M{m}")


def fetch_statement(cik: int, statement: str = "income",
                    freq: str = "annual", *, single_quarter: bool = False,
                    http_get: Optional[Callable] = None,
                    user_agent: str = DEFAULT_UA, timeout: int = 30,
                    use_cache: bool = True, refresh: bool = False
                    ) -> Dict[Tuple[int, str], Dict[str, Optional[float]]]:
    """CIK + statement kind -> structured financial statement.

    Parameters
    ----------
    statement : {"income", "balance", "cashflow"}
    freq : {"annual", "quarterly", "both"}
    single_quarter : bool
        For flow items (income/cashflow) at quarterly freq, convert YTD
        cumulative values to single-quarter: ``Q2_single = Q2_YTD - Q1_YTD``,
        ``Q4_single = FY - Q3_YTD``. Balance-sheet (instant) items are never
        differenced. Per-share (EPS) and share counts are kept as-reported.

    Returns ``{(fiscal_year, period): {metric_name: value}}`` where period is
    ``"FY"`` or ``"Q1".."Q4"`` (single-quarter labels when adjusted). Monetary
    values in million USD; share counts in million; per-share as-is.
    """
    if statement not in _STATEMENT_CONCEPTS:
        raise ValueError(
            f"statement must be one of {list(_STATEMENT_CONCEPTS)}, got {statement!r}")
    facts = fetch_company_facts(cik, http_get=http_get, user_agent=user_agent,
                                timeout=timeout, use_cache=use_cache, refresh=refresh)
    gaap = facts.get("facts", {}).get("us-gaap", {})
    concepts_def = _STATEMENT_CONCEPTS[statement]
    is_flow = statement in ("income", "cashflow")
    metric_names = [c[0] for c in concepts_def]

    raw: Dict[str, Dict[Tuple[str, str], float]] = {}
    metric_unit: Dict[str, str] = {}
    all_periods: set = set()
    for display, candidates, unit in concepts_def:
        concept = next((c for c in candidates if c in gaap), None)
        if concept is None:
            continue
        pts = _dedupe_by_period(gaap[concept]["units"].get(unit, []))
        d = {}
        for (s, e), p in pts.items():
            v = p["val"]
            if unit in ("USD", "shares"):
                v = v / 1e6
            d[(s, e)] = v
            all_periods.add((s, e))
        raw[display] = d
        metric_unit[display] = unit

    pinfo = {p: _period_from_end(p[1]) for p in all_periods}
    q_order = {"Q1": 1, "Q2": 2, "Q3": 3}
    annual_p = sorted([p for p in all_periods if pinfo[p][1] == "FY"],
                      key=lambda p: pinfo[p][0])
    quarterly_p = sorted([p for p in all_periods if pinfo[p][1] in q_order],
                         key=lambda p: (pinfo[p][0], q_order[pinfo[p][1]]))

    # (fy, fp) -> period across ALL periods (incl. FY), so single-quarter Q4
    # derivation can find the annual figure even when freq="quarterly".
    all_by_fyfp = {}
    for p in all_periods:
        fy, fp = pinfo[p]
        all_by_fyfp[(fy, fp)] = p

    def build_table(periods, do_single_q):
        from collections import defaultdict
        years = defaultdict(dict)
        for p in periods:
            fy, fp = pinfo[p]
            years[fy][fp] = p
        data = {}
        for fy in sorted(years):
            yps = years[fy]
            if do_single_q and is_flow:
                fy_p = all_by_fyfp.get((fy, "FY"))
                conv = []
                if "Q1" in yps: conv.append(("Q1", yps["Q1"], None))
                if "Q2" in yps and "Q1" in yps: conv.append(("Q2", yps["Q2"], yps["Q1"]))
                if "Q3" in yps and "Q2" in yps: conv.append(("Q3", yps["Q3"], yps["Q2"]))
                if fy_p is not None and "Q3" in yps: conv.append(("Q4", fy_p, yps["Q3"]))
                if "FY" in yps: conv.append(("FY", yps["FY"], None))
                for fp, num_p, den_p in conv:
                    row = {}
                    for m in metric_names:
                        u = metric_unit.get(m, "USD")
                        nv = raw.get(m, {}).get(num_p)
                        if u != "USD" or den_p is None:
                            row[m] = nv
                        else:
                            dv = raw.get(m, {}).get(den_p)
                            row[m] = (nv - dv) if (nv is not None and dv is not None) else None
                    data[(fy, fp)] = row
            else:
                for fp, p in yps.items():
                    data[(fy, fp)] = {m: raw.get(m, {}).get(p) for m in metric_names}
        return data

    result = {}
    if freq in ("annual", "both"):
        result.update(build_table(annual_p, do_single_q=False))
    if freq in ("quarterly", "both"):
        result.update(build_table(quarterly_p, do_single_q=single_quarter))
    return result
