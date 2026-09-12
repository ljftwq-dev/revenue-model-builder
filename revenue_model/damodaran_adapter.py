"""Damodaran industry-data adapter (stdlib-only, zero new dependencies).

Keeps the ``Benchmark`` bands shipped in ``industry.py`` honest:

    fetch (free HTML export, disk-cached)  ->  parse (html.parser)
    ->  recompute profile-cluster quartile bands  ->  diff against the
    shipped literals.

Upstream updates once a year (January). The fetch is cached with a 30-day
TTL (not 365) so a January refresh is picked up within a month, and every
verify run reports the upstream vintage next to the vintage stamped on the
shipped bands — stale literals get caught even when the numbers happen to
be unchanged year over year.

Data grade B: hand-updated annual aggregates; per-industry values are
averages of firm-level CAGRs, so cluster bands describe cross-industry
spread, not firm-level dispersion (same caveat as the shipped bands).

CLI (no network in tests; verify fetches on first run)::

    python -m revenue_model.damodaran_adapter verify [--refresh]

Exit code 0 = shipped bands match upstream; 1 = drift or missing data
(regenerate the literals in ``industry.py`` and bump the vintage).
"""
import re
import sys
import urllib.request
from html.parser import HTMLParser
from typing import Dict, List, NamedTuple, Optional, Tuple

from .cache import cache_get_timed, cache_set_timed
from .industry import INDUSTRY_PROFILES

HISTGR_URL = ("https://pages.stern.nyu.edu/~adamodar/New_Home_Page/"
              "datafile/histgr.html")
_CACHE_KEY = "damodaran_histgr_html"
_CACHE_TTL_S = 30 * 24 * 3600   # annual upstream, monthly pickup

# Profile key -> Damodaran industry names. Single source of truth for the
# clusters behind industry.py's benchmarks (regime_shift_tech deliberately
# absent: no industry history anchors an AI inflection).
CLUSTERS: Dict[str, Tuple[str, ...]] = {
    "consumer_electronics": (
        "Electronics (Consumer & Office)", "Electronics (General)",
        "Computers/Peripherals", "Office Equipment & Services"),
    "semiconductor": ("Semiconductor", "Semiconductor Equip"),
    "saas_subscription": (
        "Software (System & Application)", "Software (Internet)",
        "Computer Services", "Information Services"),
    "advertising": (
        "Advertising", "Entertainment", "Publishing & Newspapers",
        "Broadcasting"),
    "retail_store": (
        "Retail (General)", "Retail (Special Lines)", "Retail (Automotive)",
        "Retail (Building Supply)", "Retail (Grocery and Food)",
        "Retail (Distributors)"),
    "telecom_subscriber": (
        "Telecom (Wireless)", "Telecom. Services", "Cable TV"),
    "industrial_capacity": (
        "Machinery", "Electrical Equipment", "Engineering/Construction",
        "Building Materials"),
    "financial_interest": ("Bank (Money Center)", "Banks (Regional)"),
    "commodity_cyclical": (
        "Metals & Mining", "Coal & Related Energy", "Oil/Gas (Integrated)",
        "Oil/Gas (Production and Exploration)", "Steel", "Precious Metals"),
}


class HistgrRow(NamedTuple):
    n_firms: int
    cagr_5y: Optional[float]     # revenue CAGR, last 5 years (fraction)
    exp_2y: Optional[float]      # expected revenue growth, next 2 years


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _to_fraction(s: str) -> Optional[float]:
    """'11.18%' -> 0.1118; 'NA' / '' / junk -> None."""
    s = s.replace(",", "").strip()
    if s in ("", "NA", "N/A", "-"):
        return None
    pct = s.endswith("%")
    if pct:
        s = s[:-1].strip()
    try:
        v = float(s)
    except ValueError:
        return None
    return v / 100.0 if pct else v


class _TableParser(HTMLParser):
    """Collect rows of <td> cell texts from an Excel-exported HTML table."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: List[List[str]] = []
        self._row: Optional[List[str]] = None
        self._cell: Optional[List[str]] = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self._cell is not None:
            self._row.append("".join(self._cell))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def parse_histgr(html: str) -> Dict[str, HistgrRow]:
    """Parse the histgr HTML export into ``{industry: HistgrRow}``."""
    p = _TableParser()
    p.feed(html)
    header_idx: Dict[str, int] = {}
    out: Dict[str, HistgrRow] = {}
    for row in p.rows:
        cells = [_norm(c) for c in row]
        if "Industry Name" in cells:
            header_idx = {c: i for i, c in enumerate(cells)}
            continue
        if not header_idx or not cells:
            continue
        name = cells[0]
        try:
            n_firms = int(cells[header_idx["Number of Firms"]])
        except (KeyError, ValueError, IndexError):
            continue
        cagr = _to_fraction(cells[header_idx["CAGR in Revenues- Last 5 years"]])
        exp = _to_fraction(cells[
            header_idx["Expected Growth in Revenues - Next 2 years"]])
        out[name] = HistgrRow(n_firms, cagr, exp)
    return out


def fetch_histgr(refresh: bool = False, timeout: float = 30.0
                 ) -> Tuple[str, Optional[str]]:
    """Return ``(html, vintage)`` from cache or the Damodaran site.

    ``vintage`` ("YYYY-MM") is scraped from the page's update stamp when
    possible; None means unknown (treat shipped-band vintage as authoritative
    until the next successful scrape).
    """
    hit, html = cache_get_timed(_CACHE_KEY, _CACHE_TTL_S, refresh=refresh)
    if not hit:
        req = urllib.request.Request(
            HISTGR_URL, headers={"User-Agent": "revenue-model-builder/0.18"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            html = r.read().decode("utf-8", errors="replace")
        cache_set_timed(_CACHE_KEY, html)
    months = ["January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November",
              "December"]
    mon = "|".join(months)
    m = re.search(rf"({mon})\s+\d{{1,2}},\s*(20\d\d)", html) \
        or re.search(rf"({mon})\s+(20\d\d)", html)
    vintage = None
    if m:
        vintage = f"{m.group(2)}-{months.index(m.group(1)) + 1:02d}"
    return html, vintage


def _quantile(vals: List[float], q: float) -> float:
    """Linear-interpolation quantile (matches numpy/pandas default)."""
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    frac = pos - lo
    return s[lo] * (1.0 - frac) + s[hi] * frac


def cluster_bands(parsed: Dict[str, HistgrRow]
                  ) -> Dict[str, Dict[str, Tuple[float, float, float, int]]]:
    """Recompute each profile cluster's quartile bands: ``{profile:
    {metric: (p25, p50, p75, n_firms)}}``."""
    out: Dict[str, Dict[str, Tuple[float, float, float, int]]] = {}
    for key, industries in CLUSTERS.items():
        cagrs, exps, n_firms = [], [], 0
        for ind in industries:
            row = parsed.get(ind)
            if row is None:
                continue
            n_firms += row.n_firms
            if row.cagr_5y is not None:
                cagrs.append(row.cagr_5y)
            if row.exp_2y is not None:
                exps.append(row.exp_2y)
        entry: Dict[str, Tuple[float, float, float, int]] = {}
        if cagrs:
            entry["revenue_cagr_5y"] = (
                _quantile(cagrs, 0.25), _quantile(cagrs, 0.50),
                _quantile(cagrs, 0.75), n_firms)
        if exps:
            entry["revenue_exp_growth_2y"] = (
                _quantile(exps, 0.25), _quantile(exps, 0.50),
                _quantile(exps, 0.75), n_firms)
        out[key] = entry
    return out


def diff_bands(profiles, fresh: Dict[str, Dict[str, Tuple[float, float,
                                                          float, int]]],
               clusters: Optional[Dict[str, Tuple[str, ...]]] = None
               ) -> List[str]:
    """Pure diff: shipped literals vs freshly recomputed bands. Returns a
    human-readable report (empty list = all match). ``clusters`` defaults to
    the module's CLUSTERS (injectable for tests)."""
    lines: List[str] = []
    tol = 5e-4   # literals are rounded to 4 decimals
    for key in (CLUSTERS if clusters is None else clusters):
        profile = profiles.get(key)
        if profile is None:
            lines.append(f"{key}: profile missing from registry")
            continue
        shipped = {b.metric: b for b in profile.benchmarks}
        fresh_metrics = fresh.get(key, {})
        for metric, (p25, p50, p75, _) in fresh_metrics.items():
            b = shipped.get(metric)
            if b is None:
                lines.append(f"{key}/{metric}: missing in shipped literals")
                continue
            drift = [f"{got:.4f}!={want:.4f}" for got, want, name in (
                (b.p25, p25, "p25"), (b.p50, p50, "p50"),
                (b.p75, p75, "p75")) if abs(got - want) > tol]
            if drift:
                lines.append(
                    f"{key}/{metric}: drift ({', '.join(drift)}); "
                    f"upstream now "
                    f"({p25:.4f}, {p50:.4f}, {p75:.4f})")
        for metric in shipped:
            if metric not in fresh_metrics:
                lines.append(f"{key}/{metric}: upstream has no value "
                             f"(industry renamed or dropped?)")
    return lines


def verify(refresh: bool = False) -> int:
    """Fetch (cached), recompute, diff against shipped literals. Returns a
    process exit code: 0 = match, 1 = drift/missing."""
    html, vintage = fetch_histgr(refresh=refresh)
    parsed = parse_histgr(html)
    missing = [i for inds in CLUSTERS.values() for i in inds if i not in parsed]
    if missing:
        print(f"MISSING upstream industries: {missing}")
        return 1
    lines = diff_bands(INDUSTRY_PROFILES, cluster_bands(parsed))
    shipped_vintages = {b.vintage for p in INDUSTRY_PROFILES.values()
                        for b in p.benchmarks}
    print(f"upstream vintage: {vintage or 'unknown'}; "
          f"shipped band vintage: {sorted(shipped_vintages)}")
    if not lines:
        print("OK — shipped Benchmark bands match upstream "
              f"({len(parsed)} industries parsed)")
        return 0
    for l in lines:
        print("DRIFT:", l)
    print("Regenerate the literals in industry.py and bump the vintage.")
    return 1


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    refresh = "--refresh" in argv
    return verify(refresh=refresh)


if __name__ == "__main__":
    raise SystemExit(main())
