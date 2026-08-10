"""tushare_adapter — A-share (NEV / intelligent-driving) data source adapter.

Positioned as the project's "financial facts layer" (design Principle 1):
auto-fills ``total_revenue`` with real historical anchors from tushare's
income statement, and seeds intelligent-driving segment drivers with an
industry template (name/unit/source/source_url pre-filled, values left as 0.0
placeholders for a human) — the same semi-automated boundary as ``extractor``:
the machine gives structure + the anchor, the analyst fills the C-grade driver
values.

Design choices:
- **Pure stdlib** (``urllib``). No tushare SDK dependency; the call is a plain
  HTTP POST to ``https://api.tushare.pro``.
- **Token is a runtime argument, never hardcoded.** Load it via your secrets
  manager (e.g. ``secrets_loader.get_tushare_token()``) and pass it in.
- **``http_get`` is injectable** (``http_get(url, payload, timeout) -> dict``)
  so the test suite and CI need no network and no token.
"""
import json
import urllib.request
from typing import Callable, Dict, List, Optional

from .driver import Driver, BASE, PENETRATION, SHARE, PRICE, LEVEL_C
from .segment import Segment
from .model import RevenueModel

TUSHARE_URL = "https://api.tushare.pro"

# Intelligent-driving industry driver template (NEV-focused A-shares).
# Pre-fills each driver's name/unit/source/source_url with industry-realistic
# values; values stay 0.0 placeholders. Mirrors the NovaTech demo's structure
# and the CAAM / GG-II (高工产业研究院) public data sources.
_INTEL_DRIVING_TEMPLATE = {
    "智能驾驶": {
        BASE: ("百万辆", "中国乘用车销量", "CAAM", "http://www.caam.org.cn"),
        PENETRATION: ("小数", "L2+ 辅助驾驶前装渗透率", "高工产业研究院", "http://www.gg-ii.com"),
        SHARE: ("小数", "{company} 智驾市占率", "估算", ""),
        PRICE: ("元", "智驾方案单价 (ASP)", "估算", ""),
    },
    "智能座舱": {
        BASE: ("百万辆", "中国乘用车销量", "CAAM", "http://www.caam.org.cn"),
        PENETRATION: ("小数", "智能座舱前装渗透率", "高工产业研究院", "http://www.gg-ii.com"),
        SHARE: ("小数", "{company} 座舱市占率", "估算", ""),
        PRICE: ("元", "座舱单价 (ASP)", "估算", ""),
    },
}


def _post(body: dict, *, http_get: Optional[Callable] = None, timeout: int = 40) -> dict:
    """POST to the tushare endpoint. ``http_get`` injectable for offline tests."""
    if http_get is not None:
        return http_get(TUSHARE_URL, body, timeout)
    req = urllib.request.Request(
        TUSHARE_URL, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _call(api_name: str, token: str, params: dict, fields: str = "",
          *, http_get: Optional[Callable] = None, timeout: int = 40) -> dict:
    body = {"api_name": api_name, "token": token, "params": params}
    if fields:
        body["fields"] = fields
    return _post(body, http_get=http_get, timeout=timeout)


def fetch_income(ts_code: str, token: str, *, http_get: Optional[Callable] = None,
                 timeout: int = 40) -> Dict[int, float]:
    """Annual-report revenue from tushare ``income`` (end_date = YYYY1231 only).

    Returns ``{year: revenue_in_yuan}`` for each fiscal year on record.
    """
    r = _call("income", token, {"ts_code": ts_code}, fields="end_date,revenue",
              http_get=http_get, timeout=timeout)
    data = r.get("data", {})
    fields = data.get("fields", [])
    items = data.get("items", [])
    di = fields.index("end_date") if "end_date" in fields else 0
    ri = fields.index("revenue") if "revenue" in fields else 1
    out: Dict[int, float] = {}
    for it in items:
        ed = str(it[di])
        if ed.endswith("1231") and it[ri]:
            out[int(ed[:4])] = float(it[ri])
    return out


def fetch_company_name(ts_code: str, token: str, *, http_get: Optional[Callable] = None,
                       timeout: int = 40) -> str:
    """Company name from tushare ``stock_basic``; falls back to ts_code on error
    (the endpoint occasionally fails with a transient SSL EOF — non-fatal)."""
    try:
        r = _call("stock_basic", token, {"ts_code": ts_code}, fields="ts_code,name",
                  http_get=http_get, timeout=timeout)
        items = r.get("data", {}).get("items", [])
        if items:
            fields = r.get("data", {}).get("fields", [])
            ni = fields.index("name") if "name" in fields else 1
            if items[0][ni]:
                return items[0][ni]
    except Exception:
        pass
    return ts_code


def _intel_driving_segments(company: str, years: List[int]) -> List[Segment]:
    """Build intelligent-driving segment drivers from the industry template:
    name/unit/source/source_url pre-filled, values 0.0 placeholders."""
    segments: List[Segment] = []
    for seg_name, tmpl in _INTEL_DRIVING_TEMPLATE.items():
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


def build_model_from_tushare(
    ts_code: str,
    *,
    token: str,
    years: Optional[List[int]] = None,
    http_get: Optional[Callable] = None,
    timeout: int = 40,
) -> RevenueModel:
    """Build a ``RevenueModel`` for an A-share intelligent-driving company.

    - ``total_revenue`` is auto-filled from tushare ``income`` (real historical
      anchors, converted to million yuan — the engine's working unit).
    - Segment drivers use the intelligent-driving industry template
      (name/unit/source/source_url pre-filled; values are 0.0 placeholders to
      be filled by a human, tagged ``[adapter] ... fill value``).

    Load ``token`` via your secrets manager (never hardcode). Pass ``http_get``
    (``url, payload, timeout -> dict``) for offline testing / CI.
    """
    income = fetch_income(ts_code, token, http_get=http_get, timeout=timeout)
    if not income:
        raise ValueError(
            f"tushare income returned no annual data for {ts_code!r}; "
            f"check the code and the token's permissions")
    name = fetch_company_name(ts_code, token, http_get=http_get, timeout=timeout)
    yrs = sorted(income)
    if years:
        kept = [y for y in yrs if y in years]
        yrs = kept or yrs
    total = {y: income[y] / 1e6 for y in yrs}  # yuan -> million yuan
    segments = _intel_driving_segments(name, yrs)
    return RevenueModel(company=name, segments=segments, total_revenue=total)
