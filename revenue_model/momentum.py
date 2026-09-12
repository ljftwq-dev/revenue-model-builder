"""Quarterly momentum reading (v0.21a) — the quarterly layer.

The analyst reads quarterlies for momentum; this module is that step as a
pipeline stage. Single-quarter revenues roll into a trailing-twelve-month
(TTM) series; the *change* in TTM year-over-year growth is the momentum
signal — the trend extrapolation on annual points cannot see a turning
point that quarterly data already shows.

Design: pure functions on a plain list of single-quarter revenues
(chronological, from `sec_adapter.fetch_fiscal_quarters` or any source);
fewer than 8 quarters → "insufficient" (refuse to guess, as always).
"""
from dataclasses import dataclass
from typing import List, Optional, Sequence

_MOMENTUM_BAND = 0.03   # ±3pp change in YoY counts as a turn; inside = steady


@dataclass(frozen=True)
class MomentumReading:
    """One company-level momentum verdict with its evidence line."""
    state: str                     # accelerating | decelerating | steady | insufficient
    recent_yoy: Optional[float]    # latest TTM YoY (fraction/yr)
    prior_yoy: Optional[float]     # TTM YoY one quarter earlier
    n_quarters: int
    evidence: str = ""


def ttm_series(revs: Sequence[float]) -> List[float]:
    """Rolling 4-quarter totals from single-quarter revenues."""
    out: List[float] = []
    for i in range(len(revs) - 3):
        window = revs[i:i + 4]
        if any(v <= 0 for v in window):
            continue          # a gap quarter poisons its whole TTM window
        out.append(sum(window))
    return out


def detect_momentum(revs: Sequence[float]) -> MomentumReading:
    """Momentum from single-quarter revenues (chronological).

    recent_yoy = TTM now vs TTM 4 quarters ago (i.e. YoY on the latest
    TTM); prior_yoy = the same comparison one step earlier. A swing beyond
    ±3pp between them is a turn; fewer than 9 quarters (6 TTM points) is
    "insufficient".
    """
    n = len(revs)
    if n < 9:
        return MomentumReading(
            "insufficient", None, None, n,
            f"only {n} quarters (<9) — no momentum reading, refuse to guess")
    ttm = ttm_series(revs)
    if len(ttm) < 6:
        return MomentumReading(
            "insufficient", None, None, n,
            "TTM chain broken (gaps) — no momentum reading")
    recent = ttm[-1] / ttm[-5] - 1.0
    prior = ttm[-2] / ttm[-6] - 1.0
    swing = recent - prior
    if swing > _MOMENTUM_BAND:
        state = "accelerating"
    elif swing < -_MOMENTUM_BAND:
        state = "decelerating"
    else:
        state = "steady"
    turn = {"accelerating": "an up-turn annual points cannot see yet — "
                            "trend extrapolation likely UNDERSTATES",
            "decelerating": "a down-turn annual points cannot see yet — "
                            "trend extrapolation likely OVERSTATES",
            "steady": "no turn visible at quarterly granularity"}[state]
    return MomentumReading(
        state, recent, prior, n,
        f"TTM growth {recent:+.0%}/yr vs {prior:+.0%} one quarter earlier "
        f"({swing:+.0%}pp swing) — {turn}")


def quarterly_momentum(cik: int, *, http_get=None, user_agent: str = "",
                       timeout: int = 30) -> MomentumReading:
    """CIK -> momentum reading via SEC quarterly revenue (adapter layer)."""
    from . import sec_adapter
    kwargs = {"http_get": http_get, "timeout": timeout}
    if user_agent:
        kwargs["user_agent"] = user_agent
    quarters = sec_adapter.fetch_fiscal_quarters(cik, **kwargs)
    return detect_momentum([q[3] for q in quarters])
