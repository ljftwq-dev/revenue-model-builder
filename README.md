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
pip install -e ".[docx]"          # + python-docx & matplotlib, to render .docx memos
pip install -e ".[dev]"           # + pytest, to run the test suite
pip install -e ".[backtest]"      # + statsmodels, for Holt/ARIMA backtesting
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

**Render the model to a Word research memo (.docx)** (needs the `[docx]` extra):

> **Language**: the memo is bilingual — `lang="en"` (default, for the global /
> PyPI audience) or `lang="zh"` (中文版). Every memo carries a footnote showing
> the active language and how to switch.

```python
from revenue_model.docx_builder import build_docx

build_docx(model, "memo.docx", lang="en")            # English (default)
build_docx(model, "memo_zh.docx", lang="zh")         # 中文版
```

Or via CLI:

```bash
python -m revenue_model docx -o memo.docx --lang en      # default
python -m revenue_model docx -o memo.docx --lang zh      # 中文版
python -m revenue_model docx -o memo.docx --no-charts    # tables only (skip matplotlib)
```

The 7-section memo — Executive Summary → Company & Segment Overview →
ABC-graded Driver Tables → Residual Alignment → Uncertainty & Scenarios (with
embedded Monte Carlo distribution / tornado / forecast charts) → Limitations →
Methodology — is the **narrative** counterpart to the Excel **working paper**.
Two honest defaults: `ranges=None` flags the default ±10% Monte Carlo bands as
illustrative; `forecast_years=None` produces a historical-only memo (or a
`[not yet populated]` alarm if passed unfilled) — never silent.

**Build a model from tushare (A-share, NEV / intelligent-driving)**:

The structured-data adapter auto-fills `total_revenue` from tushare's income
statement and seeds intelligent-driving segment drivers from an industry
template (智能驾驶 / 智能座舱; values are `[adapter]` placeholders for you to
fill — the machine gives the anchor + structure, the analyst fills the
C-grade driver values).

```python
from revenue_model.tushare_adapter import build_model_from_tushare
# load token via your secrets manager; never hardcode
model = build_model_from_tushare("002405.SZ", token=TUSHARE_TOKEN)
```

Or via CLI:

```bash
TUSHARE_TOKEN=... python -m revenue_model tushare 002405.SZ
python -m revenue_model tushare 002405.SZ --token ... --years 2020 2021 2022
```

Verified end-to-end on 德赛西威 (002405.SZ): 20 years of real revenue pulled
and aligned as the residual anchor.

**US equities via SEC EDGAR** (no key needed — SEC is public):

```python
from revenue_model.sec_adapter import build_model_from_sec
model = build_model_from_sec("NVDA")   # US ticker
```

**HK equities via AKShare** (needs the `[data]` extra):

```python
from revenue_model.akshare_adapter import build_model_from_akshare
model = build_model_from_akshare("01211")   # HK code, e.g. 比亚迪股份
```

Or via CLI: `python -m revenue_model sec NVDA` / `akshare 01211`.

**Reported segment revenue via stockanalysis.com** (needs the `[scrape]` extra — playwright; SEC XBRL segment tags vary per issuer, so this fills the gap `sec_adapter` leaves):

```python
from revenue_model.sa_adapter import build_model_from_sa
model = build_model_from_sa("NVDA")   # pulls Compute & Networking + Graphics
```

The three total-revenue adapters (`tushare` / `sec` / `akshare`) fill `total_revenue`
from structured official sources and seed intelligent-driving segment drivers as
placeholders. The segment adapter (`sa`) additionally fills each Segment's
`reported_revenue` A-grade anchor (history-first, Principle 5); drivers stay as
the forecast layer a human fills. Verified: NVDA FY22-FY26, Σ reported segments == total.

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

## Stochastic processes (experimental)

Upgrade uniform-sampling Monte Carlo to **driver-specific stochastic processes** —
pure stdlib, no numpy. Prices follow geometric Brownian motion; bounded ratios
(penetration, share) follow a logit-OU process that stays in (0, 1); drivers
can be correlated via Cholesky.

```python
from revenue_model.stochastic import (
    GBMDriver, LogitOUDriver, CorrelatedBundle, simulate_revenue, logit)

price = GBMDriver("ASP", S0=650.0, mu=0.03, sigma=0.10)                # log-normal price
share = LogitOUDriver("market share", p0=0.14, theta=2.0,
                      mu_bar=logit(0.18), sigma=0.10)                  # bounded, mean-reverting
bundle = CorrelatedBundle([price, share], rho=[[1.0, -0.3], [-0.3, 1.0]])

mc = simulate_revenue(segment, 2024, bundle, n=20000, seed=0)         # -> MCResult
print(mc.median, mc.percentiles["p5"], mc.percentiles["p95"])
```

See [design principles: stochastic layer](docs/design-principles.md#stochastic-layer)
for the SDEs and why logit-OU keeps bounded ratios bounded.

> Experimental — the uniform Monte Carlo above remains the default. See
> [`tests/test_stochastic.py`](tests/test_stochastic.py) for analytic-solution
> validation (GBM mean, OU stationary variance, induced correlation).

## Backtesting

How accurate is a revenue forecast, really? The `backtest` extra answers that
with **honest out-of-sample evaluation** — fit on history, predict the next
year, slide the window forward, and never let a method see the value it must
predict.

Five methods head-to-head: **Naive** (random walk — the benchmark to beat),
**Linear** trend, **CAGR** (log-linear / constant-growth), **Holt** exponential
smoothing, and **ARIMA**. Pure-stdlib metrics (`sMAPE` / `MAPE` / `MAE` / `RMSE`
/ R² / directional accuracy); `sMAPE` is the headline number because it stays
robust across companies of very different sizes. `Naive` / `Linear` / `CAGR`
need nothing; `Holt` / `ARIMA` lazy-import statsmodels.

```python
from revenue_model.backtest import (
    Naive, LinearTrend, LogLinearCAGR, HoltLinear, ARIMA,
    rolling_backtest, evaluate, score_table,
)

steps = rolling_backtest(
    years, values,
    [Naive(), LinearTrend(), LogLinearCAGR(), HoltLinear(), ARIMA()],
    min_train=8, horizon=1)
print(score_table(evaluate(steps)))
```

Real A-share data loads through the `data` extra (akshare, cached as CSV for
reproducibility). **Ten companies spanning six growth regimes**:

| method | avg sMAPE | wins (best / 10) |
|---|---|---|
| **Holt / ARIMA** (adaptive) | **~14%** | **10 / 10** |
| Naive | 21% | 0 |
| Linear / CAGR (fixed trend) | 36% / 31% | 0 |

![sMAPE heatmap — company × method](examples/backtest_demo/heatmap_smape.png)

> **What this teaches about the framework itself.** On the revenue *total*
> level, adaptive statistical methods dominate fixed trends — high-growth
> names grow exponentially, so a linear fit systematically under-predicts and
> even gets the *direction* wrong. The value of the **driver decomposition**
> is therefore *not* "guess the total more accurately" (statistics does that
> better) but **locating structure**: which segment rides a trend and which
> rides a one-off event (e.g. Luxun's 2025 Leoni acquisition — invisible to any
> aggregate method). Accuracy and interpretability are complements, not
> substitutes. See [`examples/backtest_demo/`](examples/backtest_demo/).

## NVIDIA demo — where driver trees work, and where they break

The first **U.S.-equity** demo. NVIDIA is a deliberately two-faced test: **same
company, same `base × penetration × share × price` tree, same engine** — Gaming
hold-out **sMAPE 1.0%** (mature trend market) vs Data Center **60%** (AI regime
shift; FY2025 actual $115.2B vs forecast $18.4B). The demo then closes the loop
with a Monte Carlo scenario band whose Bull tail frames the actual where the
point forecast collapsed.

![NVIDIA Gaming vs Data Center — actual vs driver extrapolation](examples/nvda_demo/nvda_backtest.png)

> Accuracy is a property of the **industry**, not the model. See
> [`examples/nvda_demo/`](examples/nvda_demo/) and the flagship methodology doc
> [`docs/industry-fit-analysis.md`](docs/industry-fit-analysis.md) — the
> industry-fit matrix, five techniques for event-driven growth, and why this
> library chooses honesty over false precision.

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
the proposal's semi-automated boundary (§7). **Proprietary / non-public
company data must not enter the repo**; real-company demos (Luxun, NVIDIA) use
only public disclosures (see [DISCLAIMER.md](DISCLAIMER.md)). The fictional
NovaTech is the zero-real-data default.

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
│   ├── docx_builder.py  # render to .docx research memo (bilingual, ABC, charts)
│   ├── backtest/        # out-of-sample backtesting (metrics / methods / rolling / data)
│   └── demo.py          # NovaTech fictional example
├── tests/               # 154 tests — formula, validation, residual, MC, tornado, extractor, backtest, docx, i18n, tushare/sec/akshare/sa adapters
├── docs/
│   └── design-principles.md
└── pyproject.toml
```

## Roadmap

- [x] Monte Carlo revenue distribution + sensitivity (tornado) analysis
- [x] Segment skeleton extraction from annual-report text (LLM)
- [x] Driver extrapolation API (incremental / logistic / trend-fit)
- [ ] Driver value estimation (C-grade, from industry data)
- [x] Bear / Base / Bull scenarios (sliced from the Monte Carlo distribution)
- [x] Multi-market data source adapters (A股 tushare / 美股 SEC EDGAR / 港股 AKShare)
- [ ] Automated driver extraction from annual-report text
- [x] Reported segment-revenue adapter (stockanalysis.com via playwright, [scrape] extra)
- [x] Word memo builder (.docx research memo, bilingual, with embedded charts)
- [x] PyPI release
- [x] Visualization charts (distribution / tornado / waterfall / forecast)
- [x] Interactive Streamlit app (driver sliders -> live charts)
- [x] Backtesting — out-of-sample method comparison (Naive / Linear / CAGR / Holt / ARIMA)

## Who is this for

Sell-side research, PE/VC investment teams, equity analysts, and students of
fundamental analysis who want a **reusable, auditable** revenue-modeling
scaffold rather than rebuilding the same spreadsheet structure by hand.

## License & disclaimer

MIT — see [LICENSE](LICENSE). This is a **research/education tool, not investment
advice** — full statement in [DISCLAIMER.md](DISCLAIMER.md).
