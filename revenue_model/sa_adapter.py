"""sa_adapter — stockanalysis.com segment-revenue adapter.

The US-market segment counterpart to ``sec_adapter``: ``sec_adapter`` fills
``total_revenue`` from SEC EDGAR's XBRL API but cannot get **segment** revenue
(segment tags vary per issuer in XBRL), so its segments ship as placeholder
templates. This adapter pulls the **reported segment revenue** (A-grade anchor,
per Principle 2 / history-first Principle 5) from stockanalysis.com's
"Revenue by Segment" table and feeds it into ``Segment.reported_revenue``.

Design choices (mirrors ``sec_adapter``):
- **``[scrape]`` extra** (playwright). Lazy-imported — never triggered by
  ``import revenue_model``; the core stays zero-dependency.
- **``table_extractor`` injectable** (``url -> list[{caption, headers, rows}]``).
  The default launches headless chromium via playwright; tests pass a fixture,
  so the suite needs no browser and no network.
- **Pure parser** (``_extract_segment_revenue``) is browser-free and unit-tested
  with a real NVDA table fixture.
- Data is million USD (matches ``sec_adapter``'s US anchor convention).
"""
import re
from typing import Callable, Dict, List, Optional, Tuple

from .driver import Driver, BASE, PENETRATION, SHARE, PRICE, LEVEL_C
from .segment import Segment
from .model import RevenueModel

SA_BASE = "https://stockanalysis.com/stocks"
DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")

# JS run inside the browser: extract every table's caption + headers + rows.
# (caption = nearest section/parent h2|h3 — stockanalysis groups tables that way)
_EXTRACT_JS = """ts => ts.map(t => {
    let cap = '';
    let sec = t.closest('section') || t.parentElement;
    if (sec) { let h = sec.querySelector('h2,h3'); if (h) cap = h.innerText.trim(); }
    return {
        caption: cap,
        headers: Array.from(t.querySelectorAll('thead th')).map(e => (e.innerText||'').trim()),
        rows: Array.from(t.querySelectorAll('tbody tr')).map(tr => Array.from(tr.querySelectorAll('td')).map(td => (td.innerText||'').trim()))
    };
})"""


def _parse_money(s: str) -> Optional[float]:
    """'$193,479' / '193,479' -> 193479.0; '' / '-' -> None."""
    if s is None:
        return None
    s = s.strip().replace("$", "").replace(",", "").replace("%", "")
    if not s or s in ("-", "—", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _extract_segment_revenue(
    tables: List[dict],
) -> Tuple[Dict[str, Dict[int, float]], Dict[int, float]]:
    """Pure parser: from a list of {caption, headers, rows} tables (as returned
    by the browser extractor), locate 'Revenue by Segment' and return
    ``(segment_revenue, total_revenue)`` where each is ``{year: million_USD}``.

    Raises ``ValueError`` if no segment table is found. Browser-free → unit-testable.
    """
    seg_table = None
    for t in tables:
        if "segment" in (t.get("caption") or "").lower():
            seg_table = t
            break
    if seg_table is None:
        raise ValueError("no 'Revenue by Segment' table on the page")

    headers = seg_table.get("headers", [])
    # Map column index -> fiscal year int. Headers look like 'FY 2026'.
    year_cols: Dict[int, int] = {}
    for i, h in enumerate(headers):
        m = re.search(r"(\d{4})", h)
        if m and ("FY" in h or "Fiscal" in h):
            year_cols[i] = int(m.group(1))

    segments: Dict[str, Dict[int, float]] = {}
    total: Dict[int, float] = {}
    for row in seg_table.get("rows", []):
        if not row:
            continue
        name = row[0].strip()
        vals: Dict[int, float] = {}
        for i, yr in year_cols.items():
            if i < len(row):
                v = _parse_money(row[i])
                if v is not None:
                    vals[yr] = v
        if not vals:
            continue
        if "total" in name.lower() or "revenue" == name.lower().strip():
            total = vals
        else:
            segments[name] = vals
    return segments, total


def _default_table_extractor(
    url: str, *, user_agent: str = DEFAULT_UA, timeout: int = 45000
) -> List[dict]:
    """Launch headless chromium, navigate, return rendered tables.

    Lazy-imports playwright (the ``[scrape]`` extra). Waits for the segment
    table to render before extracting — stockanalysis builds tables client-side.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=user_agent, locale="en-US",
            viewport={"width": 1366, "height": 900},
        )
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        try:
            page.wait_for_selector("table tbody tr", timeout=20000)
        except Exception:
            pass  # let the extractor return whatever is there
        tables = page.eval_on_selector_all("table", _EXTRACT_JS)
        browser.close()
    return tables


def fetch_segments_sa(
    ticker: str,
    *,
    table_extractor: Optional[Callable[[str], List[dict]]] = None,
    user_agent: str = DEFAULT_UA,
    timeout: int = 45000,
) -> Tuple[Dict[str, Dict[int, float]], Dict[int, float]]:
    """``ticker`` -> (segment_revenue, total_revenue) from stockanalysis.com.

    Each map is ``{year: million_USD}``. ``table_extractor`` is injectable
    (``url -> tables``); the default launches headless chromium via playwright.
    """
    if table_extractor is None:
        table_extractor = lambda url: _default_table_extractor(
            url, user_agent=user_agent, timeout=timeout)
    url = f"{SA_BASE}/{ticker.lower()}/financials/"
    tables = table_extractor(url)
    return _extract_segment_revenue(tables)


def _placeholder_drivers(seg_name: str, years: List[int]) -> Dict[str, Driver]:
    """Four C-grade placeholder drivers so the Segment validates (drivers are
    the forecast layer; reported_revenue carries the A-grade history)."""
    specs = [
        (BASE, "million units", "market base"),
        (PENETRATION, "fraction", "penetration"),
        (SHARE, "fraction", "market share"),
        (PRICE, "USD", "unit price"),
    ]
    out: Dict[str, Driver] = {}
    for kind, unit, label in specs:
        out[kind] = Driver(
            name=f"{seg_name} {label}", kind=kind,
            values={y: 0.0 for y in years}, level=LEVEL_C, unit=unit,
            source="[sa_adapter] placeholder - fill value",
        )
    return out


def build_model_from_sa(
    ticker: str,
    *,
    table_extractor: Optional[Callable[[str], List[dict]]] = None,
    years: Optional[List[int]] = None,
    user_agent: str = DEFAULT_UA,
    timeout: int = 45000,
) -> RevenueModel:
    """Build a ``RevenueModel`` for a US-listed company from stockanalysis.com.

    Each reported segment becomes a ``Segment`` whose ``reported_revenue`` is
    the A-grade anchor (history); drivers are C-grade placeholders (the forecast
    layer a human fills). ``total_revenue`` is the reported total. Needs the
    ``[scrape]`` extra (playwright) unless ``table_extractor`` is injected.
    """
    seg_rev, total_rev = fetch_segments_sa(
        ticker, table_extractor=table_extractor,
        user_agent=user_agent, timeout=timeout)
    if not seg_rev and not total_rev:
        raise ValueError(f"stockanalysis.com returned no segment data for {ticker!r}")

    all_years = set(total_rev)
    for v in seg_rev.values():
        all_years |= set(v)
    yrs = sorted(all_years)
    if years:
        yrs = [y for y in yrs if y in years] or yrs

    segments: List[Segment] = []
    for seg_name, rev_by_year in seg_rev.items():
        reported = {y: rev_by_year[y] for y in yrs if y in rev_by_year}
        d = _placeholder_drivers(seg_name, yrs)
        segments.append(Segment(
            name=seg_name, base=d[BASE], penetration=d[PENETRATION],
            share=d[SHARE], price=d[PRICE], reported_revenue=reported))

    total = {y: total_rev[y] for y in yrs if y in total_rev}
    return RevenueModel(company=ticker, segments=segments, total_revenue=total)
