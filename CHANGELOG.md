# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [0.12.1] - 2026-08-10

### Fixed
- **`validate()` false-positive on reported-anchor models** (C1): when every
  segment carries an A-grade reported anchor, a residual within rounding
  tolerance (~`N+1` million, since reported figures are whole-millions) is now
  recognized as caliber consistency, not the back-solve trap. Previously a Σ vs
  total difference of just ±1 would falsely emit "penetration back-solved"
  (positive) or "model structure wrong" (negative) — the exact warnings
  Principle 1 exists to catch, misfired on the flagship history-first feature.
  Driver-layer back-solve detection is unchanged (Principle 1 intact). New
  `tests/test_reported_anchor_validate.py` covers the rounding case in both
  directions plus the driver-back-solve and large-residual guards.

## [0.12.0] - 2026-08-10

### Added
- **Disk cache for network adapters** (`revenue_model.cache`): the `sec` / `sa` /
  `q4cdn` adapters now cache their raw network fetches (SEC ticker map + XBRL
  revenue, stockanalysis tables, q4cdn PDF text) to disk, so repeat calls don't
  re-fetch (faster, fewer requests, works offline on a warm cache).
  - Default location `~/.cache/rmb/`; override with the `RMB_CACHE_DIR` env var
    (e.g. `RMB_CACHE_DIR=D:\rmb_cache`).
  - JSON on disk (human-readable / inspectable). New `use_cache=True` (default)
    and `refresh=False` params on every `fetch_*` / `build_model_*`; `refresh=True`
    forces a re-fetch.
  - Injectable getters (`http_get` / `table_extractor` / `pdf_text_getter`) bypass
    the cache, so tests stay offline & deterministic.
  - Core stays zero-dependency: `cache.py` is stdlib-only and importing it does no IO.

### Changed
- README (EN/ZH): new Caching section, test count 162 → 170.

## [0.11.0] - 2026-08-10

### Added
- **q4cdn IR-PDF adapter** (`revenue_model.q4cdn_adapter`, `[pdf]` extra):
  parse company IR "Revenue by Market Platform" PDF supplements hosted on
  Q4 Inc's CDN (`s201.q4cdn.com/{company_id}/...`) at **quarterly granularity**
  — finer than `sa_adapter`'s annual segment table. `fetch_market_platform(url)`
  returns `{line_item: {(fiscal_year, quarter): million_USD}}`;
  `fiscal_year_rollup` aggregates to annual.
  - **Pure-stdlib parser** (`_extract_market_platform`); PyMuPDF lazy-imported
    only in the default text getter.
  - **`pdf_text_getter` injectable** → the test suite runs offline, no PDF, no network.
  - Verified on NVDA's Q1 FY27 supplement: Data Center = Hyperscale + ACIE,
    TOTAL = Data Center + Edge Computing, all 9 quarters caliber-consistent.
  - **No `build_model_*`** by design: the market-platform caliber differs from
    the business-segment caliber the other adapters use; mixing them would
    conflate calibers. This adapter is the data layer (see `examples/web_scraping/`).

### Changed
- `pyproject.toml`: new optional extra `pdf = ["PyMuPDF>=1.23"]`.
- README (EN/ZH): new q4cdn adapter section, test count 154 → 162.

## [0.10.0] - 2026-08-10

### Added
- **Segment reported-revenue anchor** (`Segment.reported_revenue`): an A-grade
  reported figure that takes precedence over the driver product in `revenue()`
  (history-first, Principle 5). Backward compatible — defaults to empty, so
  existing models keep the driver-product behavior. New `.revenue_source(year)`
  reports whether a year's figure is the reported anchor or the driver product.
- **stockanalysis.com segment adapter** (`revenue_model.sa_adapter`, `[scrape]`
  extra): the segment counterpart to `sec_adapter`. `build_model_from_sa(ticker)`
  pulls reported segment revenue from stockanalysis.com's "Revenue by Segment"
  table (e.g. NVDA Compute & Networking + Graphics) into each Segment's
  `reported_revenue` — filling the gap `sec_adapter` leaves (SEC XBRL segment
  tags vary per issuer, so segments were placeholder templates).
  - **Pure-stdlib core parser** (`_extract_segment_revenue`); playwright is
    lazy-imported only in the default browser extractor.
  - **`table_extractor` injectable** (url -> tables) → the test suite runs
    offline, with no browser and no network.
  - End-to-end verified on NVDA: FY22-FY26, Σ reported segments == reported
    total (residual 0, caliber-consistent).

### Changed
- `Segment` gained a `reported_revenue: Dict[int, float]` field (default empty)
  and a `.revenue_source(year)` method; `revenue(year)` returns the reported
  anchor when present, else the driver product. All 148 existing tests pass
  unchanged (backward compatible).
- `pyproject.toml`: new optional extra `scrape = ["playwright>=1.40"]`.
- README (EN/ZH): new stockanalysis adapter section, roadmap entry checked,
  test count 148 → 154.

## [0.9.0] - 2026-08-10

### Added
- **US-equity SEC adapter** (`revenue_model.sec_adapter`): the US-market
  counterpart to `tushare_adapter`. `build_model_from_sec(ticker)` pulls annual
  revenue from SEC EDGAR's XBRL `companyconcept` API → auto-fills
  `total_revenue` (million USD). Solves the data-cleaning Yahoo couldn't:
  filters full-year rows from quarter-only rows (period ≥ 350d) and falls back
  from `Revenues` to the ASC 606 `RevenueFromContractWithCustomer...` element.
  No token/key (SEC is public; only a `User-Agent`). `http_get` injectable.
- **HK-equity AKShare adapter** (`revenue_model.akshare_adapter`, `[data]`
  extra): the HK-market counterpart. `build_model_from_akshare(code)` pulls
  "营业额" from AKShare's `stock_financial_hk_report_em`. `ak` injectable. HK
  intelligent-driving names are sparse — the template is a starting point.
- **CLI**: new `sec` and `akshare` subcommands; `tushare` / `sec` / `akshare`
  now form a three-market adapter suite (A-share / US / HK).
- End-to-end verified: NVDA (FY26 $216B, AI surge), 比亚迪股份 01211 (2025 ¥804B).

### Changed
- README (EN/ZH): US + HK adapter sections, test count 133 → 148, roadmap
  multi-market ✅ (A-share / US / HK all via structured official sources).

## [0.8.0] - 2026-08-10

### Added
- **A-share tushare adapter** (`revenue_model.tushare_adapter`, NEV /
  intelligent-driving focus): the project's first **structured-data** source.
  `build_model_from_tushare(ts_code, token=...)` pulls real annual-report
  revenue from tushare `income` → auto-fills `total_revenue` (the Principle-1
  anchor, in million yuan), and seeds intelligent-driving segment drivers
  (智能驾驶 / 智能座舱) from an industry template — each driver's
  name/unit/source/source_url is pre-filled (CAAM, 高工产业研究院), values are
  `[adapter]` placeholders for a human, mirroring `extractor`'s semi-automated
  boundary: the machine gives the anchor + structure, the analyst fills the
  C-grade driver values.
  - **Pure stdlib** (urllib); no tushare SDK. Token is a runtime argument (load
    via your secrets manager; never hardcode) or `TUSHARE_TOKEN` env var.
  - **`http_get` injectable** → test suite / CI need no network and no token.
  - CLI: `python -m revenue_model tushare 002405.SZ` (德赛西威 demo).
  - End-to-end verified on 德赛西威 (002405.SZ): 20 years of real revenue.

### Changed
- README (EN/ZH): new tushare adapter section, test count 124 → 133.

## [0.7.0] - 2026-08-10

### Added
- **Word memo builder** (`revenue_model.docx_builder`, extra `docx`): render a
  `RevenueModel` into a 7-section analyst research memo (.docx) — the narrative
  counterpart to `excel_builder`'s working paper. Sections: Executive Summary,
  Company & Segment Overview, ABC-graded Driver Tables, Residual Alignment,
  Uncertainty & Scenarios (embedded Monte Carlo distribution / tornado /
  forecast charts), Limitations, and a Methodology appendix.
  - **Bilingual**: every memo carries a `lang` parameter (`"en"` default for the
    global / PyPI audience, `"zh"` for 中文版). The footnote on each memo shows the
    active language and how to switch. `driver.kind_label(lang)` and all `viz`
    plot functions thread `lang` through (default `"zh"` = backward compatible).
  - **Two honest defaults**, encoding the project's honesty philosophy at the
    API boundary:
    - `ranges=None` → Monte Carlo uses default ±10% bands but **flags them as
      illustrative** in §5 (chart callout) and §6 (Limitations). The shape is
      structurally valid; the absolute spread is not — silence would mislead.
    - `forecast_years=None` → historical-only memo; passed-but-unfilled → a
      prominent `[Forecast drivers not yet populated]` alarm (never silent skip).
  - CLI: `python -m revenue_model docx -o memo.docx --lang en [--no-charts]`.
  - `include_charts=False` renders §5 as tables only (no matplotlib needed);
    `include_charts=True` without matplotlib raises `ImportError` naming the extra.
  - **Full traceability via clickable hyperlinks**: every driver carries an
    optional `source_url`; the memo renders it as a real clickable link (blue,
    underlined — opens the browser). A new "Data Source Index" appendix lists
    every driver's source + URL. The methodology section links to the GitHub
    docs (design-principles / industry-fit / proposal), and the executive
    summary carries internal chapter cross-references (§3 / §4 / §5 jumps).
    Mirrors the revenue-model-builder skill's "链接：[URL]" convention — every
    number is one click from its origin.

### Changed
- `pyproject.toml`: new optional extra `docx = [python-docx>=1.0, matplotlib>=3.5]`.
  Core stays zero-dependency.
- `driver.kind_label` and all `viz.plot_*` functions gained a `lang` parameter
  (default `"zh"`, backward compatible).
- README (EN/ZH): new Word memo section, `lang` callout, test count 102 → 120.

## [0.6.0] - 2026-08-09

### Added
- **NVIDIA driver demo** (`examples/nvda_demo/`): the first **U.S.-equity** demo
  and the sharpest possible test of the driver-tree method's boundary. One
  company, two segments, the same `base × penetration × share × price` tree and
  the same engine — Gaming hold-out **sMAPE 1.0%** (trend market) vs Data Center
  **60%** (AI regime shift, actual $115.2B vs forecast $18.4B). Includes a
  **scenario close-out**: a Monte Carlo over honestly-uncertain C-grade Data
  Center drivers whose Bull tail frames the actual breakout — the point forecast
  collapsed, the scenario band captured the truth. Ships `build_model.py`,
  `backtest_nvda.py`, `plot_results.py` (→ `nvda_backtest.png`), `findings.md`,
  and an ABC-graded `data/sources.md`.
- **Flagship methodology doc** (`docs/industry-fit-analysis.md`): generalizes
  the NVIDIA result into a practitioner framework — an industry-fit matrix
  (strong / adapt / avoid), five techniques for event-driven growth (scenarios,
  leading indicators, S-curves, causal models, Bayesian updating), and why the
  library chooses honesty over false precision. Linked from the docs nav.

### Notes
- Core engine unchanged; the demo exercises existing `backtest` + Monte Carlo
  `scenarios` APIs. NVIDIA segment revenue is A-grade (official disclosures via
  Our World in Data); drivers are B/C-grade estimates, as documented per ABC
  principle. Not investment advice.

## [0.5.0] - 2026-08-02

### Added
- **Backtesting module** (`revenue_model.backtest`, extras `backtest` +
  `data`): honest out-of-sample evaluation of revenue forecasts.
  - `metrics` — pure-stdlib forecast-accuracy metrics (MAE / RMSE / MAPE /
    **sMAPE** / R² / directional accuracy). sMAPE is the headline: bounded in
    [0, 2] and robust across companies of very different revenue scales.
  - `methods` — five forecasters behind one protocol: `Naive` (random-walk
    benchmark), `LinearTrend`, `LogLinearCAGR`, `HoltLinear`, `ARIMA`.
    Naive/Linear/CAGR are stdlib; Holt/ARIMA lazy-import statsmodels.
  - `rolling` — expanding/fixed-window backtest engine; a method never sees
    the value it must predict. `evaluate()` aggregates per-method metrics;
    `score_table()` renders a CLI-friendly table.
  - `data` — akshare annual-revenue loader with on-disk CSV cache (B-grade,
    sourced from 同花顺 annual abstracts; million-yuan units to match the engine).
- **Two demo experiments** (`examples/backtest_demo/`): a Luxun driver
  hold-out (build from 2023-24, predict 2025 vs reported) and a ten-company
  cross-method comparison spanning six growth regimes, with heatmap + ranking
  charts (`heatmap_smape.png`, `ranking.png`).
- **Methodological finding** (documented in README): on revenue *totals*,
  adaptive methods (Holt/ARIMA, ~14% sMAPE) dominate fixed trends (Linear/CAGR,
  31–36%) and win all 10 companies; the driver decomposition's value is
  locating structure (trend vs one-off event), not beating statistics on
  aggregate accuracy.

### Changed
- `pyproject.toml`: new optional extras `backtest = [statsmodels>=0.14]` and
  `data = [akshare>=1.14]`. Core stays zero-dependency.
- README (EN/ZH): new Backtesting section, roadmap entry, test count 72 → 102.

## [0.4.0] - 2026-08-02

### Added
- **Visualization module** (`revenue_model.viz`, extra `viz`): four matplotlib
  charts that turn model output into pictures, each returning an `Axes` so it
  embeds anywhere (notebooks, reports, the Streamlit app):
  - `plot_revenue_distribution` — Monte Carlo histogram with P5/P25/median/P75/
    P95 markers and Bear/Base/Bull bands.
  - `plot_tornado` — ranked sensitivity bars around the base case.
  - `plot_waterfall` — cumulative "upside bridge" as each driver is moved.
  - `plot_forecast` — historical (solid) vs forecast (same-color dashed)
    trajectory per segment, with a reported-vs-forecast (Σ segments) total line.
  - `plot_dashboard` — a 2×2 panel combining all four for one segment.
  Headless (Agg) smoke tests; CJK glyph fallback so Chinese names render.
- **Interactive Streamlit app** (`examples/streamlit_app.py`, extra `app`):
  load a model (default: the Luxun real A-share demo), drag driver-range
  sliders in the sidebar, watch all four charts + metric cards recompute live.
  Ships a startup guard that prints the correct `streamlit run` command if the
  script is launched with plain `python`.

### Notes
- The core engine stays **zero-dependency** — `viz` and `app` are optional
  extras, and `viz` is lazy-imported (never triggered by `import revenue_model`).

## [0.3.0] - 2026-08-02

### Added
- **Driver extrapolation API** (`Driver.extrapolate_*`): turn a driver's history
  into a defensible forward path. Every extrapolated point is a new C-grade,
  sourced value — the original driver is never mutated (immutable semantics).
  - `extrapolate_incremental(years, delta_pp)` — bounded incremental forecasts
    (e.g. penetration *+X percentage points/year*), auto-clamped to [0, 1].
    Encodes Principle 3 (incremental, not growth-rate) directly as an API.
  - `extrapolate_logistic(years, L, k, t0)` — logistic S-curve for long-horizon
    saturation of bounded ratios.
  - `fit_trend(years).extrapolate(years)` — OLS least-squares trend projection
    (pure stdlib) for price / base drivers.
- **Real A-share demo** (`examples/`, Luxun Precision / 002475): a fully
  documented historical-alignment case on a real company. Consumer / comms /
  automotive segments reconstructed from the annual report, reconciled to
  reported totals (residual ≈ 1.3%), plus a 2026–2028E forecast column. The
  fictional NovaTech demo is retained as a zero-knowledge quickstart.

### Fixed
- **Extractor**: small segments (< 5% of revenue, e.g. Luxun's PC-interconnect
  line) are now accumulated into `unmodeled` instead of being dropped, so the
  reported total is preserved.
- **Validation warnings**: tiered residual logic — `< 1%` warns about genuine
  back-solving, `1–5%` hints at a possible scope change / missing segment.
  Fixes a false positive on the Luxun demo (口径变化 misread as back-solve).

### Changed
- README roadmap: marked PyPI release and driver extrapolation as done;
  corrected test count (35 → 72).

## [0.2.0] - 2026-07-28

### Added
- **Stochastic revenue layer** (`revenue_model.stochastic`, experimental):
  upgrade uniform-sampling Monte Carlo to driver-specific stochastic processes.
  - `GBMDriver` — geometric Brownian motion for prices ($dS=\mu S\,dt+\sigma S\,dW$)
  - `LogitOUDriver` — bounded mean-reverting process for penetration/share
    (Ornstein-Uhlenbeck in logit space, sigmoid-mapped to (0, 1))
  - `OUDriver` — unbounded mean reversion (Vasicek-style)
  - `CorrelatedBundle` — Cholesky-induced correlated Brownian increments
  - `simulate_revenue()` — stochastic paths → revenue distribution (reuses `MCResult`)
  - Pure stdlib: Box-Muller normals, Euler-Maruyama discretization, hand-rolled
    Cholesky. Zero-dependency core intact. 18 analytic-solution tests.
- **End-to-end pipeline**: `RevenueModel.from_report(text)` turns an annual
  report's "main business analysis" text into a model in one call — LLM
  extraction → driver templates → `Segment` skeletons.
- **Driver templates** (`revenue_model.templates`): 6 business types
  (hardware / software / service / advertising / financial / retail), all
  normalized to `base × penetration × share × price`.
- **Unified CLI**: `python -m revenue_model {build, simulate, excel, extract}`
  and a `revenue-model` console script.
- **Docs site**: mkdocs Material with MathJax (LaTeX-rendered formulas) and a
  GitHub Pages workflow (`mkdocs build --strict` clean).
- **Community**: CONTRIBUTING (emphasizes the zero-dependency core invariant),
  Code of Conduct, Issue/PR templates.

### Changed
- `pyproject.toml`: project URLs, PyPI classifiers, console-script entry point.
- Math formulas in `docs/design-principles.md` now render as LaTeX; identifier
  expressions stay in code blocks.
- Driver kinds are now `Literal`-typed (`DriverKind` / `DataLevel`) —
  mypy-friendly, backward compatible.
- README test count and API references corrected (`scenarios`, `implied_driver`).

## [0.1.0] - 2026-07-28

Initial PyPI release. Bottom-up revenue forecasting engine with a
zero-dependency core: `Driver` / `Segment` / `RevenueModel`, structural
residual alignment, A/B/C data grading, Monte Carlo + tornado sensitivity,
Bear/Base/Bull scenarios, `implied_driver` calibration, and LLM-based segment
extraction from annual reports.
