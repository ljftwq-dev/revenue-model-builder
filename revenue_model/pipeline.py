"""Pipeline: annual-report text -> segment skeletons -> RevenueModel.

Implements the semi-automated boundary of
``docs/proposal-segment-extraction.md`` §7: the LLM pulls a segment skeleton
(business lines, revenue, driver_type, hints); filling concrete driver
*values* (C-grade estimates) remains a human step.

:func:`parsed_to_segments` turns the extracted dict into ``Segment`` objects
whose driver ``values`` are placeholders (0.0) tagged with the LLM's hint as
``source`` — so a human knows exactly which number to fill for each driver.
"""
from typing import List

from .driver import Driver, BASE, PENETRATION, SHARE, PRICE
from .segment import Segment
from .templates import get_template


def parsed_to_segments(parsed: dict, year: int) -> List[Segment]:
    """Convert an extracted segment skeleton dict into ``Segment`` placeholders.

    Each segment's ``driver_type`` selects a 4-factor template; driver values
    are 0.0 placeholders (to be filled by a human), and each driver's
    ``source`` records the LLM's hint so the fill-in step is guided.

    ``year`` is the fiscal year the extracted revenue corresponds to.
    """
    segments: List[Segment] = []
    for seg in parsed.get("segments", []) or []:
        dtype = seg.get("driver_type") or "hardware_product"
        try:
            tpl = get_template(dtype)
        except KeyError:
            tpl = get_template("hardware_product")
        hints = seg.get("driver_hints") or {}
        confidence = seg.get("confidence") or "C"

        def _driver(kind: str) -> Driver:
            unit, name_hint = tpl[kind]
            return Driver(
                name=(hints.get(kind) or name_hint),
                kind=kind,
                values={year: 0.0},
                level=confidence,
                unit=unit,
                source=f"[skeleton] {kind} - fill C-grade value",
            )

        segments.append(Segment(
            name=seg["name"],
            base=_driver(BASE),
            penetration=_driver(PENETRATION),
            share=_driver(SHARE),
            price=_driver(PRICE),
        ))
    return segments
