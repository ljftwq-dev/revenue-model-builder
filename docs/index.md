# revenue-model-builder

A **bottom-up revenue forecasting framework** — turn a driver tree
(`market_base × penetration × share × price`) into an **auditable** revenue
model that aligns to reported totals via a structural residual line. Core
engine has **zero third-party dependencies** (pure Python stdlib), including
the Monte Carlo + sensitivity layer.

:material-github: [Source on GitHub](https://github.com/ljftwq-dev/revenue-model-builder)
&nbsp;·&nbsp; :material-package-variant: `pip install revenue-model-builder`

---

## Why

Most open-source finance tooling covers **trading / backtesting**
(zipline, backtrader, QuantLib) or **DCF valuation**. **Driver-based revenue
forecasting** — decomposing revenue into `base × penetration × share × price`,
what sell-side analysts and PE associates actually do — has almost no
open-source presence. This project is a minimal, runnable encoding of that
workflow, with the math enforced in code rather than left to a prompt.

## Core idea

```
segment_revenue = market_base × penetration × share × price
total_revenue   = Σ(segments) + residual          # residual absorbs un-modeled biz
```

The design encodes five hard-won modeling rules — a **structural residual**
that absorbs un-modeled business, **A/B/C data grading** for traceability,
**incremental** (not growth-rate) penetration forecasts, a **certainty
pyramid** for prioritizing forecast inputs, and a **history-first** workflow.

## Quick start

```python
from revenue_model import Driver, Segment, RevenueModel, BASE, PENETRATION, SHARE, PRICE

seg = Segment(
    name="cockpit-domestic",
    base=Driver("China passenger car sales", BASE, {2022: 22.0, 2023: 23.0},
                level="A", unit="million units", source="CAAM"),
    penetration=Driver("DMS penetration", PENETRATION, {2022: 0.04, 2023: 0.06},
                       level="B", unit="fraction", source="research institute"),
    share=Driver("market share", SHARE, {2022: 0.10, 2023: 0.12},
                 level="C", unit="fraction", source="estimate"),
    price=Driver("ASP", PRICE, {2022: 600, 2023: 620},
                 level="C", unit="yuan", source="benchmark"),
)
model = RevenueModel("DemoCo", [seg], total_revenue={2022: 110.0, 2023: 215.0})

for r in model.validate_all():
    print(r.year, f"segments={r.segment_sum:.1f}", f"residual={r.residual:.1f}", r.warnings)
```

!!! tip "CLI"
    Once installed: `python -m revenue_model {build, simulate, excel, extract}`.

## Documentation

- :material-scale-balance: **[Design Principles](design-principles.md)** — the five hard-won modeling rules (residual, ABC grading, incremental penetration, certainty pyramid, history-first)
- :material-file-document-outline: **[Segment Extraction Proposal](proposal-segment-extraction.md)** — annual-report → segment skeleton pipeline
- :material-chart-line: **[Stochastic Revenue Design](plans/2026-07-28-stochastic-revenue-design.md)** — v0.2→v0.3 roadmap (Monte Carlo → financial stochastic processes)

## Uncertainty

Turn point forecasts into **distributions** and find out **which assumption
matters most** — pure stdlib, no numpy:

```python
from revenue_model import simulate_model, tornado

mc = simulate_model(model, 2024, {"market share": (0.10, 0.18)}, n=20000, seed=0)
print(mc.median, mc.percentiles["p5"], mc.percentiles["p95"])
```

---

*Research / education tool, not investment advice. See
[DISCLAIMER](https://github.com/ljftwq-dev/revenue-model-builder/blob/main/DISCLAIMER.md).*
