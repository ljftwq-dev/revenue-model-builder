"""akshare_adapter — HK-equity (港交所) data source adapter.

The HK-market counterpart to ``tushare_adapter`` / ``sec_adapter``: auto-fills
``total_revenue`` from AKShare's ``stock_financial_hk_report_em`` (东方财富 港股
利润表), and seeds intelligent-driving segment drivers from an industry template
(values 0.0 placeholders). HK-listed intelligent-driving names are sparse, so
this is mainly exercised on names like 比亚迪股份 (01211.HK); the template is
a starting point the analyst adjusts.

Design choices:
- **AKShare is a lazy, optional import.** The core package stays importable
  without it; install the ``[data]`` extra (``akshare``) to use this adapter.
- **``ak`` is injectable** (any module exposing ``stock_financial_hk_report_em``)
  so the test suite / CI need neither akshare nor network — the engine's
  established injection pattern (cf. ``http_get``, ``llm=``).
- HK income statements call revenue "营业额"; rows are filtered to that line.
"""
from typing import Dict, List, Optional

from .driver import Driver, BASE, PENETRATION, SHARE, PRICE, LEVEL_C
from .segment import Segment
from .model import RevenueModel

# HK revenue line items across issuers (most use 营业额; some use 收益/收入).
_REVENUE_ITEMS = ("营业额", "收益", "收入", "营业总收入")

# HK intelligent-driving template (CAAM / GG-II sources still apply for
# China-exposed HK names like BYD; price kept in HKD to match the anchor).
_INTEL_DRIVING_HK = {
    "智能驾驶": {
        BASE: ("百万辆", "中国乘用车销量", "CAAM", "http://www.caam.org.cn"),
        PENETRATION: ("小数", "L2+ 辅助驾驶前装渗透率", "高工产业研究院", "http://www.gg-ii.com"),
        SHARE: ("小数", "{company} 智驾市占率", "估算", ""),
        PRICE: ("HKD", "智驾方案单价 (ASP)", "估算", ""),
    },
    "智能座舱": {
        BASE: ("百万辆", "中国乘用车销量", "CAAM", "http://www.caam.org.cn"),
        PENETRATION: ("小数", "智能座舱前装渗透率", "高工产业研究院", "http://www.gg-ii.com"),
        SHARE: ("小数", "{company} 座舱市占率", "估算", ""),
        PRICE: ("HKD", "座舱单价 (ASP)", "估算", ""),
    },
}


def _ak(ak=None):
    """Return the akshare module (lazy import) or the injected fake."""
    if ak is None:
        import akshare as ak  # optional extra [data]
    return ak


def fetch_revenues_hk(code: str, *, ak=None, timeout: int = 30) -> Dict[int, float]:
    """HK annual revenue ("营业额") history -> {year: revenue_in_original_currency}.

    ``code`` is the bare HK code, e.g. ``"00700"``. Returns ``{}`` if no revenue
    line is found.
    """
    a = _ak(ak)
    df = a.stock_financial_hk_report_em(stock=code, symbol="利润表", indicator="年度")
    rev = df[df["STD_ITEM_NAME"].isin(_REVENUE_ITEMS)]
    out: Dict[int, float] = {}
    for _, row in rev.iterrows():
        amt = row.get("AMOUNT")
        if amt is None or amt != amt:        # NaN check (NaN != NaN)
            continue
        year = int(str(row["REPORT_DATE"])[:4])
        out[year] = float(amt)
    return out


def fetch_company_name_hk(code: str, *, ak=None, timeout: int = 30) -> str:
    """Company short name from the report; falls back to ``code``."""
    try:
        a = _ak(ak)
        df = a.stock_financial_hk_report_em(stock=code, symbol="利润表", indicator="年度")
        names = df["SECURITY_NAME_ABBR"].dropna().unique()
        if len(names):
            return str(names[0])
    except Exception:
        pass
    return code


def _intel_driving_hk_segments(company: str, years: List[int]) -> List[Segment]:
    segments: List[Segment] = []
    for seg_name, tmpl in _INTEL_DRIVING_HK.items():
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


def build_model_from_akshare(
    code: str,
    *,
    ak=None,
    years: Optional[List[int]] = None,
    timeout: int = 30,
) -> RevenueModel:
    """Build a ``RevenueModel`` for an HK-listed company via AKShare.

    ``total_revenue`` is auto-filled from the 港股利润表 "营业额" line (converted
    to million, original currency). Segment drivers use the HK intelligent-driving
    template (placeholders). Install the ``[data]`` extra (akshare) to use.
    """
    rev = fetch_revenues_hk(code, ak=ak, timeout=timeout)
    if not rev:
        raise ValueError(
            f"AKShare 港股利润表无 {code!r} 营业额数据；检查代码或 akshare 版本")
    name = fetch_company_name_hk(code, ak=ak, timeout=timeout)
    yrs = sorted(rev)
    if years:
        yrs = [y for y in yrs if y in years] or yrs
    total = {y: rev[y] / 1e6 for y in yrs}   # 元 -> 百万
    segments = _intel_driving_hk_segments(name, yrs)
    return RevenueModel(company=name, segments=segments, total_revenue=total)
