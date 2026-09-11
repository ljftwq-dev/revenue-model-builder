"""Driver — a single revenue driver factor (market base / penetration / share / price).

Extrapolation API (Principle 3 encoded as code):
- ``extrapolate_incremental`` — +pp/yr for bounded ratios (penetration/share);
  absolute increment stays constant as the base grows (unlike a % growth rate).
- ``extrapolate_logistic`` — S-curve for long-horizon saturation.
- ``fit_trend(...).extrapolate(...)`` — OLS linear trend for unbounded (price/base).
- ``extrapolate_mean_reversion`` — pull toward an anchor (yields, utilization, eCPM).
- ``extrapolate_erosion`` — geometric decline (ASP erosion in electronics).
- ``extrapolate_growth`` — geometric growth (balance sheets, ARPU escalators).
- ``extrapolate_hold`` — flat extension of the last value (sticky factors).
All return a *new* Driver downgraded to C-grade, source tagged 'extrapolated'.
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional

DriverKind = Literal["base", "penetration", "share", "price"]
DataLevel = Literal["A", "B", "C"]

BASE: DriverKind = "base"
PENETRATION: DriverKind = "penetration"
SHARE: DriverKind = "share"
PRICE: DriverKind = "price"

LEVEL_A: DataLevel = "A"
LEVEL_B: DataLevel = "B"
LEVEL_C: DataLevel = "C"

_KIND_LABELS = {
    BASE: {"zh": "市场基数", "en": "Market Base"},
    PENETRATION: {"zh": "渗透率", "en": "Penetration"},
    SHARE: {"zh": "市占率", "en": "Share"},
    PRICE: {"zh": "单价", "en": "Unit Price"},
}


@dataclass
class Driver:
    name: str
    kind: DriverKind
    values: Dict[int, float]
    level: DataLevel = LEVEL_C
    unit: str = ""
    source: str = ""
    source_url: str = ""   # optional URL → rendered as a clickable hyperlink in docx_builder

    def __post_init__(self):
        if self.kind not in _KIND_LABELS:
            raise ValueError(f"unknown driver kind: {self.kind!r}")

    def get(self, year: int) -> float:
        if year not in self.values:
            raise KeyError(f"{self.name}: no value for year {year}")
        return self.values[year]

    def years(self):
        return sorted(self.values.keys())

    def kind_label(self, lang: Literal["zh", "en"] = "zh") -> str:
        labels = _KIND_LABELS[self.kind]
        return labels.get(lang, labels["zh"])

    # ---- A2: driver extrapolation — Principle 3 as API ----
    def extrapolate_incremental(self, years: List[int], delta_pp: float) -> "Driver":
        """Incremental extrapolation: +``delta_pp`` (percentage points) per year.

        For bounded ratios (penetration/share) the increment is *absolute* —
        a 3pp/yr gain stays 3pp as the base grows, unlike a growth rate that
        decays. Values are clamped to <= 1.0 with a source flag.
        Returns a new Driver downgraded to C-grade.
        """
        last_yr = max(self.values)
        last_val = self.values[last_yr]
        bounded = self.kind in (PENETRATION, SHARE)
        new_values = dict(self.values)
        clamped = False
        for y in years:
            v = last_val + delta_pp * (y - last_yr)
            if bounded and v > 1.0:
                v = 1.0
                clamped = True
            new_values[y] = v
        src = f"incremental +{delta_pp}/yr extrapolated"
        if clamped:
            src += " (clamped to 1.0)"
        return Driver(self.name, self.kind, new_values, level=LEVEL_C,
                      unit=self.unit, source=src)

    def extrapolate_logistic(self, years: List[int], *, L: float, k: float,
                             t0: float) -> "Driver":
        """Logistic S-curve extrapolation: ``L / (1 + exp(-k*(t-t0)))``.

        For long-horizon saturation (e.g. penetration capping at L as a market
        matures). Returns a new Driver downgraded to C-grade.
        """
        new_values = dict(self.values)
        for y in years:
            new_values[y] = L / (1 + math.exp(-k * (y - t0)))
        return Driver(self.name, self.kind, new_values, level=LEVEL_C,
                      unit=self.unit,
                      source=f"logistic L={L} k={k} t0={t0} extrapolated")

    def extrapolate_mean_reversion(self, years: List[int],
                                    *, target: Optional[float] = None,
                                    speed: float = 0.5) -> "Driver":
        """Mean reversion toward an anchor: ``v <- v + speed*(target - v)`` per year.

        For cyclical or policy-anchored factors — interest yields, capacity
        utilization, eCPM, cyclical commodity prices — where the honest default
        is "return to the anchor", not "continue the trend".
        ``target=None`` anchors to the mean of the last 3 known years.
        Returns a new Driver downgraded to C-grade.
        """
        if not 0 < speed <= 1:
            raise ValueError(f"speed must be in (0, 1], got {speed}")
        if target is None:
            recent = sorted(self.values)[-3:]
            target = sum(self.values[y] for y in recent) / len(recent)
        last_yr = max(self.values)
        v = self.values[last_yr]
        # march forward year by year so multi-year horizons compound the pull
        fwd: Dict[int, float] = {}
        for y in range(last_yr + 1, max(years) + 1):
            v = v + speed * (target - v)
            fwd[y] = v
        new_values = dict(self.values)
        for y in years:
            if y > last_yr:
                new_values[y] = fwd[y]
        return Driver(self.name, self.kind, new_values, level=LEVEL_C,
                      unit=self.unit,
                      source=f"mean-reverting to {target:.4g} (speed={speed}/yr) extrapolated")

    def extrapolate_erosion(self, years: List[int], rate: float) -> "Driver":
        """Geometric price erosion: ``v * (1 - rate)^(y - last_yr)``.

        The canonical consumer-electronics default: ASPs decline a few % per
        year as products mature. ``rate`` in (0, 1). Returns a new Driver
        downgraded to C-grade.
        """
        if not 0 < rate < 1:
            raise ValueError(f"erosion rate must be in (0, 1), got {rate}")
        last_yr = max(self.values)
        last_val = self.values[last_yr]
        new_values = dict(self.values)
        for y in years:
            if y > last_yr:
                new_values[y] = last_val * (1.0 - rate) ** (y - last_yr)
        return Driver(self.name, self.kind, new_values, level=LEVEL_C,
                      unit=self.unit,
                      source=f"erosion -{rate:.0%}/yr extrapolated")

    def extrapolate_growth(self, years: List[int], rate: float) -> "Driver":
        """Geometric growth: ``v * (1 + rate)^(y - last_yr)``.

        For balance-sheet-like bases (interest-earning assets) and contractual
        escalators (ARPU step-ups). ``rate`` > -1. Returns a new Driver
        downgraded to C-grade.
        """
        if rate <= -1:
            raise ValueError(f"growth rate must be > -1, got {rate}")
        last_yr = max(self.values)
        last_val = self.values[last_yr]
        new_values = dict(self.values)
        for y in years:
            if y > last_yr:
                new_values[y] = last_val * (1.0 + rate) ** (y - last_yr)
        return Driver(self.name, self.kind, new_values, level=LEVEL_C,
                      unit=self.unit,
                      source=f"geometric +{rate:.0%}/yr extrapolated")

    def extrapolate_hold(self, years: List[int]) -> "Driver":
        """Flat extension of the last known value.

        For sticky factors an analyst would not forecast off-trend without
        evidence: ad load, telecom ARPU, market share at steady state.
        Returns a new Driver downgraded to C-grade.
        """
        last_yr = max(self.values)
        last_val = self.values[last_yr]
        new_values = dict(self.values)
        for y in years:
            if y > last_yr:
                new_values[y] = last_val
        return Driver(self.name, self.kind, new_values, level=LEVEL_C,
                      unit=self.unit, source="held flat extrapolated")

    def fit_trend(self, fit_years: List[int]) -> "_TrendFit":
        """Ordinary-least-squares linear fit over ``fit_years`` (pure stdlib).

        Returns a ``_TrendFit`` whose ``.extrapolate(years)`` extends the line.
        For unbounded drivers (price/base). Needs >= 2 known years.
        """
        xs = [y for y in fit_years if y in self.values]
        ys = [self.values[y] for y in xs]
        if len(xs) < 2:
            raise ValueError(f"fit_trend needs >=2 known years, got {len(xs)}")
        n = len(xs)
        mx = sum(xs) / n
        my = sum(ys) / n
        denom = sum((x - mx) ** 2 for x in xs)
        if denom == 0:
            raise ValueError("fit_trend: all fit years identical")
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
        intercept = my - slope * mx
        return _TrendFit(self, slope, intercept)


class _TrendFit:
    """Result of ``Driver.fit_trend`` — call ``.extrapolate(years)`` to extend."""

    def __init__(self, driver: "Driver", slope: float, intercept: float):
        self.driver = driver
        self.slope = slope
        self.intercept = intercept

    def extrapolate(self, years: List[int]) -> "Driver":
        new_values = dict(self.driver.values)
        for y in years:
            new_values[y] = self.intercept + self.slope * y
        return Driver(self.driver.name, self.driver.kind, new_values, level=LEVEL_C,
                      unit=self.driver.unit,
                      source=f"linear trend (slope={self.slope:.4g}/yr) extrapolated")
