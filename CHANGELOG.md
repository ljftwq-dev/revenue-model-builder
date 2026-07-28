# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

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
