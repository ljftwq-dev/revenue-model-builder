"""Profile auto-recommendation (v0.19): suggest_profile().

The v0.16 lesson: accuracy is a property of the industry mechanism, and the
mis-tag teaching moment showed what a wrong label costs (DC tagged
"semiconductor" collapsed 6x). This module closes the other half of the
loop — the analyst who *doesn't know* which profile to tag gets a ranked,
evidence-carrying shortlist before forecasting.

Method: run the zero-dependency subset of the v0.17 backtest battery
(Naive, LinearTrend, LogLinearCAGR, DampedTrend, DeceleratingCAGR) on each
driver's own history; score every profile by how well its default
extrapolation family ranks on that driver, add a band-proximity bonus from
the v0.18 benchmarks (revenue CAGR inside the profile's industry band), and
a hypergrowth override for the regime-shift lesson (trends don't survive
breaks). Every suggestion carries its reasons as text lines.

Soft by design: this ranks and explains, never tags for you — the analyst
still makes the call (and can override anything downstream, as always).
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .backtest.methods import (
    DeceleratingCAGR, DampedTrend, ForecastMethod, LinearTrend,
    LogLinearCAGR, Naive,
)
from .backtest.rolling import evaluate, rolling_backtest
from .industry import INDUSTRY_PROFILES
from .segment import Segment

# Zero-dependency battery (statsmodels-based Holt/ARIMA deliberately out —
# suggest must run on a bare install, like the rest of the kernel)
_SUGGEST_METHODS: List[ForecastMethod] = [
    Naive(), LinearTrend(), LogLinearCAGR(), DampedTrend(phi=0.85),
    DeceleratingCAGR(phi=0.80),
]

# ExtrapolationSpec method -> battery representatives, keyed by *battery
# names* ("Naive", "Linear", "CAGR", "Damped", "DecelCAGR" — not class
# names). Families share the revenue-layer intuition: DampedTrend is the
# battery's damping/mean-revert translation per its graduation note,
# DecelCAGR the S-curve one. Structural methods (net_growth, incremental)
# get an intuition mapping too — the battery is corroborating evidence,
# the semantics still need a human call.
_FAMILY: Dict[str, Tuple[str, ...]] = {
    "trend": ("Linear", "Damped"),
    "hold": ("Naive",),
    "mean_revert": ("Damped", "Naive"),
    "growth": ("CAGR", "DecelCAGR"),
    "logistic": ("DecelCAGR",),
    "erosion": ("Linear", "Damped"),   # a negative trend is a trend
    "net_growth": ("DecelCAGR", "CAGR"),
    "incremental": ("Linear",),
}

# Driver weights: base and price carry the mechanism signal; the ratio
# drivers are mostly "hold" across profiles and would only dilute the score
_DRIVER_WEIGHT = {"base": 1.0, "price": 0.8, "penetration": 0.2, "share": 0.1}

# Fit-verdict multiplier: when families tie on evidence, prefer the profile
# the engine itself trusts (strong > adapt > weak)
_FIT_MULT = {"strong": 1.0, "adapt": 0.8, "weak": 0.6}

_HYPER_GROWTH = 0.40          # revenue CAGR above this triggers the override
_MIN_POINTS = 4               # battery needs >=3; 4 keeps one real step


@dataclass(frozen=True)
class ProfileSuggestion:
    """One ranked candidate with its evidence lines."""
    key: str
    score: float
    reasons: Tuple[str, ...]

    def label(self) -> str:
        return INDUSTRY_PROFILES[self.key].label_en


def _battery_ranking(years: Sequence[int], values: Sequence[float]
                     ) -> Optional[List[Tuple[str, float]]]:
    """Battery sMAPE ranking for one driver series, best first.

    Returns None when the series is too short to backtest — the honest
    signal is "no evidence", not a fabricated ranking.
    """
    if len(years) < _MIN_POINTS:
        return None
    try:
        steps = rolling_backtest(years, values, _SUGGEST_METHODS,
                                 min_train=2, horizon=1)
    except ValueError:
        return None
    scores = evaluate(steps)
    usable = [s for s in scores if s.n > 0 and s.smape == s.smape]
    if not usable:
        return None
    usable.sort(key=lambda s: s.smape)
    return [(s.name, s.smape) for s in usable]


def _rank_points(ranking: List[Tuple[str, float]],
                 family: Tuple[str, ...]) -> Tuple[float, Optional[str]]:
    """Points for the best-ranked family member (3/2/1/0), plus a reason
    fragment like 'Damped #1 (sMAPE 3.2%)'."""
    for pos, (name, smape) in enumerate(ranking, start=1):
        if name in family:
            pts = max(0, 4 - pos)
            why = f"{name} #{pos} (sMAPE {smape:.1f}%)"
            return pts, why
    return 0.0, None


def suggest_profile(seg: Segment, top_k: int = 3
                    ) -> List[ProfileSuggestion]:
    """Rank industry profiles for an untagged (or any) segment.

    Evidence per profile: (1) how its default extrapolation families rank
    on the segment's own driver histories under the zero-dependency battery;
    (2) whether the segment's revenue CAGR sits inside the profile's sourced
    Damodaran band (v0.18); (3) the hypergrowth override — a segment
    compounding past 40%/yr gets the regime-shift lesson pinned on top.

    Returns the top-k with reasons; the caller still makes the call.
    """
    drivers = {
        "base": seg.base, "penetration": seg.penetration,
        "share": seg.share, "price": seg.price,
    }
    rankings: Dict[str, Optional[List[Tuple[str, float]]]] = {}
    for kind, drv in drivers.items():
        yrs = sorted(drv.values)
        rankings[kind] = _battery_ranking(yrs, [drv.values[y] for y in yrs])

    # recent-3y revenue CAGR for the band bonus + override (same caliber as
    # benchmark_warnings — a full-window CAGR would dilute a late breakout)
    rev_years = sorted(set.intersection(*[
        set(d.values) for d in drivers.values()]))
    rev = {y: seg.revenue(y) for y in rev_years}
    yrs = sorted(rev)[-4:]
    cagr = None
    if len(yrs) >= 2 and rev[yrs[0]] > 0:
        span = yrs[-1] - yrs[0]
        if span > 0:
            cagr = (rev[yrs[-1]] / rev[yrs[0]]) ** (1.0 / span) - 1.0

    scored: List[ProfileSuggestion] = []
    battery_only: Dict[str, float] = {}
    hyper = False
    for profile in INDUSTRY_PROFILES.values():
        reasons: List[str] = []
        score = 0.0
        for kind, spec in profile.defaults.items():
            ranking = rankings.get(kind)
            if ranking is None:
                continue
            family = _FAMILY.get(spec.method)
            if family is None:
                continue
            pts, why = _rank_points(ranking, family)
            score += _DRIVER_WEIGHT[kind] * pts
            # only cite the mechanism-carrying drivers (base/price)
            if pts > 0 and why and _DRIVER_WEIGHT[kind] >= 0.8:
                reasons.append(f"{kind}: default {spec.method} — battery {why}")
        battery_only[profile.key] = score
        # band proximity bonus (v0.18 benchmarks)
        if cagr is not None:
            band = next((b for b in profile.benchmarks
                         if b.metric == "revenue_cagr_5y"), None)
            if band is not None:
                if band.p25 <= cagr <= band.p75:
                    score += 1.5
                    reasons.append(
                        f"revenue CAGR {cagr:+.0%}/yr inside the industry "
                        f"band {band.p25:.0%}-{band.p75:.0%} ({band.vintage})")
                elif abs(cagr - band.p50) <= 0.10:
                    score += 0.5
        # hypergrowth prior (v0.16 lesson) — added AFTER the fit multiplier:
        # the prior matters most exactly where the profile's naive-trend
        # defaults lose on their own history
        if cagr is not None and cagr > _HYPER_GROWTH \
                and profile.key == "regime_shift_tech":
            hyper = True
            reasons.append(
                f"revenue CAGR {cagr:+.0%}/yr is regime-shift territory "
                f"(>{_HYPER_GROWTH:.0%}) — the v0.16 lesson: trends don't "
                f"survive breaks, scenarios do")
        prior = 2.5 if (hyper and profile.key == "regime_shift_tech") else 0.0
        scored.append(ProfileSuggestion(
            profile.key,
            round(score * _FIT_MULT[profile.fit] + prior, 3),
            tuple(reasons)))

    # the band bonus and the hypergrowth prior only *re-rank* battery
    # evidence — with no backtestable history at all, refuse to guess
    if all(v == 0 for v in battery_only.values()):
        return []

    scored.sort(key=lambda s: s.score, reverse=True)
    if hyper:
        # teaching priority: when the prior fires, regime_shift leads the
        # shortlist even if its baseline-trend defaults rank poorly
        first = next((s for s in scored if s.key == "regime_shift_tech"), None)
        if first is not None and scored and first is not scored[0]:
            promoted = first.__class__(
                first.key, round(scored[0].score + 0.1, 3), first.reasons)
            scored = [promoted] + [s for s in scored if s is not first]
    if all(s.score == 0 for s in scored):
        return []   # no evidence at all — refuse to guess (too-short history)
    return scored[:top_k]
