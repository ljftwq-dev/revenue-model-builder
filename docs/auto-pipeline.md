# auto_pipeline cookbook

One call from raw segment data to a report — the v0.20 orchestration layer.
This page is the user-facing how-to; the design contract lives in
[the proposal](proposal-auto-pipeline.md).

## Quickstart

```python
from revenue_model import auto_pipeline

result = auto_pipeline(
    company="DemoCo",
    segments={
        "Core": {"base": {2021: 89.0, 2022: 100.0, 2023: 112.0, 2024: 124.0},
                 "price": {2021: 0.99, 2022: 1.0, 2023: 1.02, 2024: 1.03}},
        "AI":   {"base": {2021: 5.0, 2022: 10.0, 2023: 19.0, 2024: 36.0}},
    },
    total_revenue={2021: 94.0, 2022: 110.0, 2023: 131.0, 2024: 160.0},
    years=[2025, 2026],
    tags={"Core": "semiconductor", "AI": "auto"},
)
```

Every stage runs offline — no network, no LLM. `result` carries the model,
per-segment suggestions, warnings, gates state, and (if requested) the
report path.

## Input format

`segments` maps a segment name to its raw drivers:

- `base` is required — the quantity driver (shipments, customers, stores).
- `penetration` / `share` / `price` are optional; omitted ones default to a
  constant 1.0 ("factor absent"). A two-factor `base × price` model is the
  common case.
- ⚠️ If you tag a segment with an S-curve profile (`saas_subscription`'s
  logistic penetration), supply the real adoption curve — a constant 1.0
  collides with the logistic anchor.

## The two gates

**Gate 1 — tags.** A segment is only forecast when its mechanism tag is
confirmed: explicitly in `tags`, or the literal `"auto"` which adopts the
suggestion's top candidate and records the adoption in
`result.auto_tagged` (loud by design). Untagged segments park in
`gate1_pending` and are **not** forecast — unattended runs never guess
silently.

**Gate 2 — out-of-band stories.** When a segment's citation warning reads
ABOVE the industry band, pass its assumption in `stories` (your words for
why it beats the industry); otherwise the segment lands in `gate2_pending`
and the report still ships with the warning visible. Point forecasts are
never silently trusted for above-band extrapolations.

## Then override — always allowed

Pipeline output is a *starting point with evidence*, not a verdict. The
returned segments are ordinary `Segment` objects:

```python
comm = next(s for s in result.segments if s.name == "Commercial")
comm.base = comm.base.fit_trend(sorted(comm.base.values)).extrapolate([2025, 2026])
```

Defaults gave you a defensible floor; the override is the analyst's call
(the v0.16 soft-default rule, unchanged).

## End-to-end example

`examples/pltr_demo/pltr_demo.py` — real FY2021–24 10-K disclosure,
Government (explicit tag) + Commercial (auto-adopted subscriber family),
both gates exercised, `.docx` report, and a hand override to close.
