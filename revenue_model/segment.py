"""Segment — one business line whose revenue = base × penetration × share × price,
or an A-grade reported anchor when available."""

from dataclasses import dataclass, field
from typing import Dict, List

from .driver import Driver, DriverKind, BASE, PENETRATION, SHARE, PRICE


@dataclass
class Segment:
    name: str
    base: Driver
    penetration: Driver
    share: Driver
    price: Driver
    # A-grade reported segment revenue (million yuan/USD), e.g. pulled from a
    # 10-K / IR supplemental / stockanalysis.com. When present for a year,
    # revenue() returns it directly (history-first, Principle 5) instead of the
    # driver product — the drivers stay as the forecast layer for years without
    # a reported figure. Backward compatible (defaults to empty).
    reported_revenue: Dict[int, float] = field(default_factory=dict)

    def __post_init__(self):
        kinds = {d.kind for d in self.drivers()}
        expected = {BASE, PENETRATION, SHARE, PRICE}
        missing = expected - kinds
        if missing:
            raise ValueError(f"segment {self.name!r} missing driver kinds: {missing}")
        if len({d.name for d in self.drivers()}) != 4:
            raise ValueError(f"segment {self.name!r}: drivers must have unique names")

    def revenue(self, year: int) -> float:
        """Segment revenue for ``year``.

        A-grade reported anchor takes precedence when available (history-first,
        Principle 5); otherwise the driver product ``base × penetration × share × price``.

        Unit: million yuan/USD (the anchor's unit; the driver product derives
        (M units) × yuan = million yuan when ratios are fractions in [0,1]).
        """
        if year in self.reported_revenue:
            return self.reported_revenue[year]
        return (
            self.base.get(year)
            * self.penetration.get(year)
            * self.share.get(year)
            * self.price.get(year)
        )

    def revenue_source(self, year: int) -> str:
        """'reported' (A-grade anchor) or 'drivers' (product) — for transparency."""
        return "reported" if year in self.reported_revenue else "drivers"

    def drivers(self) -> List[Driver]:
        return [self.base, self.penetration, self.share, self.price]


def implied_driver(segment: Segment, year: int, target_revenue: float,
                   solve_kind: DriverKind) -> float:
    """Given ``target_revenue`` and the other three drivers, solve for the driver
    of ``solve_kind``. An analyst's calibration tool: anchor the three drivers
    you have data for, then align the fourth to a known revenue figure (e.g. the
    segment revenue reported in the annual report).

    Example: you know market base, penetration, and share from industry data,
    plus the reported segment revenue -> the implied unit price.

    .. caution::
        Avoid ``solve_kind=PENETRATION``. Back-solving penetration to force the
        model to tie out is exactly the trap design Principle 1 warns against:
        the distorted value then poisons the forecast. Prefer solving PRICE or
        BASE — the ones you can anchor to external data.
    """
    prod = 1.0
    for d in segment.drivers():
        if d.kind != solve_kind:
            prod *= d.get(year)
    return target_revenue / prod
