"""auto_pipeline (v0.20a): one call from raw segment data to a report.

The orchestration layer the previous five versions were building toward::

    from revenue_model import auto_pipeline

    result = auto_pipeline(
        company="DemoCo",
        segments={
            "Core": {"base": {2022: 100, 2023: 112, 2024: 124},
                     "price": {2022: 1.0, 2023: 1.02, 2024: 1.03}},
            "AI":   {"base": {2022: 10, 2023: 19, 2024: 36}},
        },
        total_revenue={2022: 110.0, 2023: 131.0, 2024: 160.0},
        years=[2025, 2026],
        tags={"Core": "semiconductor", "AI": "auto"},
    )

Stages: build drivers → suggest profiles → **gate 1 (tags)** → forecast →
citation checks → **gate 2 (out-of-band stories)** → assemble → report.

The two gates are design, not TODO (docs/proposal-auto-pipeline.md):

- **Gate 1 — tags.** A segment is forecast only when its mechanism tag is
  confirmed: explicitly in ``tags``, or the literal ``"auto"`` which adopts
  the suggestion's top candidate *and records the adoption loudly*
  (``auto_tagged``). A segment with neither lands in ``gate1_pending`` and
  is not forecast — unattended runs never guess silently.
- **Gate 2 — out-of-band stories.** When a forecast segment's benchmark
  warning reads ABOVE the industry band, the pipeline requires a story
  entry in ``stories`` (the assumption that beats the industry, in your
  words); otherwise the segment lands in ``gate2_pending`` and the report
  still ships with the warning visible. The point forecast is never
  silently trusted for an above-band extrapolation.

Soft defaults everywhere: every driver value here is just a starting point
— override any of them on the returned segments as always.
"""
import os
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple

from .driver import Driver, BASE, PENETRATION, SHARE, PRICE
from .industry import forecast_segment, segment_warnings
from .model import RevenueModel
from .momentum import MomentumReading
from .segment import Segment
from .suggest import ProfileSuggestion, suggest_profile

_KINDS = (BASE, PENETRATION, SHARE, PRICE)


def _build_segment(name: str, spec: Dict[str, Dict[int, float]]) -> Segment:
    """Raw ``{driver_kind: {year: value}}`` → Segment. Missing ratio/price
    drivers default to a constant 1.0 (two-factor base × price models are
    the common case); base must be present."""
    if BASE not in spec:
        raise ValueError(f"segment {name!r}: a 'base' driver is required")
    base_years = sorted(spec[BASE])

    def series(kind: str) -> Dict[int, float]:
        if kind in spec:
            return dict(spec[kind])
        return {y: 1.0 for y in base_years}      # neutral constant

    return Segment(
        name=name,
        base=Driver(f"{name} base", BASE, dict(spec[BASE]), level="C",
                    unit="units", source="auto_pipeline input"),
        penetration=Driver(f"{name} penetration", PENETRATION,
                           series(PENETRATION), level="C", unit="fraction",
                           source="auto_pipeline default (1.0)"),
        share=Driver(f"{name} share", SHARE, series(SHARE), level="C",
                     unit="fraction", source="auto_pipeline default (1.0)"),
        price=Driver(f"{name} price", PRICE, series(PRICE), level="C",
                     unit="units", source="auto_pipeline input/default"),
    )


@dataclass
class PipelineResult:
    """Everything the pipeline did, and everything still waiting on you."""
    company: str
    model: Optional[RevenueModel]           # None when gate-1 blocked all
    segments: List[Segment]                 # forecast segments only
    suggestions: Dict[str, List[ProfileSuggestion]]
    tags_used: Dict[str, str]               # segment -> profile key
    auto_tagged: Tuple[str, ...]            # gate-1 adoptions (loud)
    gate1_pending: Tuple[str, ...]          # untagged, NOT forecast
    gate2_pending: Tuple[str, ...]          # above-band without a story
    warnings: Dict[str, List[str]] = field(default_factory=dict)
    report_path: Optional[str] = None
    total_source: str = "manual"            # or "SEC EDGAR (auto)"
    # v0.21a quarterly layer: company-level momentum reading (None when
    # quarterly data was unavailable — soft, never blocks the spine)
    momentum: Optional[MomentumReading] = None


def _fetch_total_from_sec(
    ticker: str, years_hint: List[int], *, http_get=None,
    user_agent: str = "", timeout: int = 30,
) -> Tuple[Dict[int, float], int]:
    """ticker -> ({fiscal_year: revenue in million USD}, cik) via the
    sec_adapter (ticker mapping + annual 10-K revenues, disk-cached). The
    cik comes back for reuse by later stages (v0.21a: quarterly momentum).
    Raises ValueError with an actionable message when the ticker is unknown
    or the network is unreachable — degradation is explicit, never silent."""
    from . import sec_adapter
    kwargs = {"http_get": http_get, "timeout": timeout}
    if user_agent:
        kwargs["user_agent"] = user_agent
    try:
        cik, _name = sec_adapter.fetch_cik(ticker, **kwargs)
        rev = sec_adapter.fetch_revenues(cik, **kwargs)
    except (ValueError, OSError) as exc:
        raise ValueError(
            f"could not auto-fetch total revenue for {ticker!r} from SEC "
            f"EDGAR ({exc}). Either fix the ticker/network, or pass "
            f"total_revenue={{year: $M}} by hand.") from exc
    if not rev:
        raise ValueError(
            f"SEC EDGAR returned no annual revenue for {ticker!r}; pass "
            f"total_revenue={{year: $M}} by hand.")
    return ({y: v / 1e6 for y, v in rev.items() if y in years_hint}, cik)


def auto_pipeline(
    company: str,
    segments: Dict[str, Dict[str, Dict[int, float]]],
    total_revenue: Optional[Dict[int, float]] = None,
    years: Optional[List[int]] = None,
    tags: Optional[Dict[str, str]] = None,
    stories: Optional[Dict[str, str]] = None,
    report: Optional[str] = None,
    lang: Literal["zh", "en"] = "en",
    http_get=None,
    user_agent: str = "",
    timeout: int = 30,
    momentum_enabled: bool = True,
) -> PipelineResult:
    """Run the full offline spine: build → suggest → gate 1 → forecast →
    check → gate 2 → assemble → report. See the module docstring for the
    gate contract; nothing here needs an LLM.

    v0.20b: pass ``total_revenue=None`` with a real ticker as ``company``
    and the annual 10-K total revenue is auto-fetched from SEC EDGAR
    (disk-cached; inject ``http_get`` for tests). Failure degrades loudly
    with an actionable message — never silently.

    Note: omitted ratio drivers default to a constant 1.0 ("factor
    absent"). That is fine for hold/trend profiles, but a two-factor
    segment tagged with an S-curve profile (logistic penetration) should
    supply its real adoption curve — a constant 1.0 collides with the
    logistic anchor."""
    if years is None:
        years = []
    if not years:
        raise ValueError("years= (the forecast years) is required")
    tags = tags or {}
    stories = stories or {}

    # -- v0.20b: auto total revenue from SEC EDGAR when not given ----------
    total_source = "manual"
    cik: Optional[int] = None
    if total_revenue is None:
        hist_years = sorted({y for spec in segments.values()
                             for series in spec.values() for y in series})
        total_revenue, cik = _fetch_total_from_sec(
            company, hist_years, http_get=http_get,
            user_agent=user_agent, timeout=timeout)
        if not total_revenue:
            raise ValueError(
                f"SEC EDGAR has no annual revenue overlapping the driver "
                f"years for {company!r}; pass total_revenue by hand.")
        total_source = "SEC EDGAR (auto)"
    total_revenue = dict(total_revenue)

    # -- v0.21a: quarterly momentum (company-level evidence; soft stage) ----
    momentum: Optional[MomentumReading] = None
    if cik is not None and momentum_enabled:
        from .momentum import quarterly_momentum
        try:
            momentum = quarterly_momentum(cik, http_get=http_get,
                                          user_agent=user_agent,
                                          timeout=timeout)
        except (ValueError, OSError):
            momentum = None   # quarterly disclosure missing — soft skip

    built = {name: _build_segment(name, spec) for name, spec in segments.items()}

    # -- suggest (every segment gets its shortlist, tagged or not) ---------
    suggestions: Dict[str, List[ProfileSuggestion]] = {
        name: suggest_profile(seg) for name, seg in built.items()
    }

    # -- gate 1: tags -------------------------------------------------------
    tags_used: Dict[str, str] = {}
    auto_tagged: List[str] = []
    gate1_pending: List[str] = []
    for name in built:
        tag = tags.get(name)
        if tag == "auto":
            shortlist = suggestions.get(name)
            if shortlist:
                tags_used[name] = shortlist[0].key
                auto_tagged.append(name)
            else:
                gate1_pending.append(name)     # nothing backtestable
        elif tag:
            tags_used[name] = tag
        else:
            gate1_pending.append(name)

    # -- forecast + checks on confirmed segments only ------------------------
    forecast_segments: List[Segment] = []
    warnings: Dict[str, List[str]] = {}
    for name, tag in tags_used.items():
        seg = built[name]
        seg.industry = tag                     # gate-1 verdict, before anything
        history_end = max(seg.base.values)
        fc = forecast_segment(seg, years)
        forecast_segments.append(fc)
        seg_warnings = segment_warnings(fc, history_end=history_end)
        if name in stories:
            story = stories[name]
            seg_warnings = [f"{w} [story on file: {story}]" if "ABOVE" in w
                            else w for w in seg_warnings]
        warnings[name] = seg_warnings

    # -- gate 2: above-band without a story ----------------------------------
    gate2_pending = tuple(
        name for name, ws in warnings.items()
        if any("ABOVE the industry band" in w for w in ws)
        and name not in stories
    )

    # -- assemble -------------------------------------------------------------
    model = None
    if forecast_segments:
        model = RevenueModel(company, forecast_segments, total_revenue)

    # -- report (deferred import: python-docx is an extra; the pipeline
    #    itself stays zero-dependency when no report is requested) ----------
    report_path: Optional[str] = None
    if model is not None and report:
        from .docx_builder import build_docx
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        build_docx(model, report, forecast_years=years, lang=lang)
        report_path = report

    return PipelineResult(
        company=company,
        model=model,
        segments=forecast_segments,
        suggestions=suggestions,
        tags_used=tags_used,
        auto_tagged=tuple(auto_tagged),
        gate1_pending=tuple(gate1_pending),
        gate2_pending=gate2_pending,
        warnings=warnings,
        report_path=report_path,
        total_source=total_source,
        momentum=momentum,
    )
