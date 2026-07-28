"""Driver templates — map a segment's ``driver_type`` to a 4-factor skeleton.

Every business type normalizes to the canonical
``base × penetration × share × price`` tree, but with type-appropriate units and
name hints. Used by :func:`revenue_model.pipeline.parsed_to_segments` to turn an
LLM-extracted segment skeleton into ``Driver`` placeholders.

See ``docs/proposal-segment-extraction.md`` §5 for the mapping rationale.
"""
from typing import Dict, Tuple

from .driver import BASE, PENETRATION, SHARE, PRICE

# Each template maps each driver kind -> (default_unit, name_hint).
# Templates marked "(implicit = 1)" denote factors that collapse to 1 for that
# business type (kept in the tree so the four-factor structure stays uniform).
DriverTemplate = Dict[str, Tuple[str, str]]

DRIVER_TEMPLATES: Dict[str, DriverTemplate] = {
    "hardware_product": {
        BASE: ("million units", "market base (unit sales)"),
        PENETRATION: ("fraction", "attach / penetration rate"),
        SHARE: ("fraction", "market share"),
        PRICE: ("yuan", "ASP (average selling price)"),
    },
    "software_subscription": {
        BASE: ("million customers", "customer / install base"),
        PENETRATION: ("fraction", "adoption rate"),
        SHARE: ("fraction", "market share"),
        PRICE: ("yuan", "ARPU (annual revenue per user)"),
    },
    "service_project": {
        BASE: ("million person-days", "capacity (person-days)"),
        PENETRATION: ("fraction", "utilization rate"),
        SHARE: ("fraction", "market share"),
        PRICE: ("yuan", "price per person-day"),
    },
    "advertising": {
        BASE: ("billion impression-minutes", "traffic (DAU x time)"),
        PENETRATION: ("fraction", "ad load"),
        SHARE: ("fraction", "market share"),
        PRICE: ("yuan per thousand", "eCPM"),
    },
    "financial_interest": {
        BASE: ("billion yuan", "interest-earning assets"),
        PENETRATION: ("fraction", "(implicit = 1)"),
        SHARE: ("fraction", "(implicit = 1)"),
        PRICE: ("fraction", "yield (interest rate)"),
    },
    "retail_store": {
        BASE: ("thousand stores", "store count"),
        PENETRATION: ("fraction", "(implicit = 1)"),
        SHARE: ("fraction", "(implicit = 1)"),
        PRICE: ("million yuan", "sales per store"),
    },
}


def get_template(driver_type: str) -> DriverTemplate:
    """Return the 4-factor template for a driver_type, or raise KeyError."""
    if driver_type not in DRIVER_TEMPLATES:
        raise KeyError(
            f"unknown driver_type: {driver_type!r}; "
            f"expected one of {sorted(DRIVER_TEMPLATES)}")
    return DRIVER_TEMPLATES[driver_type]
