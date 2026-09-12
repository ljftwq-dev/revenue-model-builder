"""Industry profiles — the industry-fit matrix, executable.

The flagship methodology doc (``docs/industry-fit-analysis.md``) proves that a
driver tree's accuracy is a property of the *industry's growth mechanism*, not
of the formula: same engine, same company — NVDA Gaming 1.0% sMAPE (trend
market) vs Data Center 60% (AI regime shift). This module encodes that matrix
as forecasting *behavior*:

- ``IndustryProfile`` — one industry's fit class (strong / adapt / weak),
  per-driver-kind default extrapolation methods, and industry-specific
  validation checks.
- :func:`resolve_industry` — mechanism key ("saas_subscription"), GICS alias
  ("information technology", "40"), or Chinese alias ("软件") → profile.
- :func:`forecast_segment` — extend a Segment's drivers using the profile's
  analyst-first defaults (soft defaults: call the Driver extrapolation methods
  yourself to override).
- :func:`check_segment` / :func:`profile_warnings` — industry checks and the
  weak-fit redirect ("point forecast is a category error here — use scenarios").

Design rule (v0.16): profiles are **soft defaults + loud warnings**, never
hard blocks. A researcher must always be able to run the naive trend on a
weak-fit industry *and be told exactly why that number cannot be trusted* —
that honesty loop is the library's differentiator, and the NVDA demo depends
on it.

All profiles are pure data; adding one is a dict entry, not a subclass.
"""

from dataclasses import dataclass, field
import math
from typing import Callable, Dict, List, Optional, Tuple

from .driver import BASE, PENETRATION, SHARE, PRICE, Driver, DriverKind
from .segment import Segment

__all__ = [
    "ExtrapolationSpec", "IndustryProfile", "INDUSTRY_PROFILES",
    "resolve_industry", "list_profiles", "forecast_segment",
    "check_segment", "profile_warnings", "segment_warnings",
]


# ---------------------------------------------------------------------------
# Spec & profile containers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExtrapolationSpec:
    """Default extrapolation recipe for one driver kind in one industry.

    ``method`` ∈ {incremental, logistic, trend, mean_revert, erosion, growth,
    hold}; ``params`` are passed to the corresponding ``Driver.extrapolate_*``
    method. String params are resolved relative to the driver's history:
    ``"last"`` → last known year; ``"1.3*last"`` → 1.3 × last known value.
    """
    method: str
    params: Dict = field(default_factory=dict)


@dataclass(frozen=True)
class Benchmark:
    """One sourced industry benchmark band for a growth-related metric.

    ``p25``/``p50``/``p75`` are the quartile band of the metric across the
    profile's reference industry cluster (the exact industries are listed in
    ``note``), in annualized fraction units (0.08 = 8%/yr). Per-industry
    values behind the band are cluster *averages* of firm-level CAGRs, so the
    band describes cross-industry spread, not firm-level dispersion.

    ``grade`` follows the package's A/B/C data grading: Damodaran's dataset is
    hand-updated once a year from filings (grade B), not live exchange data.
    """
    metric: str          # e.g. "revenue_cagr_5y", "revenue_exp_growth_2y"
    p25: float
    p50: float
    p75: float
    unit: str = "fraction"
    source: str = ""     # citation with dataset, scope, and update date
    vintage: str = ""    # data-as-of, "YYYY-MM"
    grade: str = "B"
    note: str = ""       # reference industry cluster + coverage


_DM_HISTGR = ("Damodaran US industry data — histgr (historical & expected "
              "revenue growth), January 2026 update (trailing data through "
              "2025Q3). https://pages.stern.nyu.edu/~adamodar/New_Home_Page/"
              "datacurrent.html")


def _dm_band(metric: str, p25: float, p50: float, p75: float,
             note: str) -> Benchmark:
    """Shorthand for a Damodaran histgr quartile band (grade B)."""
    return Benchmark(metric=metric, p25=p25, p50=p50, p75=p75,
                     source=_DM_HISTGR, vintage="2026-01", grade="B",
                     note=note)


@dataclass(frozen=True)
class IndustryProfile:
    """One industry's forecasting defaults, checks, and fit verdict."""
    key: str
    label_en: str
    label_zh: str
    fit: str                       # "strong" | "adapt" | "weak"
    fit_note: str                  # why — grounded in the fit analysis
    defaults: Dict[DriverKind, ExtrapolationSpec]
    checks: Tuple[str, ...] = ()   # names into _CHECKS registry
    advice: str = ""               # what to do instead when fit == weak
    # sourced benchmark bands for citation-based checks (v0.18); empty means
    # "no external benchmark" and the profile's checks stay heuristic
    benchmarks: Tuple[Benchmark, ...] = ()

    def fit_label(self, lang: str = "en") -> str:
        labels = {"strong": {"en": "strong fit", "zh": "强契合"},
                  "adapt": {"en": "adapt fit", "zh": "改造后契合"},
                  "weak": {"en": "weak fit", "zh": "不契合"}}
        return labels[self.fit][lang]


# ---------------------------------------------------------------------------
# History-analysis helpers (pure stdlib, used by checks)
# ---------------------------------------------------------------------------

def _recent_cagr(values: Dict[int, float], window: int = 3) -> Optional[float]:
    """CAGR over the last ``window`` known years, or None if degenerate."""
    yrs = sorted(values)[-window:]
    if len(yrs) < 2 or yrs[0] == yrs[-1]:
        return None
    v0, v1 = values[yrs[0]], values[yrs[-1]]
    if v0 <= 0:
        return None
    return (v1 / v0) ** (1.0 / (yrs[-1] - yrs[0])) - 1.0


def _recent_mean(values: Dict[int, float], window: int = 5) -> Optional[float]:
    yrs = sorted(values)[-window:]
    if not yrs:
        return None
    return sum(values[y] for y in yrs) / len(yrs)


# ---------------------------------------------------------------------------
# Industry checks — each returns a list of warning strings (empty = clean).
# Signature: check(segment) -> List[str].
# ---------------------------------------------------------------------------

def _ck_asp_rising(seg: Segment) -> List[str]:
    """consumer_electronics: ASP historically *rising* — pricing power, or the
    erosion default will understate price."""
    c = _recent_cagr(seg.price.values)
    if c is not None and c > 0.03:
        return [f"ASP trending +{c:.0%}/yr — above the typical consumer-electronics "
                f"erosion path; the 5%/yr default will understate price if the trend "
                f"is real pricing power (justify, or switch PRICE to trend)."]
    return []


def _ck_hypergrowth_base(seg: Segment) -> List[str]:
    """semiconductor: base compounding >25%/yr — regime-shift territory."""
    c = _recent_cagr(seg.base.values)
    if c is not None and c > 0.25:
        return [f"base compounding +{c:.0%}/yr — hyper-growth like this is usually a "
                f"regime shift (see NVDA Data Center, 60% hold-out sMAPE). Consider "
                f"tagging this segment 'regime_shift_tech' and reporting scenarios."]
    return []


def _ck_net_churn_positive(seg: Segment) -> List[str]:
    """saas/telecom: base shrinking faster than ARPU grows — revenue math
    is already lost regardless of the price escalator (v0.17 Direction B)."""
    base_c = _recent_cagr(seg.base.values)
    price_c = _recent_cagr(seg.price.values)
    if base_c is not None and price_c is not None \
            and base_c < 0 and base_c + price_c < 0:
        return [f"implied net churn: base compounding {base_c:+.1%}/yr while "
                f"ARPU compounds {price_c:+.1%}/yr — net {base_c + price_c:+.1%} "
                f"still negative. No realistic price escalator offsets a "
                f"shrinking base; fix retention or cut to scenarios."]
    return []


def _ck_arpu_accelerating(seg: Segment) -> List[str]:
    """saas_subscription: ARPU compounding >10%/yr is rare without repricing."""
    c = _recent_cagr(seg.price.values)
    if c is not None and c > 0.10:
        return [f"ARPU compounding +{c:.0%}/yr — sustained NRR >120% is rare; "
                f"confirm there is a price-mix story, else the escalator overshoots."]
    return []


def _ck_adload_high(seg: Segment) -> List[str]:
    """advertising: ad load (penetration) materially above the 10-30% norm."""
    last = seg.penetration.values.get(max(seg.penetration.values))
    if last is not None and last > 0.30:
        return [f"ad load {last:.0%} — well above the 10–30% platform norm; user "
                f"experience (and regulation) typically caps further load growth."]
    return []


def _ck_shrinking_base(seg: Segment) -> List[str]:
    """retail_store: store count shrinking while sales/store rises — turnaround
    mix, fine, but the two trends must be told as one story."""
    cb = _recent_cagr(seg.base.values)
    cp = _recent_cagr(seg.price.values)
    if cb is not None and cp is not None and cb < -0.02 and cp > 0.03:
        return [f"store count {cb:.0%}/yr while sales/store {cp:+.0%}/yr — a "
                f" closures-and-upgrade turnaround. Make sure the forecast tells "
                f" both halves (fewer stores × richer stores), not just one."]
    return []


def _ck_base_saturated(seg: Segment) -> List[str]:
    """telecom_subscriber: subscriber base flat — growth must come from ARPU."""
    c = _recent_cagr(seg.base.values)
    if c is not None and abs(c) < 0.01:
        return ["subscriber base is flat (<1%/yr) — the segment is saturated; "
                "revenue growth must come from price (ARPU), which is usually "
                "policy- and competition-capped. Low structural growth."]
    return []


def _ck_utilization_cap(seg: Segment) -> List[str]:
    """industrial_capacity: utilization beyond 95% is not sustainable."""
    hot = [y for y, v in sorted(seg.penetration.values.items()) if v > 0.95]
    if hot:
        return [f"utilization >95% in {', '.join(str(y) for y in hot)} — capacity "
                f"is the binding constraint; growth needs capex (base), not a "
                f"higher utilization forecast. The mean-revert-to-80% default "
                f"is the honest assumption."]
    return []


def _ck_balance_growth_hot(seg: Segment) -> List[str]:
    """financial_interest: balance sheet compounding >20%/yr — credit-cycle flag."""
    c = _recent_cagr(seg.base.values)
    if c is not None and c > 0.20:
        return [f"interest-earning assets compounding +{c:.0%}/yr — balance-sheet "
                f"growth at that rate is a credit cycle, not a trend; stress the "
                f"rate assumption rather than extrapolating the balance sheet."]
    return []


def _ck_cycle_top(seg: Segment) -> List[str]:
    """commodity_cyclical: last price far above the multi-year mean — classic
    cycle top; trend extrapolation peaks the forecast at the worst moment."""
    last_yr = max(seg.price.values)
    last = seg.price.values[last_yr]
    m = _recent_mean(seg.price.values, window=5)
    if m is not None and m > 0 and last > 1.5 * m:
        return [f"price {last:.4g} is >1.5× the 5-yr mean ({m:.4g}) — likely cycle "
                f"top. A trend forecast would lock in peak-cycle prices forever; "
                f"the mean-reverting default is doing exactly its job."]
    return []


def _ck_regime_always(seg: Segment) -> List[str]:
    """regime_shift_tech: the warning IS the product — unconditional."""
    return ["regime-shift industry: the breakout is not in the training data, so "
            "ANY trend-based point forecast is a known-unreliable baseline (NVDA "
            "Data Center: actual $115B vs trend $18B). Report Monte Carlo "
            "scenarios (simulate_segment) with wide, honest ranges — the P90 "
            "tail framing the breakout is the deliverable, not the point."]


_CHECKS: Dict[str, Callable[[Segment], List[str]]] = {
    "asp_rising": _ck_asp_rising,
    "hypergrowth_base": _ck_hypergrowth_base,
    "arpu_accelerating": _ck_arpu_accelerating,
    "net_churn_positive": _ck_net_churn_positive,
    "adload_high": _ck_adload_high,
    "shrinking_base": _ck_shrinking_base,
    "base_saturated": _ck_base_saturated,
    "utilization_cap": _ck_utilization_cap,
    "balance_growth_hot": _ck_balance_growth_hot,
    "cycle_top": _ck_cycle_top,
    "regime_always": _ck_regime_always,
}


# ---------------------------------------------------------------------------
# The ten mechanism profiles (data, not subclasses — extend by adding entries)
# ---------------------------------------------------------------------------

INDUSTRY_PROFILES: Dict[str, IndustryProfile] = {
    "consumer_electronics": IndustryProfile(
        key="consumer_electronics",
        label_en="Consumer electronics / hardware",
        label_zh="消费电子 / 硬件",
        fit="strong",
        fit_note="trend-driven: shipments, attach rates and ASPs continue their "
                 "history (Luxun consumer-electronics hold-out −0.1% sMAPE)",
        defaults={
            BASE: ExtrapolationSpec("trend"),
            PENETRATION: ExtrapolationSpec("incremental", {"delta_pp": 0.02}),
            SHARE: ExtrapolationSpec("hold"),
            PRICE: ExtrapolationSpec("erosion", {"rate": 0.05}),
        },
        checks=("asp_rising",),
        benchmarks=(
            _dm_band("revenue_cagr_5y", 0.0416, 0.0699, 0.0748,
                     "cluster: Electronics (Consumer & Office), Electronics "
                     "(General), Computers/Peripherals, Office Equipment & "
                     "Services (172 firms)"),
            _dm_band("revenue_exp_growth_2y", 0.0119, 0.1020, 0.1979,
                     "cluster: Electronics (Consumer & Office), Electronics "
                     "(General), Computers/Peripherals, Office Equipment & "
                     "Services (172 firms)"),
        ),
    ),
    "semiconductor": IndustryProfile(
        key="semiconductor",
        label_en="Semiconductors (mature cycles)",
        label_zh="半导体（成熟周期）",
        fit="strong",
        fit_note="mature-semi factors trend until they don't (NVDA Gaming 1.0% "
                 "sMAPE); ASPs hold rather than erode (pricing power per node), "
                 "attach rates are structural product-cycle choices (held)",
        defaults={
            BASE: ExtrapolationSpec("trend"),
            PENETRATION: ExtrapolationSpec("hold"),
            SHARE: ExtrapolationSpec("hold"),
            PRICE: ExtrapolationSpec("hold"),
        },
        checks=("hypergrowth_base",),
        benchmarks=(
            _dm_band("revenue_cagr_5y", 0.0983, 0.1028, 0.1073,
                     "cluster: Semiconductor, Semiconductor Equip (97 firms)"),
            _dm_band("revenue_exp_growth_2y", 0.1920, 0.2644, 0.3368,
                     "cluster: Semiconductor, Semiconductor Equip (97 firms)"),
        ),
    ),
    "saas_subscription": IndustryProfile(
        key="saas_subscription",
        label_en="SaaS / subscription",
        label_zh="SaaS / 订阅",
        fit="adapt",
        fit_note="MAU/customers × ARPU: adoption follows an S-curve, ARPU grows "
                 "by escalator — the tree works with swapped factors",
        defaults={
            BASE: ExtrapolationSpec("net_growth",
                                    {"gross_rate": 0.30, "churn": 0.12}),
            PENETRATION: ExtrapolationSpec("logistic",
                                           {"L": 0.6, "k": 0.35, "t0": "anchor_last"}),
            SHARE: ExtrapolationSpec("hold"),
            PRICE: ExtrapolationSpec("growth", {"rate": 0.02}),
        },
        checks=("arpu_accelerating", "net_churn_positive"),
        benchmarks=(
            _dm_band("revenue_cagr_5y", 0.1637, 0.2333, 0.2762,
                     "cluster: Software (System & Application), Software "
                     "(Internet), Computer Services, Information Services "
                     "(417 firms)"),
            _dm_band("revenue_exp_growth_2y", 0.1195, 0.1868, 0.2640,
                     "cluster: Software (System & Application), Software "
                     "(Internet), Computer Services, Information Services "
                     "(417 firms)"),
        ),
    ),
    "advertising": IndustryProfile(
        key="advertising",
        label_en="Advertising",
        label_zh="广告",
        fit="adapt",
        fit_note="traffic × ad-load × eCPM: ad load is sticky (product choice), "
                 "eCPM is cyclical and mean-reverts with the ad market",
        defaults={
            BASE: ExtrapolationSpec("trend"),
            PENETRATION: ExtrapolationSpec("hold"),
            SHARE: ExtrapolationSpec("hold"),
            PRICE: ExtrapolationSpec("mean_revert", {"target": None, "speed": 0.3}),
        },
        checks=("adload_high",),
        benchmarks=(
            _dm_band("revenue_cagr_5y", 0.0632, 0.1242, 0.1674,
                     "cluster: Advertising, Entertainment, Publishing & "
                     "Newspapers, Broadcasting (187 firms)"),
            _dm_band("revenue_exp_growth_2y", 0.0051, 0.0463, 0.0832,
                     "cluster: Advertising, Entertainment, Publishing & "
                     "Newspapers, Broadcasting (187 firms)"),
        ),
    ),
    "retail_store": IndustryProfile(
        key="retail_store",
        label_en="Retail (store network)",
        label_zh="零售（门店网络）",
        fit="adapt",
        fit_note="stores × sales-per-store: openings are company-controlled "
                 "(trend), same-store sales mean-revert to CPI + low single digits",
        defaults={
            BASE: ExtrapolationSpec("trend"),
            PENETRATION: ExtrapolationSpec("hold"),
            SHARE: ExtrapolationSpec("hold"),
            PRICE: ExtrapolationSpec("mean_revert", {"target": None, "speed": 0.5}),
        },
        checks=("shrinking_base",),
        benchmarks=(
            _dm_band("revenue_cagr_5y", 0.0229, 0.0844, 0.1007,
                     "cluster: Retail (General), Retail (Special Lines), "
                     "Retail (Automotive), Retail (Building Supply), Retail "
                     "(Grocery and Food), Retail (Distributors) (242 firms)"),
            _dm_band("revenue_exp_growth_2y", 0.0416, 0.0492, 0.0700,
                     "cluster: Retail (General), Retail (Special Lines), "
                     "Retail (Automotive), Retail (Building Supply), Retail "
                     "(Grocery and Food), Retail (Distributors) (242 firms)"),
        ),
    ),
    "telecom_subscriber": IndustryProfile(
        key="telecom_subscriber",
        label_en="Telecom / subscribers",
        label_zh="电信 / 用户数",
        fit="adapt",
        fit_note="subscribers × ARPU: subscriber growth saturates (logistic), "
                 "ARPU drifts slowly and is policy-capped",
        defaults={
            BASE: ExtrapolationSpec("net_growth",
                                    {"gross_rate": 0.05, "churn": 0.035}),
            PENETRATION: ExtrapolationSpec("hold"),
            SHARE: ExtrapolationSpec("hold"),
            PRICE: ExtrapolationSpec("hold"),
        },
        checks=("base_saturated", "net_churn_positive"),
        benchmarks=(
            _dm_band("revenue_cagr_5y", 0.0863, 0.1357, 0.2026,
                     "cluster: Telecom (Wireless), Telecom. Services, Cable "
                     "TV (60 firms)"),
            _dm_band("revenue_exp_growth_2y", -0.0421, -0.0293, 0.2592,
                     "cluster: Telecom (Wireless), Telecom. Services, Cable "
                     "TV (60 firms)"),
        ),
    ),
    "industrial_capacity": IndustryProfile(
        key="industrial_capacity",
        label_en="Industrial / capacity-driven",
        label_zh="工业 / 产能驱动",
        fit="adapt",
        fit_note="capacity × utilization × price: utilization is bounded and "
                 "mean-reverts (70–90%); capacity is a capex decision (trend)",
        defaults={
            BASE: ExtrapolationSpec("trend"),
            PENETRATION: ExtrapolationSpec("mean_revert",
                                           {"target": 0.8, "speed": 0.4}),
            SHARE: ExtrapolationSpec("hold"),
            PRICE: ExtrapolationSpec("trend"),
        },
        checks=("utilization_cap",),
        benchmarks=(
            _dm_band("revenue_cagr_5y", 0.0881, 0.1103, 0.1357,
                     "cluster: Machinery, Electrical Equipment, Engineering/"
                     "Construction, Building Materials (306 firms)"),
            _dm_band("revenue_exp_growth_2y", 0.0862, 0.1141, 0.2839,
                     "cluster: Machinery, Electrical Equipment, Engineering/"
                     "Construction, Building Materials (306 firms)"),
        ),
    ),
    "financial_interest": IndustryProfile(
        key="financial_interest",
        label_en="Financials (interest income)",
        label_zh="金融（利息收入）",
        fit="weak",
        fit_note="interest-earning assets × yield: the rate cycle is not in the "
                 "historical window — point forecasts structurally unreliable",
        advice="anchor the yield to the forward policy-rate curve and run rate "
               "scenarios; treat the balance-sheet growth as a credit-cycle "
               "variable, not a trend",
        defaults={
            BASE: ExtrapolationSpec("growth", {"rate": 0.08}),
            PENETRATION: ExtrapolationSpec("hold"),
            SHARE: ExtrapolationSpec("hold"),
            PRICE: ExtrapolationSpec("mean_revert",
                                     {"target": 0.04, "speed": 0.5}),
        },
        checks=("balance_growth_hot",),
        benchmarks=(
            _dm_band("revenue_cagr_5y", 0.0830, 0.0855, 0.0880,
                     "cluster: Bank (Money Center), Banks (Regional) "
                     "(583 firms)"),
            _dm_band("revenue_exp_growth_2y", 0.0977, 0.1099, 0.1221,
                     "cluster: Bank (Money Center), Banks (Regional) "
                     "(583 firms)"),
        ),
    ),
    "commodity_cyclical": IndustryProfile(
        key="commodity_cyclical",
        label_en="Commodities / cyclical",
        label_zh="大宗商品 / 周期",
        fit="weak",
        fit_note="price is cyclical around marginal cost — trend extrapolation "
                 "peaks the forecast at exactly the wrong moment of the cycle",
        advice="mean-revert price to marginal cost and run demand/capacity-shock "
               "scenarios; watch leading indicators (inventories, spreads) "
               "instead of fitting the trend",
        defaults={
            BASE: ExtrapolationSpec("hold"),
            PENETRATION: ExtrapolationSpec("hold"),
            SHARE: ExtrapolationSpec("hold"),
            PRICE: ExtrapolationSpec("mean_revert", {"target": None, "speed": 0.3}),
        },
        checks=("cycle_top",),
        benchmarks=(
            _dm_band("revenue_cagr_5y", 0.0935, 0.1449, 0.1883,
                     "cluster: Metals & Mining, Coal & Related Energy, Oil/Gas "
                     "(Integrated), Oil/Gas (Production and Exploration), "
                     "Steel, Precious Metals (310 firms)"),
            _dm_band("revenue_exp_growth_2y", 0.0680, 0.2341, 0.4683,
                     "cluster: Metals & Mining, Coal & Related Energy, Oil/Gas "
                     "(Integrated), Oil/Gas (Production and Exploration), "
                     "Steel, Precious Metals (310 firms)"),
        ),
    ),
    "regime_shift_tech": IndustryProfile(
        key="regime_shift_tech",
        label_en="Regime-shift tech (AI inflection)",
        label_zh="范式跳变科技（AI 拐点）",
        fit="weak",
        fit_note="NVDA Data Center: same formula as Gaming, 60% hold-out sMAPE "
                 "(actual $115B vs trend $18B) — the breakout is not in the "
                 "training data, and no trend fit can recover it",
        advice="the point forecast below is a *baseline, not a forecast*: report "
               "Monte Carlo scenarios (simulate_segment) with wide honest ranges "
               "plus explicit trigger conditions; update fast as the regime "
               "reveals itself",
        defaults={  # naive trend on purpose — the baseline you measure against
            BASE: ExtrapolationSpec("trend"),
            PENETRATION: ExtrapolationSpec("trend"),
            SHARE: ExtrapolationSpec("trend"),
            PRICE: ExtrapolationSpec("trend"),
        },
        checks=("regime_always",),
        # benchmarks=() by design: an AI-inflection breakout has no meaningful
        # industry history to anchor to — the whole profile is the warning
    ),
}


# ---------------------------------------------------------------------------
# Alias resolution — mechanism keys, GICS sectors, Chinese names
# ---------------------------------------------------------------------------

_ALIASES: Dict[str, str] = {
    # GICS sector codes (coarse — see notes in each profile)
    "10": "commodity_cyclical",    "15": "commodity_cyclical",
    "20": "industrial_capacity",   "25": "retail_store",
    "30": "retail_store",          "40": "semiconductor",
    "45": "financial_interest",    "50": "telecom_subscriber",
    # GICS sector names (lowercased)
    "energy": "commodity_cyclical",       "materials": "commodity_cyclical",
    "industrials": "industrial_capacity", "consumer discretionary": "retail_store",
    "consumer staples": "retail_store",   "information technology": "semiconductor",
    "financials": "financial_interest",   "communication services": "telecom_subscriber",
    # Chinese aliases
    "消费电子": "consumer_electronics",   "硬件": "consumer_electronics",
    "半导体": "semiconductor",            "芯片": "semiconductor",
    "软件": "saas_subscription",          "订阅": "saas_subscription",
    "广告": "advertising",                "互联网广告": "advertising",
    "零售": "retail_store",               "门店": "retail_store",
    "电信": "telecom_subscriber",         "运营商": "telecom_subscriber",
    "工业": "industrial_capacity",        "制造业": "industrial_capacity",
    "银行": "financial_interest",         "金融": "financial_interest",
    "保险": "financial_interest",
    "大宗商品": "commodity_cyclical",     "周期": "commodity_cyclical",
    "能源": "commodity_cyclical",         "原材料": "commodity_cyclical",
    "人工智能": "regime_shift_tech",      "ai": "regime_shift_tech",
}


def resolve_industry(name: str) -> IndustryProfile:
    """Mechanism key, GICS code/name, or Chinese alias → IndustryProfile.

    Raises KeyError with the full catalog on unknown input (health care and
    real estate intentionally unmapped — no mechanism profile fits them yet).
    """
    key = name.strip().lower()
    if key in INDUSTRY_PROFILES:
        return INDUSTRY_PROFILES[key]
    if name.strip() in _ALIASES:
        return INDUSTRY_PROFILES[_ALIASES[name.strip()]]
    if key in _ALIASES:
        return INDUSTRY_PROFILES[_ALIASES[key]]
    raise KeyError(
        f"unknown industry: {name!r}. Mechanism profiles: "
        f"{sorted(INDUSTRY_PROFILES)}; GICS sector codes/names and Chinese "
        f"aliases are also accepted (e.g. '40', 'financials', '银行').")


def list_profiles() -> List[Tuple[str, str, str]]:
    """[(key, fit, label_en)] for discovery and CLI help."""
    return [(p.key, p.fit, p.label_en) for p in INDUSTRY_PROFILES.values()]


# ---------------------------------------------------------------------------
# Forecast & warnings
# ---------------------------------------------------------------------------

def _resolve_params(params: Dict, driver: Driver) -> Dict:
    """Resolve relative string params against the driver's history."""
    last_yr = max(driver.values) if driver.values else 0
    out: dict = {}
    for k, v in params.items():
        if isinstance(v, str) and v == "last":
            out[k] = last_yr
        elif isinstance(v, str) and v.endswith("*last"):
            out[k] = float(v[:-5]) * driver.values[last_yr]
        else:
            out[k] = v
    return out


def _logistic_t0_through_last(driver: Driver, *, L: float, k: float) -> float:
    """Solve the logistic inflection year so the curve passes through the last
    known value — forecasts leave history smoothly instead of jumping to L/2
    (t0 = last_yr + ln(L/last − 1)/k)."""
    last_yr = max(driver.values)
    last_val = driver.values[last_yr]
    if not 0 < last_val < L:
        raise ValueError(
            f"logistic anchor: last value {last_val:.4g} must be in (0, L={L:.4g}) "
            f"— raise L or lower the starting point")
    return last_yr + math.log(L / last_val - 1.0) / k


def _apply_spec(driver: Driver, years: List[int], spec: ExtrapolationSpec) -> Driver:
    """Dispatch an ExtrapolationSpec to its Driver.extrapolate_* method.

    Soft-default rule: a driver the analyst already extended to *all* target
    years wins untouched — no spec params are even resolved (a hand-held
    structural constant must not trip, say, a logistic anchor check).
    Partial coverage still gets spec treatment for the missing years.
    """
    if years and all(y in driver.values for y in years):
        return driver
    p = _resolve_params(spec.params, driver)
    if spec.method == "incremental":
        return driver.extrapolate_incremental(years, p.get("delta_pp", 0.02))
    if spec.method == "logistic":
        if spec.params.get("t0") == "anchor_last":
            p["t0"] = _logistic_t0_through_last(driver, L=p["L"], k=p["k"])
        return driver.extrapolate_logistic(years, **p)
    if spec.method == "trend":
        return driver.fit_trend(sorted(driver.values)).extrapolate(years)
    if spec.method == "mean_revert":
        return driver.extrapolate_mean_reversion(
            years, target=p.get("target"), speed=p.get("speed", 0.5))
    if spec.method == "erosion":
        return driver.extrapolate_erosion(years, p.get("rate", 0.05))
    if spec.method == "growth":
        return driver.extrapolate_growth(years, p.get("rate", 0.08))
    if spec.method == "net_growth":
        return driver.extrapolate_net_growth(
            years, p.get("gross_rate", 0.20), p.get("churn", 0.10))
    if spec.method == "hold":
        return driver.extrapolate_hold(years)
    raise ValueError(f"unknown extrapolation method: {spec.method!r}")


def forecast_segment(seg: Segment, years: List[int],
                     *, profile: Optional[IndustryProfile] = None) -> Segment:
    """Extend a segment's drivers using industry-default extrapolations.

    Soft defaults (v0.16 design rule): every driver already extended by hand —
    or extended here — stays overridable; call the ``Driver.extrapolate_*``
    methods yourself on the returned segment to override any factor. Only
    years beyond each driver's last known year are added; history is never
    touched. Profile resolution order: explicit ``profile=`` → the segment's
    ``industry`` tag → ValueError.
    """
    if profile is None:
        if not seg.industry:
            raise ValueError(
                "no industry on segment — pass profile=..., or tag the segment: "
                "Segment(..., industry='saas_subscription') (also accepts GICS "
                "aliases like '40' / 'financials' / '银行')")
        profile = resolve_industry(seg.industry)

    new = Segment(
        name=seg.name,
        base=_apply_spec(seg.base, years, profile.defaults[BASE]),
        penetration=_apply_spec(seg.penetration, years, profile.defaults[PENETRATION]),
        share=_apply_spec(seg.share, years, profile.defaults[SHARE]),
        price=_apply_spec(seg.price, years, profile.defaults[PRICE]),
        reported_revenue=dict(seg.reported_revenue),
        industry=seg.industry or profile.key,
    )
    # every forecast year without a reported anchor now depends on C-grade
    # industry defaults — tag the segment so downstream docs can say so
    return new


def profile_warnings(profile: IndustryProfile, lang: str = "en") -> List[str]:
    """Fit-class verdicts. The weak-fit line is the doc's §4 redirect, encoded."""
    if profile.fit == "weak":
        return [f"[{profile.key}] {profile.fit_label(lang)} — point forecasts are "
                f"structurally unreliable here. {profile.advice}"]
    if profile.fit == "adapt":
        return [f"[{profile.key}] {profile.fit_label(lang)} — driver tree works "
                f"with swapped factors ({profile.fit_note})."]
    return [f"[{profile.key}] {profile.fit_label(lang)} — {profile.fit_note}."]


def check_segment(seg: Segment,
                  *, profile: Optional[IndustryProfile] = None) -> List[str]:
    """Run the segment's industry checks against its *historical* drivers."""
    if profile is None:
        if not seg.industry:
            return []
        profile = resolve_industry(seg.industry)
    out: List[str] = []
    for name in profile.checks:
        out.extend(_CHECKS[name](seg))
    return out


def segment_warnings(seg: Segment,
                     *, profile: Optional[IndustryProfile] = None) -> List[str]:
    """Convenience: fit verdict + industry checks, one list. Put this next to
    any industry-default forecast you publish."""
    if profile is None and seg.industry:
        profile = resolve_industry(seg.industry)
    if profile is None:
        return []
    return profile_warnings(profile) + check_segment(seg, profile=profile)
