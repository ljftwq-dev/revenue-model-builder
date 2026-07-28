"""Segment — one business line whose revenue = base × penetration × share × price."""

from dataclasses import dataclass
from typing import List

from .driver import Driver, BASE, PENETRATION, SHARE, PRICE


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
