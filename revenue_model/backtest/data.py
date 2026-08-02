"""Annual-revenue loader: akshare (同花顺按年度) -> cached CSV.

Lazy-imports akshare (which brings pandas). The metrics / methods / rolling
core works on any series you supply, so this module is optional — import it
explicitly only when you want real A-share data.

A successful fetch is cached as CSV, so runs are reproducible offline and do
not hammer the data source on every backtest.

Unit convention: returns revenue in **million yuan** to match the engine.
akshare gives 元; we divide by 1e6.

Data grade: B — 同花顺 annual abstract, drawn from audited annual filings.
Tag the series accordingly when it feeds a model.
"""

import csv
import os
from typing import List, Optional, Tuple


def _parse_amount_yuan(s) -> Optional[float]:
    """Parse a 同花顺 amount string like '3.51亿' / '2786.51万' / '3323.44亿'
    into 元 (yuan). Returns None for missing/blank cells."""
    if s is None:
        return None
    text = str(s).strip()
    if text in ("", "-", "--", "False", "None", "nan", "NaN"):
        return None
    try:
        if text.endswith("万亿"):
            return float(text[:-2]) * 1e12
        if text.endswith("亿"):
            return float(text[:-1]) * 1e8
        if text.endswith("万"):
            return float(text[:-1]) * 1e4
        return float(text)
    except ValueError:
        return None


def _parse_year(s) -> Optional[int]:
    """Extract a 4-digit year from a 同花顺 报告期 cell ('2007' or '2007-12-31')."""
    if s is None:
        return None
    text = str(s).strip()
    if not text:
        return None
    head = text.split("-")[0].split(".")[0].split("/")[0]
    try:
        y = int(head[:4])
    except ValueError:
        return None
    return y if 1990 <= y <= 2100 else None


def _cache_path(cache_dir: str, symbol: str) -> str:
    return os.path.join(os.path.abspath(cache_dir), f"{symbol}.csv")


def _write_cache(path: str, years: List[int], values: List[float]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "revenue_million"])
        for y, v in zip(years, values):
            w.writerow([y, f"{v:.4f}"])


def _read_cache(path: str) -> Tuple[List[int], List[float]]:
    years, values = [], []
    with open(path, "r", encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if not row or row[0] == "year":
                continue
            try:
                years.append(int(row[0]))
                values.append(float(row[1]))
            except (ValueError, IndexError):
                continue
    return years, values


def load_annual_revenue(
    symbol: str,
    *,
    name: str = "",
    cache_dir: str,
    refresh: bool = False,
) -> Tuple[List[int], List[float], str]:
    """Load a company's annual total-revenue series (million yuan).

    Parameters
    ----------
    symbol
        6-digit A-share code, e.g. ``"002475"`` (Luxun). The 同花顺 annual
        abstract endpoint keys on this.
    name
        Display name (e.g. ``"立讯精密"``); defaults to ``symbol`` if empty.
    cache_dir
        Directory for the CSV cache (``{cache_dir}/{symbol}.csv``). Created if
        missing. A cached file is reused unless ``refresh=True``.
    refresh
        Force a fresh akshare fetch and overwrite the cache.

    Returns ``(years, values_million, name)``. Years ascending, each with a
    positive revenue; gaps in the source are dropped.
    """
    cache = _cache_path(cache_dir, symbol)
    if os.path.exists(cache) and not refresh:
        yrs, vals = _read_cache(cache)
        if yrs:
            return yrs, vals, name or symbol

    try:
        import akshare as ak
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "backtest.data requires akshare. Install it with:  pip install akshare"
        ) from exc

    df = ak.stock_financial_abstract_ths(symbol=str(symbol), indicator="按年度")
    rev_col = None
    for cand in ("营业总收入", "营业收入"):
        if cand in df.columns:
            rev_col = cand
            break
    if rev_col is None:
        raise KeyError(
            f"no 营业总收入/营业收入 column in 同花顺 abstract for {symbol}; "
            f"columns={list(df.columns)[:10]}")

    pairs = []
    for period, raw in zip(df["报告期"], df[rev_col]):
        y = _parse_year(period)
        yuan = _parse_amount_yuan(raw)
        if y is None or yuan is None or yuan <= 0:
            continue
        pairs.append((y, yuan / 1e6))
    pairs.sort(key=lambda t: t[0])

    if not pairs:
        raise ValueError(f"no usable annual-revenue rows for {symbol}")
    years = [p[0] for p in pairs]
    values = [p[1] for p in pairs]
    _write_cache(cache, years, values)
    return years, values, name or symbol
