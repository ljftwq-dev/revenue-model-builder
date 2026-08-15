"""form8k_adapter — SEC 8-K filing events (Direction-3 news data layer).

8-Ks are the official event disclosure: every US-listed issuer files them,
each carries standardized ``items`` codes (1.01 material agreement, 2.01 M&A
completion, 5.02 officer changes, 2.02 earnings, ...), and the submissions
API serves the full recent history as one JSON document — no key, no
scraping. Compared with the press-release sources (``ir_adapter`` /
``q4cdn_adapter``), this is the *universal* event layer: it works for any
ticker, not just Q4-Inc-hosted IR sites, and the categorization is the
issuer's own regulatory claim rather than a headline keyword guess.

Validated on a six-company pool (NVDA / AMD / SDGR / REGN / GILD / GM,
409 events 2019-2026) during the news-impact case study; see
``docs/news-impact-validation.md`` for what the events do and do not
predict.

Design (mirrors ``sec_adapter`` / ``ir_adapter``):
- **Pure stdlib** (``urllib``). No SDK, no key.
- **``http_get`` injectable** (``url, timeout -> dict``) for offline tests / CI.
- **Cache** by CIK (one parsed event list per issuer); ``refresh=True``
  re-fetches. Injected ``http_get`` bypasses the cache.
- Only the "recent" filings window of the submissions API is read (~1,000
  filings, 2019+ for active issuers). Older history lives in per-year
  ``files`` blocks and is intentionally out of scope.
"""
import json
import urllib.request
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from . import cache, sec_adapter

DEFAULT_UA = sec_adapter.DEFAULT_UA
_SUBMISSIONS_API = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

# 8-K item code -> category, priority-ordered (first match wins). An 8-K may
# carry several items; the most *material* one defines the event. E.g. an
# earnings 8-K almost always also carries 9.01 (exhibits) — the event is
# "Earnings", not "exhibits". Order reflects materiality ranking, tuned on
# the six-company pool.
ITEM_CATEGORIES: List[Tuple[str, str]] = [
    ("2.01", "M&A"),                 # completion of acquisition/disposition
    ("1.01", "Agreement"),           # entry into material agreement
    ("1.02", "Agreement"),           # termination of material agreement
    ("2.03", "Financing/Oblig"),     # direct financial obligation
    ("3.02", "Equity Issuance"),     # unregistered sales of equity
    ("5.02", "Management"),          # departure/election of officers
    ("2.02", "Earnings"),            # results of operations
    ("7.01", "Other/RegFD"),         # Reg FD disclosure
    ("8.01", "Other/RegFD"),         # other events
]


def classify_items(items: str) -> str:
    """8-K ``items`` string -> one primary category, ``""`` if none maps.

    The SEC's ``items`` field is a comma-separated list like
    ``"2.02,9.01"``. The first code present in :data:`ITEM_CATEGORIES`
    (by materiality order, not string order) wins. Item 9.01 (exhibits) and
    other procedural codes map to nothing — an 8-K that is *only* exhibits
    is not a news event.
    """
    codes = [c.strip()[:4] for c in items.split(",") if c.strip()]
    for code, category in ITEM_CATEGORIES:
        if code in codes:
            return category
    return ""


def fetch_8k_events(ticker_or_cik: Union[str, int], *, since=None,
                    http_get: Optional[Callable] = None,
                    user_agent: str = DEFAULT_UA, timeout: int = 30,
                    use_cache: bool = True, refresh: bool = False
                    ) -> List[Dict[str, Any]]:
    """Ticker or CIK -> 8-K filing events, oldest-first.

    Parameters
    ----------
    ticker_or_cik : str | int
        Ticker (resolved via ``sec_adapter.fetch_cik``) or CIK directly.
    since : date/datetime/str, optional
        Keep only events on or after this date (inclusive). Accepts
        ``date``, ``datetime`` or ``"YYYY-MM-DD"``.

    Returns a list of dicts, each::

        {"date": datetime, "category": str, "items": str,
         "form": "8-K", "accession": str}

    where ``category`` comes from :func:`classify_items`. Filings whose
    items carry no mapped category (exhibits-only 8-Ks) are skipped — they
    are procedural, not news. Cached by CIK when the default getter is
    used; ``refresh=True`` re-fetches; injected ``http_get`` bypasses.
    """
    if isinstance(ticker_or_cik, int):
        cik = ticker_or_cik
    else:
        cik, _title = sec_adapter.fetch_cik(ticker_or_cik,
                                            http_get=http_get,
                                            user_agent=user_agent,
                                            timeout=timeout,
                                            use_cache=use_cache,
                                            refresh=refresh)
    cache_enabled = use_cache and http_get is None
    key = cache.cache_key("sec_submissions_8k", cik)
    if cache_enabled:
        hit, cached = cache.cache_get(key, refresh)
        if hit:
            events = [_from_cached(e) for e in cached]
        else:
            events = _parse_submissions(_fetch(cik, http_get=http_get,
                                               user_agent=user_agent,
                                               timeout=timeout))
            cache.cache_set(key, [_to_cached(e) for e in events])
    else:
        events = _parse_submissions(_fetch(cik, http_get=http_get,
                                           user_agent=user_agent,
                                           timeout=timeout))
    if since is not None:
        if isinstance(since, str):
            since = datetime.strptime(since, "%Y-%m-%d")
        elif not isinstance(since, datetime):
            since = datetime(since.year, since.month, since.day)
        events = [e for e in events if e["date"] >= since]
    return events


def _fetch(cik: int, *, http_get: Optional[Callable], user_agent: str,
           timeout: int) -> dict:
    if http_get is not None:
        return http_get(_SUBMISSIONS_API.format(cik=cik), timeout)
    req = urllib.request.Request(_SUBMISSIONS_API.format(cik=cik),
                                 headers={"User-Agent": user_agent,
                                          "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _parse_submissions(sub: dict) -> List[Dict[str, Any]]:
    recent = sub.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    items = recent.get("items", [])
    accessions = recent.get("accessionNumber", [])
    events: List[Dict[str, Any]] = []
    for form, fdate, it, acc in zip(forms, dates, items, accessions):
        if form != "8-K" or not fdate:
            continue
        category = classify_items(it or "")
        if not category:
            continue
        try:
            dt = datetime.strptime(fdate, "%Y-%m-%d")
        except ValueError:
            continue
        events.append({"date": dt, "category": category, "items": it or "",
                       "form": "8-K", "accession": acc or ""})
    events.sort(key=lambda e: e["date"])
    return events


def _to_cached(e: Dict[str, Any]) -> dict:
    return {**e, "date": e["date"].strftime("%Y-%m-%d %H:%M:%S")}


def _from_cached(d: dict) -> Dict[str, Any]:
    return {**d, "date": datetime.strptime(d["date"], "%Y-%m-%d %H:%M:%S")}
