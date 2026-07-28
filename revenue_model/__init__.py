"""revenue-model-builder: bottom-up revenue forecasting framework.

Core abstraction:
    Driver     — a single factor (base / penetration / share / price)
    Segment    — one business line: revenue = base × penetration × share × price
    RevenueModel — multi-segment model anchored to total revenue, with a residual
                 line that absorbs un-modeled business and an alignment check.
"""

from .driver import Driver, BASE, PENETRATION, SHARE, PRICE, LEVEL_A, LEVEL_B, LEVEL_C
from .segment import Segment
from .model import RevenueModel, YearResult

__all__ = [
    "Driver", "Segment", "RevenueModel", "YearResult",
    "BASE", "PENETRATION", "SHARE", "PRICE",
    "LEVEL_A", "LEVEL_B", "LEVEL_C",
]
