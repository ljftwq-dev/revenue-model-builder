"""Segment — one business line whose revenue = base × penetration × share × price."""

from dataclasses import dataclass
from typing import List

from .driver import Driver, DriverKind, BASE, PENETRATION, SHARE, PRICE


@dataclass
class Segment:
    name: str
    base: Driver
    penetration: Driver
    share: Driver
    price: Driver

    def __post_init__(self):
        kinds = {d.kind for d in self.drivers()}
        expected = {BASE, PENETRATION, SHARE, PRICE}
        missing = expected - kinds
        if missing:
            raise ValueError(f"segment {self.name!r} missing driver kinds: {missing}")
        if len({d.name for d in self.drivers()}) != 4:
            raise ValueError(f"segment {self.name!r}: drivers must have unique names")

    def revenue(self, year: int) -> float:
        """Revenue (in million yuan) = base(M units) × penetration × share × price(yuan).

        Unit derivation: (M units) × yuan = million yuan, when penetration & share
        are fractions in [0, 1].
        """
        return (
            self.base.get(year)
            * self.penetration.get(year)
            * self.share.get(year)
            * self.price.get(year)
        )

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
