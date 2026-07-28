# revenue-model-builder

[![CI](https://github.com/ljftwq-dev/revenue-model-builder/actions/workflows/ci.yml/badge.svg)](https://github.com/ljftwq-dev/revenue-model-builder/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![Dependencies: zero](https://img.shields.io/badge/dependencies-0-success.svg)](#install)

**中文文档：[README-zh.md](README-zh.md)**

A **bottom-up revenue forecasting framework** — turn a driver tree
(`market_base × penetration × share × price`) into an **auditable** revenue
model that aligns to reported totals via a structural residual line. Core
engine has **zero third-party dependencies** (pure Python stdlib), including the
Monte Carlo + sensitivity layer.

The design encodes five hard-won modeling rules (see
[design principles](docs/design-principles.md)): a **structural residual** that
absorbs un-modeled business, **A/B/C data grading** for traceability,
**incremental** (not growth-rate) penetration forecasts, a **certainty
pyramid** for prioritizing forecast inputs, and a **history-first** workflow.

---

## Why

Most open-source finance tooling covers **trading / backtesting** (zipline,
backtrader, QuantLib) or **DCF valuation**. **Driver-based revenue forecasting**
— decomposing revenue into `base × penetration × share × price`, what sell-side
analysts and PE associates actually do — has almost no open-source presence.

The closest neighbors are TAM/SAM/SOM **prompt skills** for AI agents
(e.g. `slgoodrich/agents`, `deanpeters/Product-Manager-Skills`) — they describe
the methodology in natural language, but **none is a runnable engine**. This
project is: a minimal, pip-installable encoding of the workflow with the
math enforced in code rather than left to a prompt.

A sell-side revenue model lives or dies on whether you can defend *every*
number — "where did this penetration come from? why isn't it higher?" Manual
spreadsheets answer that with cryptic comments. `revenue-model-builder` makes
it structural: every driver carries a credibility grade and a source, the
residual is a first-class line, and an alignment check catches the classic
"back-solved penetration" trap before it poisons the forecast.

## How it compares

| | revenue-model-builder | market-sizing SKILLs | DCF valuation libs |
|---|---|---|---|
| Runnable code engine | ✅ | ❌ prompt only | ✅ |
| Focus | revenue build-up | market size (TAM/SAM/SOM) | intrinsic value |
| Aligns to reported total (residual) | ✅ structural | ❌ | n/a |
| A/B/C data grading per number | ✅ | ❌ | ❌ |
| Uncertainty (Monte Carlo + tornado) | ✅ | ❌ | sometimes |
| Core dependency footprint | **zero** | n/a | usually numpy + data API |

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

**Render the model to a formatted .xlsx** (needs the `[excel]` extra):

```bash
python -m revenue_model.excel_builder output.xlsx
```

## Monte Carlo & sensitivity

Turn point forecasts into **distributions** and find out **which assumption
matters most** — pure stdlib, no numpy:

```python
from revenue_model import simulate_model, tornado

# Revenue distribution: sample uncertain drivers, multiply, repeat
mc = simulate_model(model, 2024, {
    "market share": (0.10, 0.18),      # C-grade, wide band
    "ASP": (620, 680),
}, n=20000, seed=0)
print(mc.median, mc.percentiles["p5"], mc.percentiles["p95"])  # P5/median/P95

# Tornado: per-driver bands (NOT a uniform %) -> ranked swing
for it in tornado(seg, 2024, {
    "China passenger car sales": (23.5, 24.5),   # A-grade, narrow
    "DMS penetration": (0.07, 0.12),             # B-grade
    "market share": (0.10, 0.18),                # C-grade, wide
    "ASP": (620, 680),
}):
    print(f"{it.driver:28s} swing {it.swing:.1f}")
```

> **Why per-driver bands, not a uniform ±%?** Revenue is a *product*
> (`base × pen × share × price`), so perturbing every factor by the same
> percentage yields **identical swings** — the tornado would have zero
> discriminating power. A tornado is only meaningful when each band reflects
> that driver's real uncertainty: narrow for A-grade hard data, wide for
> C-grade estimates. (This is why A/B/C grading and sensitivity are linked.)

## Segment extraction (from annual reports)

Automate the tedious part of segment build-up — pull a **segment skeleton**
(business lines, revenue, share, YoY, margin, a driver-type tag, driver hints)
out of an annual report's "main business analysis" text via an LLM. Pure stdlib
HTTP (no SDK); the LLM call is injectable, so tests/CI need no API key.

```python
from revenue_model import extract_segments, alignment_check

# text = the "main business analysis" section (extracted upstream via PyMuPDF)
parsed = extract_segments(text, api_key="<your-llm-key>")   # load via secrets manager
print(parsed["segments"])                                   # segment skeletons
print(alignment_check(parsed))                             # Σ + residual ≈ reported total
```

The output matches the schema in
[docs/proposal-segment-extraction.md](docs/proposal-segment-extraction.md) §4.
Filling concrete driver *values* (C-grade estimates) remains a human step — see
the proposal's semi-automated boundary (§7). **Real-company data must not enter
the repo** (see [DISCLAIMER.md](DISCLAIMER.md)); demos use the fictional NovaTech.

## Design principles

| # | Principle | What it prevents |
|---|---|---|
| 1 | **Residual is structural, never back-solved** | Inflating penetration to "tie out" poisons the forecast |
| 2 | **A/B/C data grading** | Opaque spreadsheets — every number is traceable |
| 3 | **Incremental, not growth-rate, for penetration** | Bounded ratios exploding exponentially |
| 4 | **Forecast certainty pyramid** | Treating all inputs as equally knowable |
| 5 | **History first, then forecast** | Forecasting before the model reproduces history |

Plus a validation layer (triangulation, assumption documentation, S-curves):
**[docs/design-principles.md](docs/design-principles.md)**.

## API

```python
Driver(name, kind, values, level="C", unit="", source="")
#   kind ∈ {BASE, PENETRATION, SHARE, PRICE};  level ∈ {"A","B","C"}

Segment(name, base, penetration, share, price)
#   .revenue(year) -> float  (million yuan)

implied_driver(segment, year, target_revenue, solve_kind) -> float
#   calibrate one driver to a known revenue (e.g. reported segment revenue);
#   prefer solve_kind=PRICE/BASE over PENETRATION (avoids the back-solve trap)

RevenueModel(company, segments, total_revenue)
#   .validate(year)  -> YearResult   (segment_revenues, residual, warnings)
#   .validate_all()  -> list[YearResult]

simulate_segment(segment, year, ranges, n=10000, seed=0) -> MCResult
simulate_model(model, year, ranges, n=10000, seed=0)     -> MCResult
#   ranges: {driver_name: (low, high)};  MCResult has mean/median/stdev/percentiles

tornado(segment, year, ranges) -> list[SensitivityItem]   # ranked by swing

scenarios(mc, *, bear_p=0.10, bull_p=0.90) -> list[Scenario]  # Bear/Base/Bull from the distribution

extract_segments(text, *, api_key=None, llm=None) -> dict  # segment skeleton from annual report
alignment_check(parsed) -> dict                            # Σ + residual ≈ reported total
```

## Project structure

```
revenue-model-builder/
├── revenue_model/
│   ├── driver.py        # Driver — one factor (base/pen/share/price) + ABC grade
│   ├── segment.py       # Segment — revenue = base × pen × share × price
│   ├── model.py         # RevenueModel — residual + alignment validation
│   ├── monte_carlo.py   # revenue distribution + tornado sensitivity (pure stdlib)
│   ├── extractor.py     # annual-report text -> segment skeleton (LLM, pure stdlib)
│   ├── excel_builder.py # render to .xlsx (ABC colors, IF formulas, residual)
│   └── demo.py          # NovaTech fictional example
├── tests/               # 35 tests — formula, validation, residual, MC, tornado, extractor
├── docs/
│   └── design-principles.md
└── pyproject.toml
```

## Roadmap

- [x] Monte Carlo revenue distribution + sensitivity (tornado) analysis
- [x] Segment skeleton extraction from annual-report text (LLM)
- [ ] Driver value estimation (C-grade, from industry data)
- [x] Bear / Base / Bull scenarios (sliced from the Monte Carlo distribution)
- [ ] Multi-market data source adapters (A股 tushare / US yfinance / HK)
- [ ] Automated driver extraction from annual-report text
- [ ] Word memo builder (historical + forecast narrative)
- [ ] PyPI release

## Who is this for

Sell-side research, PE/VC investment teams, equity analysts, and students of
fundamental analysis who want a **reusable, auditable** revenue-modeling
scaffold rather than rebuilding the same spreadsheet structure by hand.

## License & disclaimer

MIT — see [LICENSE](LICENSE). This is a **research/education tool, not investment
advice** — full statement in [DISCLAIMER.md](DISCLAIMER.md).
