"""Macro driver revision — the event -> driver revision -> re-run loop.

Direction-3 (news-impact validation) concluded that upstream signals are
*wave detectors*: their value is triggering driver revisions one to four
quarters before reported revenue — never direct event->revenue regressions.
This module turns that conclusion into code:

1. ``MacroBinding`` declares how an upstream QESA series maps onto a revenue
   driver: channel (demand / cost / fx), an elasticity (pp of driver growth
   per pp of upstream YoY, estimated in the QESA transmission study), a
   transmission lag in quarters, and the forecast window the revision covers.
2. ``suggest_revisions()`` reads recent upstream shocks from a
   :class:`~revenue_model.qesa_adapter.QesaStore` and emits one
   ``RevisionSuggestion`` per binding whose shock clears ``min_shock_pp``.
3. ``apply_revision()`` converts a suggestion into a *new* Driver with the
   same discipline as the extrapolation API: values adjusted, level
   downgraded to C, source tagged with the signal and its evidence.

Everything is a suggestion until a human accepts it — the memo renders the
evidence (shock, elasticity, lag, source) next to the before/after forecast
so the analyst can veto any revision.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from .driver import Driver, LEVEL_C
from .qesa_adapter import QesaStore

__all__ = ["MacroBinding", "RevisionSuggestion", "suggest_revisions",
           "apply_revision"]


@dataclass
class MacroBinding:
    """How one upstream QESA series maps onto one revenue driver.

    Fields
    ------
    series_id : QESA series (e.g. 'PCOPPUSDM' LME copper, 'DEXCHUS' CNY/USD).
    label : human name for memos ('LME铜', '人民币汇率').
    channel : 'demand' (volume driver up with upstream), 'cost' (pass-through
        into unit price), or 'fx' (translation into reporting currency).
    target : driver *name* the revision applies to (must match the model).
    elasticity : pp of target-driver growth per +1pp upstream YoY. Sign
        matters: copper +1pp -> manufacturer unit price +0.08pp (pass-through);
        CNY/USD +1% (depreciation) -> exporter CNY revenue up.
    lag_quarters : transmission lag estimated in the QESA study (1-4).
    window_years : how many forecast years the revision spreads over
        (default 1 — the shock decays within the year it lands).
    note : free-text evidence for the memo (study, beta, sample).
    """

    series_id: str
    label: str
    channel: str
    target: str
    elasticity: float
    lag_quarters: int
    window_years: int = 1
    note: str = ""

    def __post_init__(self):
        if self.channel not in ("demand", "cost", "fx"):
            raise ValueError(f"unknown channel: {self.channel!r}")
        if self.lag_quarters < 0:
            raise ValueError("lag_quarters must be >= 0")


@dataclass
class RevisionSuggestion:
    """A concrete revision candidate for one binding (shock already read)."""

    binding: MacroBinding
    shock_date: str            # ISO date of the triggering observation
    shock_yoy: float           # upstream YoY in pp (or pct for fx)
    shock_delta_pp: float      # change in upstream YoY vs prior period, pp
    implied_pp: float          # elasticity * shock_delta_pp — driver growth pp
    evidence: str = ""

    @property
    def lands_quarter(self) -> str:
        """Rough calendar label of when the revision lands."""
        y, m = int(self.shock_date[:4]), int(self.shock_date[5:7])
        q = (m - 1) // 3 + 1 + self.binding.lag_quarters
        y += (q - 1) // 4
        return f"{y}Q{(q - 1) % 4 + 1}"

    def summary(self, lang: str = "zh") -> str:
        b = self.binding
        if lang == "zh":
            return (f"{b.label} {self.shock_date} YoY {self.shock_yoy:+.1f}pp "
                    f"(Δ{self.shock_delta_pp:+.1f}pp) → {b.target} "
                    f"{self.implied_pp:+.2f}pp/yr, 滞后{b.lag_quarters}季, "
                    f"落地 {self.lands_quarter}")
        return (f"{b.label} {self.shock_date} YoY {self.shock_yoy:+.1f}pp "
                f"(Δ{self.shock_delta_pp:+.1f}pp) -> {b.target} "
                f"{self.implied_pp:+.2f}pp/yr, lag {b.lag_quarters}q, "
                f"lands {self.lands_quarter}")


def suggest_revisions(bindings: Sequence[MacroBinding], store: QesaStore,
                      min_shock_pp: float = 1.0,
                      lookback_obs: int = 3) -> List[RevisionSuggestion]:
    """Scan recent upstream moves and emit one suggestion per triggered binding.

    A binding triggers when the latest observation's *change in YoY*
    (``shock_delta_pp``) clears ``min_shock_pp`` in absolute value — a jump in
    the growth rate, not merely a high level. ``lookback_obs`` observations
    are scanned so a shock one period old is still caught.
    """
    out: List[RevisionSuggestion] = []
    for b in bindings:
        obs = store.series_history(b.series_id, limit=lookback_obs + 1)
        if len(obs) < 2:
            continue
        latest = obs[-1]
        if latest.yoy is None or obs[-2].yoy is None:
            continue
        delta = latest.yoy - obs[-2].yoy
        if abs(delta) < min_shock_pp:
            continue
        out.append(RevisionSuggestion(
            binding=b, shock_date=latest.date, shock_yoy=float(latest.yoy),
            shock_delta_pp=float(delta),
            implied_pp=round(b.elasticity * delta, 4),
            evidence=b.note))
    return out


def apply_revision(driver: Driver, suggestion: RevisionSuggestion,
                   years: List[int]) -> Driver:
    """Apply a suggestion to ``driver`` over ``years`` (forecast years).

    The implied pp is spread over ``binding.window_years`` as a constant
    annual increment to the driver's hold-forward path (relative to the last
    historical value). Mirrors the extrapolation discipline: the returned
    Driver is C-grade and its source carries the full evidence chain.
    """
    if suggestion.binding.target != driver.name:
        raise ValueError(
            f"binding targets {suggestion.binding.target!r}, "
            f"driver is {driver.name!r}")
    last_yr = max(driver.values)
    last_val = driver.values[last_yr]
    b = suggestion.binding
    per_year = suggestion.implied_pp / max(b.window_years, 1)
    new_values = dict(driver.values)
    for i, y in enumerate(sorted(years), start=1):
        cum = per_year * min(i, b.window_years)   # cumulative pp by year i
        if driver.kind in ("penetration", "share"):
            # bounded ratios: 1 pp = +0.01 absolute on the fraction
            new_values[y] = last_val + 0.01 * cum
        else:
            # price/base: pp acts on the growth path (hold-forward baseline)
            new_values[y] = last_val * (1.0 + cum / 100.0)
    src = (f"macro-signal: {b.label} {suggestion.shock_date} "
           f"ΔYoY {suggestion.shock_delta_pp:+.1f}pp × β {b.elasticity:+.3f} "
           f"= {suggestion.implied_pp:+.2f}pp over {b.window_years}yr "
           f"(lag {b.lag_quarters}q, lands {suggestion.lands_quarter})")
    return Driver(driver.name, driver.kind, new_values, level=LEVEL_C,
                  unit=driver.unit, source=src)
