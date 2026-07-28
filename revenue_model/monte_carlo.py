"""Monte Carlo + sensitivity analysis — turn point forecasts into distributions.

Design choice: implemented on the Python standard library only (``random`` +
``statistics``). No numpy. The core engine stays zero-dependency; this module
inherits that property. For 10k samples of a four-factor product, stdlib timing
is a few tens of milliseconds — fast enough for interactive modeling.

Two complementary views of uncertainty:

* :func:`simulate_segment` / :func:`simulate_model` — **Monte Carlo**: sample
  drivers from ranges, multiply, repeat → a *distribution* of revenue with
  confidence intervals (P5/P25/median/P75/P95). Answers "how uncertain is the
  number?"

* :func:`tornado` — **sensitivity** (one-at-a-time): perturb each driver ±pct
  holding others fixed → ranked "swing" per driver. Answers "which assumption
  matters most?" without any randomness.
"""

import random
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .driver import PENETRATION, SHARE
from .model import RevenueModel
from .segment import Segment

Range = Tuple[float, float]


@dataclass
class MCResult:
    """Summary of a Monte Carlo revenue distribution (million yuan)."""
    year: int
    n: int
    mean: float
    median: float
    stdev: float
    percentiles: Dict[str, float]
    samples: List[float] = field(default_factory=list, repr=False)


@dataclass
class SensitivityItem:
    """One row of a tornado chart: swing in revenue when one driver moves."""
    segment: str
    driver: str
    low_revenue: float
    base_revenue: float
    high_revenue: float
    swing: float


def _summarize(samples: List[float], year: int) -> MCResult:
    s = sorted(samples)
    n = len(s)

    def pct(p: float) -> float:
        return s[min(max(int(round(p * n)), 0), n - 1)]

    return MCResult(
        year=year,
        n=n,
        mean=statistics.fmean(s),
        median=statistics.median(s),
        stdev=(statistics.pstdev(s) if n > 1 else 0.0),
        percentiles={"p5": pct(0.05), "p25": pct(0.25),
                     "p75": pct(0.75), "p95": pct(0.95)},
        samples=s,
    )


def simulate_segment(segment: Segment, year: int, ranges: Dict[str, Range],
                     n: int = 10000, *, seed: int = 0) -> MCResult:
    """Monte Carlo for one segment's revenue in one year.

    ``ranges`` maps ``driver.name -> (low, high)``; each named driver is sampled
    uniformly from its interval, the rest stay at their point value. Returns the
    distribution of ``base × penetration × share × price`` (million yuan).

    Driver names are expected to be unique within the segment (Segment already
    enforces this).
    """
    if year not in segment.base.values:
        raise KeyError(f"{segment.name}: drivers have no value for year {year}")
    rng = random.Random(seed)
    factors = [(d, d.name in ranges) for d in segment.drivers()]
    samples: List[float] = []
    for _ in range(n):
        prod = 1.0
        for d, uncertain in factors:
            if uncertain:
                lo, hi = ranges[d.name]
                prod *= rng.uniform(lo, hi)
            else:
                prod *= d.get(year)
        samples.append(prod)
    return _summarize(samples, year)


def simulate_model(model: RevenueModel, year: int,
                   ranges: Dict[str, Range], n: int = 10000, *,
                   seed: int = 0) -> MCResult:
    """Monte Carlo for total *modeled* revenue (Σ segments) in one year.

    This is the sum of segment revenues — it does **not** include the residual
    line, because the residual is anchored to the reported total (a hard input,
    not uncertain). Use this to quantify how driver uncertainty propagates to
    the modeled portion of the business.
    """
    rng = random.Random(seed)
    per_segment = [[(d, d.name in ranges) for d in seg.drivers()]
                   for seg in model.segments]
    samples: List[float] = []
    for _ in range(n):
        total = 0.0
        for seg, factors in zip(model.segments, per_segment):
            prod = 1.0
            for d, uncertain in factors:
                if uncertain:
                    lo, hi = ranges[d.name]
                    prod *= rng.uniform(lo, hi)
                else:
                    prod *= d.get(year)
            total += prod
        samples.append(total)
    return _summarize(samples, year)


def tornado(segment: Segment, year: int,
            ranges: Dict[str, Range]) -> List[SensitivityItem]:
    """One-at-a-time sensitivity for a segment in a year.

    ``ranges`` maps ``driver.name -> (low, high)`` absolute bounds — *each
    driver's own uncertainty band*, not a uniform percentage. This is essential
    for a multiplicative model: perturbing every factor by the same ±% yields
    identical swings (revenue scales 1:1 with any factor), so a tornado is only
    meaningful when bands reflect each driver's real uncertainty — typically
    narrow for A-grade hard data, wide for C-grade estimates.

    For each driver, revenue is recomputed at its low and high while the others
    stay at base, and results are ranked by swing descending — the classic
    tornado-chart ordering. Penetration/share highs are clipped to 1.0; drivers
    absent from ``ranges`` are skipped. Fully deterministic.
    """
    if year not in segment.base.values:
        raise KeyError(f"{segment.name}: drivers have no value for year {year}")
    base_revenue = segment.revenue(year)
    items: List[SensitivityItem] = []
    for d in segment.drivers():
        if d.name not in ranges:
            continue
        lo, hi = ranges[d.name]
        lo = max(0.0, lo)
        if d.kind in (PENETRATION, SHARE):
            hi = min(hi, 1.0)
        low_rev = _revenue_with(segment, year, d.name, lo)
        high_rev = _revenue_with(segment, year, d.name, hi)
        items.append(SensitivityItem(
            segment=segment.name, driver=d.name,
            low_revenue=low_rev, base_revenue=base_revenue,
            high_revenue=high_rev, swing=abs(high_rev - low_rev)))
    items.sort(key=lambda x: x.swing, reverse=True)
    return items


def _revenue_with(segment: Segment, year: int, driver_name: str,
                  override: float) -> float:
    """Segment revenue with one driver replaced by ``override``."""
    prod = 1.0
    for d in segment.drivers():
        prod *= override if d.name == driver_name else d.get(year)
    return prod


@dataclass
class Scenario:
    """One of Bear / Base / Bull, derived from a Monte Carlo distribution."""
    name: str
    revenue: float
    percentile: float


def scenarios(mc: MCResult, *, bear_p: float = 0.10, bull_p: float = 0.90) -> List[Scenario]:
    """Derive Bear / Base / Bull from a Monte Carlo revenue distribution.

    A free byproduct of the distribution: Bear = P(bear_p), Base = median,
    Bull = P(bull_p). This avoids hand-setting three parameter sets — the
    scenarios fall straight out of the uncertainty you already modeled in
    :func:`simulate_segment` / :func:`simulate_model`.

    Default bands P10 / median / P90; tighten or widen via ``bear_p`` / ``bull_p``.
    """
    s = mc.samples
    n = len(s)

    def q(p: float) -> float:
        return s[min(max(int(round(p * n)), 0), n - 1)]

    return [
        Scenario("Bear", q(bear_p), bear_p),
        Scenario("Base", mc.median, 0.50),
        Scenario("Bull", q(bull_p), bull_p),
    ]
