"""q4cdn_adapter — parse company IR 'Revenue by Market Platform' PDFs (quarterly).

Many listed companies host IR supplements on Q4 Inc's CDN
(``s201.q4cdn.com/{company_id}/files/doc_financials/...``), including
"Quarterly Revenue Trend" PDFs that break revenue out by **market platform /
sub-market at quarterly granularity** — finer than the annual segment table
``sa_adapter`` pulls from stockanalysis.com.

Example (NVDA FY27 supplement, recast caliber):
    Data Center  = Hyperscale + ACIE
    TOTAL        = Data Center + Edge Computing
    9 quarters of history (Q1 FY25 .. Q1 FY27).

Design (mirrors ``sa_adapter``):
- **``[pdf]`` extra** (PyMuPDF). Lazy-imported; the core stays zero-dependency.
- **``pdf_text_getter`` injectable** (``url -> text``). Default downloads via
  urllib and extracts text with PyMuPDF; tests pass a text fixture, so the suite
  runs offline with no network and no PDF.
- **Pure parser** (``_extract_market_platform``) is PDF-free and unit-tested with
  a real NVDA text fixture.
- Returns **quarterly** data ``{line_item: {(fiscal_year, q): million_USD}}``;
  ``fiscal_year_rollup`` aggregates to annual for the annual RevenueModel layer.

Why no ``build_model_*`` here (unlike sa/sec/tushare/akshare adapters): the
market-platform caliber (Data Center / Edge / Hyperscale / ACIE) differs from
the business-segment caliber (Compute & Networking / Graphics) the other
adapters use. Mixing them in one RevenueModel would conflate two calibers.
This adapter is the **data layer**; how the sub-market detail feeds driver
modeling is an analyst decision (see ``examples/web_scraping/``).
"""
import re
import urllib.request
from typing import Callable, Dict, List, Tuple

Quarter = Tuple[int, str]  # (fiscal_year, "Q1".."Q4")

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")

_HEADER_PATTERNS = [
    re.compile(r"^fiscal", re.I),          # "Fiscal 2025" or "Fiscal  " (year may be on next line)
    re.compile(r"^\d{4}$"),                 # bare year line (e.g. "2027" split from "Fiscal")
    re.compile(r"in\s+millions", re.I),     # "($ in millions)" unit header
    re.compile(r"^q[1-4]$", re.I),
    re.compile(r"^=+\s*page|^page\s+\d+", re.I),
    re.compile(r"revenue\s+by\s+market", re.I),
    re.compile(r"^\w[\w\s]*\s+quarterly\s+revenue", re.I),
]


def _parse_money(s: str):
    """'$22,563' / '22,563' -> 22563.0; '' / '-' -> None."""
    if s is None:
        return None
    s = s.strip().replace("$", "").replace(",", "")
    if not s or s in ("-", "—", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _is_header(line: str) -> bool:
    return any(p.search(line) for p in _HEADER_PATTERNS)


def _is_note(line: str) -> bool:
    # Footnote lines like "Note: ...", "1 Data Center will include...",
    # "2 Edge Computing highlights...".
    return bool(re.match(r"^(note\s*:|\d+\s+[A-Z])", line, re.I))


def _extract_market_platform(
    text: str,
) -> Tuple[Dict[str, Dict[Quarter, float]], List[Quarter]]:
    """Pure parser: PDF text -> ({line_item: {(fy, q): million_USD}}, quarter_cols).

    Returns ``({}, [])`` if the quarter header row isn't recognized. PDF-free ->
    unit-testable with a captured text fixture.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # 1. Build the quarter column labels from "Fiscal YYYY" + "Q1..Q4" headers.
    # Match across newlines: PyMuPDF can emit "Fiscal  \n2027" on two lines.
    fiscal_years = [int(y) for y in re.findall(r"Fiscal\s+(\d{4})", text, re.I)]
    q_tokens = [l for l in lines if re.fullmatch(r"q[1-4]", l, re.I)]
    if not fiscal_years or not q_tokens:
        return {}, []

    quarters: List[Quarter] = []
    qi = 0
    for i, fy in enumerate(fiscal_years):
        # Each fiscal year contributes 4 quarters, except possibly the last
        # (the most recent year may have only 1-3 reported quarters).
        n = 4 if i < len(fiscal_years) - 1 else (len(q_tokens) - qi)
        for _ in range(max(0, n)):
            if qi < len(q_tokens):
                quarters.append((fy, q_tokens[qi].upper()))
                qi += 1
    n_cols = len(quarters)
    if n_cols == 0:
        return {}, []

    # 2. Walk lines; a line-item name (possibly multi-line) is followed by
    #    ``n_cols`` money values.
    items: List[Tuple[str, List[float]]] = []
    cur_name: List[str] = []
    cur_vals: List[float] = []
    for l in lines:
        if _is_header(l):
            continue
        if _is_note(l):
            if cur_name and len(cur_vals) == n_cols:
                items.append((" ".join(cur_name), cur_vals))
            break
        money = _parse_money(l)
        if money is not None:
            cur_vals.append(money)
            if len(cur_vals) == n_cols and cur_name:
                items.append((" ".join(cur_name), cur_vals))
                cur_name, cur_vals = [], []
        else:
            # Non-numeric, non-header, non-note -> part of a line-item name.
            cur_name.append(l)

    result: Dict[str, Dict[Quarter, float]] = {}
    for name, vals in items:
        result[_clean_name(name)] = {
            quarters[i]: vals[i] for i in range(min(n_cols, len(vals)))
        }
    return result, quarters


def _clean_name(name: str) -> str:
    """Normalize a line-item name: strip trailing footnote digits, collapse spaces."""
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\d+$", "", name).strip()  # "Data Center1" -> "Data Center"
    return name


def _default_pdf_text_getter(
    url: str, *, user_agent: str = DEFAULT_UA, timeout: int = 60
) -> str:
    """Download the PDF and extract text via PyMuPDF (lazy-imported, [pdf] extra)."""
    import fitz  # PyMuPDF
    import io

    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    doc = fitz.open(stream=io.BytesIO(data), filetype="pdf")
    return "\n".join(page.get_text() for page in doc)


def fetch_market_platform(
    url: str,
    *,
    pdf_text_getter: Callable[[str], str] = None,
    user_agent: str = DEFAULT_UA,
    timeout: int = 60,
    use_cache: bool = True,
    refresh: bool = False,
) -> Tuple[Dict[str, Dict[Quarter, float]], List[Quarter]]:
    """Download + parse a 'Revenue by Market Platform' PDF from a q4cdn URL.

    ``pdf_text_getter`` injectable (``url -> text``); default downloads via
    urllib and extracts with PyMuPDF. Returns
    ``({line_item: {(fy, q): million_USD}}, quarter_columns)``. When the default
    getter is used, the extracted PDF text is cached to disk
    (``RMB_CACHE_DIR``, default ``~/.cache/rmb/``); ``refresh=True`` re-downloads.
    """
    if pdf_text_getter is None and use_cache:
        from . import cache
        key = cache.cache_key("q4cdn", url)
        hit, text = cache.cache_get(key, refresh)
        if not hit:
            text = _default_pdf_text_getter(url, user_agent=user_agent, timeout=timeout)
            cache.cache_set(key, text)
        return _extract_market_platform(text)
    getter = pdf_text_getter or (lambda u: _default_pdf_text_getter(
        u, user_agent=user_agent, timeout=timeout))
    return _extract_market_platform(getter(url))


def fiscal_year_rollup(
    quarterly: Dict[Quarter, float],
) -> Dict[int, float]:
    """Aggregate a single line-item's quarterly series to fiscal-year totals.

    A fiscal year with all four quarters sums to the full year; a partial year
    (the most recent, e.g. only Q1 reported) sums what's available — callers
    should treat partial years as incomplete (the latest year is often partial).
    """
    annual: Dict[int, float] = {}
    for (fy, _q), v in quarterly.items():
        annual[fy] = annual.get(fy, 0.0) + v
    return annual
