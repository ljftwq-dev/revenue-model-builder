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
        # When every segment carries an A-grade reported anchor, a near-zero
        # residual reflects caliber consistency (the company's own segments sum
        # to its own total), NOT the back-solve trap (Principle 1). Allow a
        # rounding tolerance — reported figures are whole-millions, so a Σ vs
        # total difference of ±(N+1) is rounding noise, not a smell. Without
        # this, every real reported-anchor model would falsely trip
        # "penetration back-solved" / "model structure wrong".
        all_reported = bool(seg_rev) and all(
            seg.revenue_source(year) == "reported" for seg in self.segments)
        rounding_tol = float(len(self.segments) + 1)  # ~1M per segment + total
        ties_out = all_reported and abs(resid) <= rounding_tol
        warnings: List[str] = []
        if resid < -1e-6 and not ties_out:
            warnings.append(
                f"residual negative ({resid:.1f}): segments exceed total revenue, "
                f"model structure is wrong")
        if ratio > 0.5:
            warnings.append(
                f"residual ratio {ratio:.0%} too high: un-modeled business dominates, "
                f"consider adding segments")
        if 0 < ratio < 0.05 and not ties_out:
            if ratio < 0.01:
                warnings.append(
                    f"residual ratio {ratio:.1%} near zero: penetration was likely "
                    f"back-solved to force alignment (base/pen/share should use "
                    f"industry-realistic values, not fitted)")
            else:
                warnings.append(
                    f"residual ratio {ratio:.0%} small: usually fine when few "
                    f"segments cover most revenue (e.g. after a caliber change); "
                    f"only a concern if penetration was fitted")
        return YearResult(year, seg_rev, s, total, resid, ratio, warnings)

    def validate_all(self) -> List[YearResult]:
        return [self.validate(y) for y in self.years()]

    @classmethod
    def from_report(cls, text: str, *, api_key: str = None, llm=None,
                    year: int = None, **extract_kwargs) -> "RevenueModel":
        """Build a model straight from annual-report text (end-to-end pipeline).

        Runs segment extraction (LLM) -> skeleton -> ``Segment`` placeholders
        -> model. Driver **values** are placeholders (0.0) tagged with the
        LLM's hints as ``source``; filling real C-grade values is the next,
        human step (see ``docs/proposal-segment-extraction.md`` §7).

        Load ``api_key`` via your secrets manager (never hardcode); pass
        ``llm`` (a ``messages -> content`` callable) for offline/testing.
        """
        from .extractor import extract_segments
        from .pipeline import parsed_to_segments
        parsed = extract_segments(text, api_key=api_key, llm=llm, **extract_kwargs)
        yr = year or parsed.get("fiscal_year") or 2024
        segments = parsed_to_segments(parsed, yr)
        total_yuan = float(parsed.get("total_revenue") or 0)
        total = {yr: total_yuan / 1e6} if total_yuan else {}
        return cls(parsed.get("company", "Unknown"), segments, total_revenue=total)
