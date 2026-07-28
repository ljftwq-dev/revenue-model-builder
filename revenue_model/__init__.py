"""revenue-model-builder: bottom-up revenue forecasting framework.

Core abstraction:
    Driver     — a single factor (base / penetration / share / price)
    Segment    — one business line: revenue = base × penetration × share × price
    RevenueModel — multi-segment model anchored to total revenue, with a residual
                 line that absorbs un-modeled business and an alignment check.
"""

from .driver import (
    Driver, BASE, PENETRATION, SHARE, PRICE,
    LEVEL_A, LEVEL_B, LEVEL_C, DriverKind, DataLevel,
)
from .segment import Segment, implied_driver
from .model import RevenueModel, YearResult
from .monte_carlo import (
    MCResult, SensitivityItem, Scenario,
    simulate_segment, simulate_model, tornado, scenarios,
)
from .extractor import (
    DRIVER_TYPES, build_prompt, parse_segments, extract_segments, alignment_check,
)

__all__ = [
    "Driver", "Segment", "RevenueModel", "YearResult", "implied_driver",
    "BASE", "PENETRATION", "SHARE", "PRICE",
    "LEVEL_A", "LEVEL_B", "LEVEL_C",
    "DriverKind", "DataLevel",
    "MCResult", "SensitivityItem", "Scenario",
    "simulate_segment", "simulate_model", "tornado", "scenarios",
    "DRIVER_TYPES", "build_prompt", "parse_segments",
    "extract_segments", "alignment_check",
]
