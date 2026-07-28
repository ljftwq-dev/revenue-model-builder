# revenue-model-builder

[![CI](https://github.com/ljftwq-dev/revenue-model-builder/actions/workflows/ci.yml/badge.svg)](https://github.com/ljftwq-dev/revenue-model-builder/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)

**中文文档：[README-zh.md](README-zh.md)**

A **bottom-up revenue forecasting framework** — turn a driver tree
(`market_base × penetration × share × price`) into an **auditable** revenue
model that aligns to reported totals via a structural residual line.

> Most open-source finance tools cover trading/backtesting (zipline,
> backtrader, QuantLib). **Driver-based revenue forecasting** — what sell-side
> analysts and PE associates actually do — has almost no open-source presence.
> This fills that gap with a minimal, runnable encoding of the workflow.

The design encodes five hard-won modeling rules (see
[design principles](docs/design-principles.md)): a **structural residual** that
absorbs un-modeled business, **A/B/C data grading** for traceability,
**incremental** (not growth-rate) penetration forecasts, a **certainty
pyramid** for prioritizing forecast inputs, and a **history-first** workflow.

---

## Why

A sell-side revenue model lives or dies on whether you can defend *every
number* — "where did this penetration come from? why isn't it higher?" Manual
spreadsheets answer that with cryptic comments. `revenue-model-builder` makes
it structural: every driver carries a credibility grade and a source, the
residual is a first-class line, and an alignment check catches the classic
"back-solved penetration" trap before it poisons the forecast.

## Core idea

```
segment_revenue = market_base × penetration × share × price
total_revenue   = Σ(segments) + residual          # residual absorbs un-modeled biz
```

Unit derivation: base in **million units** × price in **yuan** = **million
yuan** (when penetration & share are fractions in [0,1]). So `Segment.revenue()`
returns million yuan by construction.

## Install

```bash
pip install -e .                  # core engine only (pure stdlib, zero deps)
pip install -e ".[excel]"         # + openpyxl, to render .xlsx output
pip install -e ".[dev]"           # + pytest, to run the test suite
```

## Quick start

**Build a model and validate it aligns to reported totals:**

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
    print(r.year, f"segments={r.segment_sum:.1f}", f"residual={r.residual:.1f}",
          f"({r.residual_ratio:.0%})", r.warnings)
```

**Run the fictional demo** (NovaTech, an automotive-AI company — all data fabricated):

```bash
python -m revenue_model.demo
```

```
--- 2024 ---
  舱内-国内      :    218.4 百万元
  舱内-海外      :    120.0 百万元
  Σ 分项        :    338.4
  差额行        :     71.6  (17.5%)
  总收入        :    410.0
  [ok] 对齐通过（Σ分项 + 差额 = 总收入）
```

**Render the model to a formatted .xlsx** (needs the `[excel]` extra):

```bash
python -m revenue_model.excel_builder output.xlsx
```

The Excel output implements A/B/C color coding (black/blue/red), IF-protected
revenue formulas, the residual line, and an orange-tinted forecast area left
blank until the historical model ties out.

## Design principles

| # | Principle | What it prevents |
|---|---|---|
| 1 | **Residual is structural, never back-solved** | Inflating penetration to "tie out" poisons the forecast |
| 2 | **A/B/C data grading** | Opaque spreadsheets — every number is traceable |
| 3 | **Incremental, not growth-rate, for penetration** | Bounded ratios exploding exponentially |
| 4 | **Forecast certainty pyramid** | Treating all inputs as equally knowable |
| 5 | **History first, then forecast** | Forecasting before the model reproduces history |

Full reasoning + numerical examples: **[docs/design-principles.md](docs/design-principles.md)**.

## API

```python
Driver(name, kind, values, level="C", unit="", source="")
#   kind ∈ {BASE, PENETRATION, SHARE, PRICE};  level ∈ {"A","B","C"}

Segment(name, base, penetration, share, price)
#   .revenue(year) -> float  (million yuan)

RevenueModel(company, segments, total_revenue)
#   .validate(year)  -> YearResult   (segment_revenues, residual, warnings)
#   .validate_all()  -> list[YearResult]
```

## Project structure

```
revenue-model-builder/
├── revenue_model/
│   ├── driver.py        # Driver — one factor (base/pen/share/price) + ABC grade
│   ├── segment.py       # Segment — revenue = base × pen × share × price
│   ├── model.py         # RevenueModel — residual + alignment validation
│   ├── excel_builder.py # render to .xlsx (ABC colors, IF formulas, residual)
│   └── demo.py          # NovaTech fictional example
├── tests/               # 10 tests — formula, validation, residual invariants
├── docs/
│   └── design-principles.md
└── pyproject.toml
```

## Roadmap

- [ ] Multi-market data source adapters (A股 tushare / US yfinance / HK)
- [ ] Automated driver extraction from annual-report text
- [ ] Word memo builder (historical + forecast narrative, as the original skill does)
- [ ] Forecast helper enforcing incremental-penetration (Principle 3)
- [ ] PyPI release

## Who is this for

Sell-side research, PE/VC investment teams, equity analysts, and students of
fundamental analysis who want a **reusable, auditable** revenue-modeling
scaffold rather than rebuilding the same spreadsheet structure by hand.

## License

MIT — see [LICENSE](LICENSE).
