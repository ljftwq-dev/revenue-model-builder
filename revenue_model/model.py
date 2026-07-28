"""RevenueModel — multi-segment model anchored to total revenue, with residual alignment."""

from dataclasses import dataclass
from typing import Dict, List

from .segment import Segment


@dataclass
class YearResult:
    year: int
    segment_revenues: Dict[str, float]
    segment_sum: float
    total_revenue: float
    residual: float
    residual_ratio: float
    warnings: List[str]


@dataclass
class RevenueModel:
    company: str
    segments: List[Segment]
    total_revenue: Dict[int, float]

    def years(self):
        return sorted(self.total_revenue.keys())

    def segment_sum(self, year: int) -> float:
        return sum(seg.revenue(year) for seg in self.segments)

    def residual(self, year: int) -> float:
        """Residual line = total_revenue − Σ(segments). Absorbs un-modeled business
        (e.g. aftermarket, IoT, custom dev). Structural by design — never back-solve
        penetration to force it to zero."""
        return self.total_revenue[year] - self.segment_sum(year)

    def validate(self, year: int) -> YearResult:
        seg_rev = {seg.name: seg.revenue(year) for seg in self.segments}
        s = sum(seg_rev.values())
        total = self.total_revenue[year]
        resid = total - s
        ratio = resid / total if total else 0.0
        warnings: List[str] = []
        if resid < -1e-6:
            warnings.append(
                f"residual negative ({resid:.1f}): segments exceed total revenue, "
                f"model structure is wrong")
        if ratio > 0.5:
            warnings.append(
                f"residual ratio {ratio:.0%} too high: un-modeled business dominates, "
                f"consider adding segments")
        if 0 < ratio < 0.05:
            warnings.append(
                f"residual ratio {ratio:.0%} suspiciously small: penetration may have "
                f"been back-solved (should keep industry-realistic values)")
        return YearResult(year, seg_rev, s, total, resid, ratio, warnings)

    def validate_all(self) -> List[YearResult]:
        return [self.validate(y) for y in self.years()]
