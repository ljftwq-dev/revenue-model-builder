"""ir_adapter — Investor Relations press releases from Q4 Inc-hosted IR sites.

Many US-listed companies (NVDA, Schrödinger, Apple, ...) host their IR websites
on Q4 Inc's platform. Press releases are served by a uniform JSON API::

    https://ir.{company}.com/feed/PressRelease.svc/GetPressReleaseList
        ?LanguageId=1&bodyType=0&pressReleaseDateFilter=3
        &categoryId=00000000-0000-0000-0000-000000000000
        &pageSize=-1&pageNumber=0&tagList=&includeTags=true
        &year=-1&excludeSelection=1

One call returns ALL press releases for the issuer (full history). This is the
data layer for Direction-3 (news-impact modeling): structured, free, no key,
no anti-scraping (validated on SDGR: 259 releases, 2017-2026, one round-trip).

Design (mirrors ``sec_adapter`` / ``q4cdn_adapter``):
- **Pure stdlib** (``urllib``). No SDK.
- **No token / key.** The Q4 press API is fully public.
- **``http_get`` injectable** (``url, timeout -> dict``) for offline tests / CI.
- **Cache** by IR domain (one JSON blob per company).
- **Classification helper** maps headlines to event categories (Earnings /
  Partnership / Pipeline / ...) — the first step of news -> driver mapping.

Why no ``build_model_*`` here (like ``q4cdn_adapter``): press releases are a
different caliber from financial statements / driver trees. This adapter is
the **data layer**; how press signals feed driver adjustment is a research
decision (see rmb-路线图与待办.docx 方向三 case study).
"""
import json
import urllib.request
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")

# Q4 Inc press-release list endpoint — constant across all Q4-hosted IR sites.
# pageSize=-1 + year=-1 -> full history in one call.
_Q4_PRESS_PATH = ("/feed/PressRelease.svc/GetPressReleaseList"
                  "?LanguageId=1&bodyType=0&pressReleaseDateFilter=3"
                  "&categoryId=00000000-0000-0000-0000-000000000000"
                  "&pageSize=-1&pageNumber=0&tagList=&includeTags=true"
                  "&year=-1&excludeSelection=1")

# Known Q4 Inc-hosted IR domains. Extend as more companies are validated.
# Callers may always pass ``ir_domain=`` directly for unmapped tickers.
_TICKER_IR_DOMAINS: Dict[str, str] = {
    "SDGR": "ir.schrodinger.com",
    "NVDA": "investor.nvidia.com",
}


def _get(url: str, *, http_get: Optional[Callable] = None,
         user_agent: str = DEFAULT_UA, timeout: int = 30) -> dict:
    if http_get is not None:
        return http_get(url, timeout)
    req = urllib.request.Request(url, headers={"User-Agent": user_agent,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def resolve_ir_domain(ticker: str) -> Optional[str]:
    """Ticker -> Q4 Inc IR domain (best-effort static lookup).

    Returns the IR domain (e.g. ``"ir.schrodinger.com"``) if known, else
    ``None`` — callers then pass ``ir_domain=`` to ``fetch_press_releases``
    directly. Future versions may auto-discover via web search.
    """
    return _TICKER_IR_DOMAINS.get(ticker.upper())


def fetch_press_releases(ir_domain: str, *, http_get: Optional[Callable] = None,
                         user_agent: str = DEFAULT_UA, timeout: int = 30,
                         use_cache: bool = True, refresh: bool = False
                         ) -> List[Dict[str, Any]]:
    """IR domain -> list of press-release dicts (full history, newest-first).

    Parameters
    ----------
    ir_domain : str
        e.g. ``"ir.schrodinger.com"`` (no scheme). Resolve via
        ``resolve_ir_domain(ticker)`` or pass directly for unmapped tickers.

    Returns a list of dicts, each::

        {"date": datetime, "headline": str, "detail_url": str,
         "pdf_url": str, "id": int}

    Cached by IR domain (key ``ir_press_{domain}``) when the default getter is
    used; ``refresh=True`` re-fetches. Injected ``http_get`` bypasses cache.
    """
    from . import cache
    cache_enabled = use_cache and http_get is None
    key = cache.cache_key("ir_press", ir_domain)
    if cache_enabled:
        hit, cached = cache.cache_get(key, refresh)
        if hit:
            return [_from_cached(p) for p in cached]
    url = f"https://{ir_domain}{_Q4_PRESS_PATH}"
    data = _get(url, http_get=http_get, user_agent=user_agent, timeout=timeout)
    items = data.get("GetPressReleaseListResult", []) or []
    parsed: List[Dict[str, Any]] = []
    for it in items:
        raw_date = it.get("PressReleaseDate", "")
        try:
            dt = datetime.strptime(raw_date, "%m/%d/%Y %H:%M:%S")
        except (ValueError, TypeError):
            continue
        headline = (it.get("Headline") or "").strip()
        if not headline:
            continue
        detail = it.get("LinkToDetailPage", "") or ""
        if detail and not detail.startswith("http"):
            detail = f"https://{ir_domain}" + detail
        parsed.append({
            "date": dt,
            "headline": headline,
            "detail_url": detail,
            "pdf_url": it.get("DocumentPath", "") or "",
            "id": it.get("PressReleaseId"),
        })
    parsed.sort(key=lambda p: p["date"], reverse=True)
    if cache_enabled:
        cache.cache_set(key, [_to_cached(p) for p in parsed])
    return parsed


def _to_cached(p: Dict[str, Any]) -> dict:
    """Serialize a press dict for JSON cache (datetime -> str)."""
    return {**p, "date": p["date"].strftime("%m/%d/%Y %H:%M:%S")}


def _from_cached(d: dict) -> Dict[str, Any]:
    """Deserialize a press dict from JSON cache (str -> datetime)."""
    return {**d, "date": datetime.strptime(d["date"], "%m/%d/%Y %H:%M:%S")}


# ---- classification: headline -> event category ----------------------------
# Lightweight keyword rules. First step of news -> driver mapping (Direction-3).
# Not NLP — just enough to bucket releases for cross-company pooling. Tuned
# for biotech / software / general US-listed issuers; extend ``_CAT_RULES``
# for other sectors.
_CAT_RULES: List[tuple] = [
    ("Earnings", ["financial results", "reports fourth quarter",
                  "reports first quarter", "reports second quarter",
                  "reports third quarter", "reports full-year",
                  "reports full year", "quarterly results"]),
    ("Earnings Notice", ["to announce", "schedules", "will report"]),
    ("Partnership/M&A", ["collaboration", "agreement", "partnership", "license",
                         "strategic", "acquire", "acquisition", "merger",
                         "joint venture"]),
    ("Pipeline/Product", ["introduces", "launches", "phase", "clinical", "fda",
                          "trial", "drug", "candidate", "molecule", "platform",
                          "software", "product", "clearance", "approval",
                          "presents data", "positive data"]),
    ("Financing", ["offering", "pricing of", "closing of", "underwritten",
                   "common stock", "convertible notes"]),
    ("Inducement Grants", ["inducement grant"]),
    ("IR Event", ["investor conference", "to participate", "present at",
                  "fireside"]),
    ("Management Change", ["appoints", "names ", "to join", "resigns",
                           "retire"]),
    ("Governance", ["annual meeting", "proxy"]),
]


def classify(headline: str) -> str:
    """Headline -> event category (first matching rule wins, else ``"Other"``).

    Ordered keyword rules; tuned for biotech / tech US-listed issuers. Extend
    ``_CAT_RULES`` for other sectors. Intentionally simple — the SDGR case
    study showed title adjectives ('Strong') can mislead, so this buckets by
    event *type*, not sentiment.
    """
    t = headline.lower()
    for cat, keywords in _CAT_RULES:
        if any(k in t for k in keywords):
            return cat
    return "Other"


def fetch_press_for_ticker(ticker: str, *, http_get: Optional[Callable] = None,
                           user_agent: str = DEFAULT_UA, timeout: int = 30,
                           use_cache: bool = True, refresh: bool = False,
                           with_category: bool = True) -> List[Dict[str, Any]]:
    """Ticker -> press releases (convenience wrapper).

    Resolves the IR domain via ``resolve_ir_domain``; raises ``ValueError`` if
    the ticker isn't in the known-domain map — call ``fetch_press_releases``
    with ``ir_domain=`` directly for unmapped tickers. When
    ``with_category=True`` (default), each release gets a ``"category"`` key
    from :func:`classify`.
    """
    domain = resolve_ir_domain(ticker)
    if domain is None:
        raise ValueError(
            f"no known Q4 Inc IR domain for ticker {ticker!r}; "
            f"call fetch_press_releases(ir_domain=...) directly")
    releases = fetch_press_releases(domain, http_get=http_get,
                                    user_agent=user_agent, timeout=timeout,
                                    use_cache=use_cache, refresh=refresh)
    if with_category:
        for r in releases:
            r["category"] = classify(r["headline"])
    return releases
