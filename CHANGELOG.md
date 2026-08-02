# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

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
