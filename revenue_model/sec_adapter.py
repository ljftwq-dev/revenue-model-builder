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
