# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [0.21.0] - 2026-09-14

### Added
- **Four-segment quarterly matrix (v0.21b acceptance #2)**:
  `segment_matrix.py` — the trace method as pipeline code. Pure-text
  `build_from_texts` core (unit-testable, no PDF), lazy-fitZ wrapper,
  `MatrixLoopError`-guarded double closed loops (A: US branches ==
  geographic US; B: four segments == total revenue), Q4 backcast from
  the FY 10-K minus filed quarters, `pltr_spec()` preset, `yoy_summary`.
  CLI: `python -m revenue_model matrix <queue>`. Live check: six PLTR
  quarters rebuild with H1'26 = 3,568.0M — exactly the hand-built
  evidence-chains card.
- **Chains workflow CLI (v0.21b acceptance #3: 看卡、拉链、定参数)**:
  `chains_cli.py` — card browsing (ring / segment / free-text filters),
  spec-JSON chain building with `quote_contains` disambiguation (a bare
  `file·pN` anchor is only accepted when unique — same-page multiplicity
  surfaced in the live drill), `ChainBook` validation through the
  existing `Chain` hard constraints, markdown rendering in the
  线索→链条→参数 style. `llm_digest.load_cached_cards` loads verified
  cards from cache with no backend. CLI: `cards` / `chain`.
- **8-worker page parallelism**: `digest_document(workers=N)` fans page
  backend calls out over a thread pool (extraction stays on the main
  thread — PyMuPDF is not thread-safe; cache writes are atomic
  tmp+replace). Validated on the full 12-document PLTR drill rebuilt
  after a workspace loss: 2,638 verified cards.

### Added
- **Information-layer codification (v0.21b core)**: the 2026-09-12 manual
  drill, now pipeline code.
  - `evidence.py`: `EvidenceCard` (verbatim-quote verification,
    whitespace-tolerant) + `Chain` (>= 2 verified cards → verdict → one
    parameter, with `user` vs `user-delegated` authority) + `ChainBook`.
    Hard constraints structural: unverified cards never chain, chainless
    revisions never report.
  - `gate.py`: unified `GateBook` state machine (state.json + resume) for
    documents/tags/stories gates; the delegation phrase maps to
    `user-delegated`; the coverage checklist persists immediately
    (Principle 0) and renders as loudly as warnings.
  - `llm_digest.py`: page-cached per-page digestion; `make_glm_backend`
    (Zhipu API, key via `ZHIPU_API_KEY`/param — never hard-coded);
    hallucinated quotes voided into a reject log; `MissingBackendError`
    is a Gate H question, never a crash.
  - `auto_pipeline`: evidence stage (`digest_queue`/`digest_backend`/
    `workdir`); `PipelineResult` carries `chainbook`/`gates_waiting`/
    `coverage`.
  - Pilot live check: Q2'26 deck, all 36 pages — 85 verified cards
    (manual drill's anchors all hit: p4 highlights, p23 customers, p27
    guidance, p29 NRR), 70 hallucinated/paraphrased candidates voided by
    verification (~45% reject rate — the guard earns its keep).

### Added
- **Quarterly momentum layer (v0.21a)**: the analyst's "read quarterlies
  for momentum" step as a pipeline stage. `momentum.py` (pure stdlib,
  kernel-scoped) rolls single-quarter revenues into a TTM series and reads
  the *change* in TTM YoY (±3pp band): accelerating / decelerating /
  steady, with an evidence line annual points cannot produce ("trend
  extrapolation likely UNDERSTATES/OVERSTATES"). Fewer than 9 quarters →
  "insufficient" (refuse to guess). Wired into `auto_pipeline`
  (`momentum_enabled=True` by default when the total was auto-fetched;
  failures skip softly), exposed as `PipelineResult.momentum` and exported
  (`detect_momentum`, `ttm_series`, `MomentumReading`). Live-checked on
  PLTR: TTM +56%/yr vs +47% one quarter earlier — a real accelerating
  up-turn the annual 4-point history cannot show.

### Added
- **`auto_pipeline` — the offline spine (v0.20a)**: one call from raw
  segment data to a report, zero network / zero LLM. Stages: build drivers
  (omitted ratio drivers default to constant 1.0) → suggest shortlists →
  **gate 1** (explicit tags, or `"auto"` adopting the top candidate loudly;
  untagged segments park in `gate1_pending` and are not forecast) →
  forecast → citation checks → **gate 2** (ABOVE-band segments require a
  story in `stories`, else `gate2_pending`) → assemble → optional `.docx`
  report (python-docx imported lazily — the pipeline itself stays
  zero-dependency). Returns `PipelineResult` with everything the pipeline
  did and everything still waiting on you.
- **PLTR demo** (`examples/pltr_demo`): real FY2021–24 10-K disclosure
  end-to-end in one command — explicit tag + auto-adoption + both gates +
  a hand override closing the soft-default loop.
- **`docs/auto-pipeline.md`** cookbook: input format, gate contract,
  override pattern.
- **SEC auto total revenue (v0.20b)**: pass `total_revenue=None` with a
  real ticker as `company` and the annual 10-K total is auto-fetched from
  SEC EDGAR via the existing adapter (disk-cached, `http_get` injectable —
  tests stay zero-network). `PipelineResult.total_source` records where
  the total came from. Failure degrades loudly with an actionable message
  (unknown ticker / network down → pass `total_revenue` by hand), never
  silently. Live-checked with PLTR: auto-fetched totals match the 10-K
  segment sums to the decimal.
- mypy: `auto_pipeline.py` joins the kernel scope; `__init__`-reachable
  stub-less extras (statsmodels, pymysql) and the report builder are
  scoped out via per-module overrides.

## [0.19.0] - 2026-09-12

### Added
- **Demo closes the loop (v0.19 step 2)**: `industry_demo` now opens with an
  *untagged* Gaming segment — `suggest_profile` ranks semiconductor first
  (battery evidence in the shortlist), the analyst accepts, and the [4]
  hold-out lands at 1.0% sMAPE: no-tag → right-tag → accurate. The DC
  mis-tag segment shows the other half: the untagged shortlist *led with
  the regime-shift warning* before we ignored it on purpose. Two halves of
  one teaching loop.
- **Profile catalog page (v0.19 step 3)**: `docs/profile-catalog.md`,
  *generated* from `INDUSTRY_PROFILES` by
  `examples/profile_catalog/render_catalog.py` — summary table (fit / base
  default / checks / benchmark count) plus one section per profile:
  mechanism one-liner, driver-defaults table, checks, Damodaran bands,
  weak-fit advice. The page cannot drift from the registry.
- **Profile auto-recommendation — `suggest_profile()` (v0.19 step 1)**: the
  other half of the v0.16 teaching loop. For an untagged segment, run the
  zero-dependency subset of the backtest battery (Naive, LinearTrend,
  LogLinearCAGR, DampedTrend, DeceleratingCAGR — no statsmodels needed) on
  each driver's own history; score every profile by how its default
  extrapolation families rank on base/price (ratio drivers carry almost no
  signal and are weighted down), add the v0.18 band-proximity bonus
  (revenue CAGR inside the profile's Damodaran band), and a hypergrowth
  prior — recent-3y revenue CAGR above 40% pins `regime_shift_tech` first
  with the v0.16 lesson in the reasons. Returns `ProfileSuggestion`
  top-k with evidence lines; refuses to guess when no driver history is
  backtestable. Soft by design: it ranks and explains, the analyst still
  tags.
- Fixed two latent type errors in `backtest/rolling.py` exposed by bringing
  `suggest.py` (pure stdlib, now in the mypy kernel scope) into the type
  graph.

## [0.18.0] - 2026-09-12

### Added
- **Benchmark dataclass — sourced industry bands (v0.18 step 1)**: checks get
  their citation backbone. `Benchmark` (exported) carries one metric's
  quartile band (`p25`/`p50`/`p75`, annualized fractions) plus full citation
  (`source` / `vintage` / `grade` / `note`); `IndustryProfile.benchmarks`
  (default empty — soft add, nothing breaks) anchors 9 of 10 profiles with
  Damodaran histgr clusters (Jan 2026 update, TTM 2025Q3): revenue CAGR last
  5y and expected revenue growth next 2y, per industry cluster (e.g. SaaS =
  System & Application + Internet + Computer/Information Services, 417 firms).
  `regime_shift_tech` stays unanchored by design — an AI inflection has no
  industry history to appeal to. Bands describe cross-industry spread within
  the cluster (per-industry values are firm-CAGR averages); data graded B
  (annual hand update). Heuristic checks unchanged this step — they draw on
  the bands in step 3.
- **Citation-based band checks — `benchmark_warnings()` (v0.18 step 3)**:
  segment revenue growth (driver-product caliber) vs the sourced bands,
  soft by design — inside the band → silence; outside → one line per side
  carrying the numbers, the cluster, the vintage, and the grade. History
  years compare against the 5y CAGR band, forecast years (explicit
  ``history_end`` boundary, forwarded from ``segment_warnings``) against the
  analyst-expected band; heuristic ``check_segment`` stays as the backstop
  layer, and ``regime_shift_tech`` stays heuristic-only by design.
- **Damodaran adapter — `damodaran_adapter` (v0.18 step 2)**: the bands'
  honesty is now automated, stdlib-only (zero new dependencies). Fetches the
  free histgr HTML export (30-day disk cache via the existing TTL cache),
  parses it with ``html.parser`` (percent strings → fractions), recomputes
  the cluster quartile bands with the same linear interpolation as the
  shipped literals, and diffs them — ``python -m
  revenue_model.damodaran_adapter verify [--refresh]`` exits 0 on match and
  prints drift lines plus upstream-vs-shipped vintage on mismatch.
  ``CLUSTERS`` is the single source of truth for the profile→industry
  mapping (regime_shift_tech deliberately absent). Verified live against
  the January 2026 update: 96 industries parsed, all 18 bands match.

## [0.17.0] - 2026-09-12

### Added
- **Churn-survival dynamics (Direction B of the v0.16 optimization study)** —
  subscription bases get their water-in/water-out math:
  - `Driver.extrapolate_net_growth(years, gross_rate, churn)` —
    `base_t = base_{t-1} x (1+gross) - base_{t-1} x churn`; the two knobs stay
    separate because the analyst defends acquisition and retention separately.
    A net rate <= 0 raises (an extinguishing base needs scenarios, not a
    forecast).
  - `saas_subscription` / `telecom_subscriber` base defaults switched to
    `net_growth` (30%/12% and 5%/3.5% analyst-first soft defaults; hand
    overrides always win).
  - New `net_churn_positive` check (both profiles): base compounding negative
    while ARPU compounds positive, with the sum still negative — "no realistic
    price escalator offsets a shrinking base."
- **DampedTrend + DeceleratingCAGR graduated into `revenue_model.backtest`**
  as first-class methods (per the pre-registered validation: DecelCAGR beat
  Naive on its home saas profile with double significance, r ~= -0.7;
  Damped won the adapt bucket with the best directional accuracy, 74%).
  `default_methods()` now returns 7 methods. The experiment's frozen copies
  stay in `examples/profile_validation/` for reproducibility.
- **G1 code gate in CI**: ruff with an explicitly pinned ruleset
  (E4/E7/E9/F/B, line-length 99, target py39 — immune to ruff's evolving
  defaults) + mypy scoped to the pure-stdlib kernel
  (driver/segment/model/monte_carlo/industry). 37 lint findings and 6 type
  findings fixed on adoption, including 6x closure-over-loop-variable
  (B023) bound via default args before they become real bugs.
- **FIG teaching-consensus citations (Direction D)**: the weak-fit financials
  classification now cites the sell-side teaching lineage (M&I/BIWS/edbodmer
  balance-sheet-first FIG modeling) and the A-share 规模×息差 perspective —
  with the Track-B JPM warning + MC coverage as the engine's independent
  re-derivation of that consensus.

### Fixed
- **`forecast_segment` hand-coverage bug (the Track-B API finding)**: a driver
  already extended by hand to *all* target years is now returned untouched —
  spec params are not even resolved. Previously a hand-held structural
  constant (e.g. 1.0) on a logistic-default kind raised ValueError from the
  anchor check despite the hand extension. Partial coverage still gets spec
  treatment for missing years. Regression-tested with the exact Track-B
  scenario.

### Changed
- `telecom_subscriber` base default: logistic (1.3x last) → `net_growth`.
- Default backtest battery: 5 → 7 methods (score tables gain two rows).

## [0.16.1] - 2026-09-12

### Added
- **Profile validation — the pre-registered experiment, run and reported**
  (`docs/profile-validation.md`, `examples/profile_validation/`). The v0.16
  industry-fit matrix tested out-of-sample: Track A (244 S&P 500
  constituents, anti-survivorship anchor 2023-12-31, 8 methods × FY2023-25,
  pure-stdlib Wilcoxon + Bonferroni + rank-biserial) and Track B (six
  hand-built driver trees exercising the real v0.16 API, FY2025 touched
  once). Verdicts: H1 rejected at the company-total layer but supported at
  the driver layer (NVDA Gaming 3.0% vs 10.9%); H2 partial (Damped −1.2pp
  validation / −1.6pp test vs Naive on adapt); H3 clean (warning hit 2/2,
  false alarms 0/4, MC P10-P90 framed all three weak-fit test years).
  DecelCAGR graduates with double significance (saas home profile,
  −5.7pp / −7.2pp, r ≈ −0.7); GrowthRevert honestly falsified at home
  (+9.3pp validation). README claim narrowed accordingly (driver layer vs
  totals layer). API finding recorded: `_apply_spec` resolves logistic
  params before checking hand coverage (v0.17 fix candidate).

## [0.16.0] - 2026-09-11

### Added
- **Industry profiles — the industry-fit matrix, executable**. The flagship
  methodology doc (`docs/industry-fit-analysis.md`) proved a driver tree's
  accuracy is a property of the *industry's growth mechanism* (NVDA Gaming
  1.0% vs Data Center 60% hold-out sMAPE); this release encodes that matrix
  as forecasting behavior:
  - **`industry` module** — `IndustryProfile` registry of **10 mechanism
    profiles** (consumer_electronics, semiconductor, saas_subscription,
    advertising, retail_store, telecom_subscriber, industrial_capacity,
    financial_interest, commodity_cyclical, regime_shift_tech), each carrying
    a fit class (strong / adapt / weak), per-driver-kind default
    extrapolation specs, industry-specific checks, and — for weak-fit
    industries — the scenario-first redirect. Profiles are pure data: adding
    one is a dict entry, not a subclass.
  - **`resolve_industry()`** — mechanism keys, GICS sector codes/names
    (`"40"`, `"financials"`), and Chinese aliases (`"软件"`, `"银行"`) all
    resolve; health care / real estate intentionally unmapped (no mechanism
    profile fits yet) with a catalog-bearing error.
  - **`Segment(..., industry=...)`** — optional tag, fully backward
    compatible; tags change forecast *defaults and warnings*, never the
    historical driver math.
  - **`forecast_segment()`** — extend every driver with the profile's
    analyst-first defaults (soft defaults by design: hand extrapolations
    always win; history is never touched; results stay C-grade).
  - **`check_segment()` / `profile_warnings()` / `segment_warnings()`** —
    10 industry checks (hypergrowth base, utilization cap, cycle top, ASP
    pricing-power, ad-load norm, ARPU acceleration, saturated subscribers,
    turnaround mix, credit-cycle flag, unconditional regime-shift redirect)
    plus the weak-fit verdict lines.
  - **Driver: 4 new extrapolation methods** (all pure stdlib, C-grade,
    source-tagged like the existing three): `extrapolate_mean_reversion`
    (yields / utilization / eCPM pull toward an anchor, `target=None` =
    last-3yr mean), `extrapolate_erosion` (geometric ASP decline),
    `extrapolate_growth` (geometric growth for balance sheets / escalators),
    `extrapolate_hold` (flat extension for sticky factors).
  - **Logistic anchoring**: profile specs support `t0="anchor_last"` — the
    inflection year is solved so the S-curve passes through the last known
    value (forecasts leave history smoothly instead of jumping to L/2).
  - **`examples/industry_demo/`** — NVDA re-run on v0.16: the mis-tag
    teaching moment (DC tagged `semiconductor` trips the hypergrowth check
    *before any forecast*), profile-default hold-out (Gaming 3.0% sMAPE vs
    DC 57.9% / FY2025 −82%), and the Monte Carlo close-out where the
    distribution frames the actual $115B.
  - 42 new tests (`test_industry.py`); suite total 303.
- Design rule of the release: profiles are **soft defaults + loud warnings,
  never hard blocks** — a researcher can always run the naive trend on a
  weak-fit industry *and be told exactly why that number cannot be trusted*.
  The NVDA demo depends on that loop staying open.

## [0.15.0] - 2026-08-16

### Added
- **Macro driver revisions — the event -> driver revision -> re-run loop**
  (Direction-3's conclusion encoded as code):
  - **`qesa_adapter` module** — read-only accessor for a QESA (Quant Event
    Signal Aggregator) store: `QesaStore` supports both backends (SQLite via
    stdlib, MySQL via the new `[qesa]` extra `pymysql`), with
    `series_history` / `latest` / `recent_shocks` / `series_info`.
  - **`macro_revision` module** — `MacroBinding` (upstream series -> driver
    mapping with channel `demand`/`cost`/`fx`, elasticity pp/pp, transmission
    lag in quarters, evidence note), `suggest_revisions()` (triggers on a
    *jump in upstream YoY*, not a high level), and `apply_revision()`
    (returns a new C-grade Driver tagged with the full evidence chain, same
    discipline as the extrapolation API). Suggestions are advisory — the memo
    carries the evidence next to the before/after forecast.
  - **Two demos**: `examples/luxun-real-demo/luxun_macro_demo.py` (real
    A-share Luxun model; cost channel via LME copper/aluminum + fx channel
    via CNY/USD; bundled `sample_qesa.db` of real FRED data so the demo runs
    offline) and `examples/nvda_demo/nvda_macro_demo.py` (demand channel via
    durable-goods orders; sector-peer-borrowed beta explicitly flagged C-grade
    with a magnitude sanity-check note; segment financials illustrative).
  - 21 new tests (`test_qesa_adapter`, `test_macro_revision`).

## [0.14.1] - 2026-08-15

### Changed
- **`docs/news-impact-validation.md`** extended from one round to three:
  - **Round 2 (revenue dimension, 18 issuers / 8 sectors)**: post-event YoY
    ran 7-9pp below baseline across every sector and one cell cleared
    Bonferroni — but pre-event growth was already low (p=0.013), the paired
    post−pre delta is zero, and filing rate falls monotonically with growth
    tercile (4.3 / 3.4 / 2.6 per year). The "effect" is **selection**: slow
    growers file more non-Earnings 8-Ks. Filing frequency is a reverse slow
    variable — a screening feature, not a shock.
  - **Round 3 (customer → supplier lead-lag, 8 pairs)**: customer event
    density ≥2/quarter precedes supplier YoY of +59-62% (vs +30% baseline,
    MWU p ≤ 0.008) at lags +1..+4 with clean placebo lags and a monotone
    dose-response — but the 13 high-activity quarters cluster inside two
    industry waves (2020-21 cloud, 2023+ AI), and the acceleration placebo
    fails. **News is a wave detector, not a trading signal**: ecosystem
    event density marks a driver regime shift 1-4 quarters before reported
    revenue, which is the trigger for the event → driver revision →
    re-run loop (never event → revenue regressions).
  - Methodological checklist extended (pre-event diagnostics, placebo lags,
    "what does n mean"), conclusion rewritten as three scoped answers.

## [0.14.0] - 2026-08-15

### Added
- **News-impact validation** (Direction-3): the pooled six-company case study
  (NVDA / AMD / SDGR / REGN / GILD / GM; 409 8-K events, 2019-2026) is
  documented in `docs/news-impact-validation.md`. Headline finding: the
  original single-company SDGR p=0.033 was a small-sample artifact — under
  pooling, market adjustment and Bonferroni correction, **no 8-K category
  carries robust monthly-horizon information on large caps**. The null
  result ships with the methodology that exposed it.
- **`news_impact` module** — honest event-study statistics, pure stdlib:
  - `welch_test` / `mann_whitney_u` hand-rolled (regularized incomplete
    beta via Lentz continued fraction; tie-corrected, continuity-corrected
    normal approximation). Verified against scipy to 8 decimals (constants
    in tests; scipy itself is not a dependency).
  - `event_study(events_by_sample, outcomes_by_sample, ...)` — pooled
    cross-issuer studies with per-category rows, automatic Bonferroni
    family correction surfaced per row (`significant` vs
    `bonferroni_significant`), and `min_n` small-sample guards that report
    without testing.
  - `align_first_after` — strict next-period alignment (a `date`-keyed
    outcome series; `date`/`datetime` compared safely).
- **`form8k_adapter` module** — 8-K filing events from SEC's submissions
  API: universal coverage (any ticker), official item classification
  (2.01 M&A / 1.01 Agreement / 5.02 Management / 2.02 Earnings / ...) via
  `classify_items` with materiality-priority ordering, `since` filter,
  cached by CIK, `http_get` injectable. The universal replacement for
  guessing Q4-Inc IR domains.
- **`sec_adapter.fetch_fiscal_quarters`** — fiscal-year-general
  single-quarter revenue series: anchored on each true-annual period (so
  non-calendar fiscal years like NVDA's late-January close derive
  correctly), concept-merged, discrete quarters preferred over derived
  values, incomplete trailing fiscal years excluded (the M7 honesty rule).

### Fixed
- **`sec_adapter` BUG-A (concept switching)**: `fetch_statement` picked the
  first revenue concept the issuer files and dropped the rest — SDGR
  switched from the ASC 606 element to `Revenues` in 2024, silently losing
  2019-2023 quarters. All candidate concepts are now merged per period
  (first-listed wins on overlap; overlap values are identical in practice).
- **`sec_adapter` BUG-B (period collision)**: a YTD cumulative and a
  discrete quarter sharing an end date collided in the `(fy, fp)` slot map,
  corrupting single-quarter differencing (SDGR Q3'24 derived as
  discrete(Jul-Sep) − YTD(Jan-Jun) = −48.6M). Slots now resolve
  deterministically — single-quarter mode prefers the discrete quarter,
  as-reported mode prefers the YTD figure — and differencing subtracts the
  fiscal chain predecessor, never the neighbouring slot. Chain differences
  carry a ~one-quarter span guard, so broken chains derive nothing rather
  than garbage.

### Tests
- Suite 204 → 240 (+36: statement fixes / fiscal quarters 11, form8k 11,
  news_impact 14).

## [0.13.0] - 2026-08-11

### Added
- **`sec_adapter` full financial statements** (`fetch_company_facts` +
  `fetch_statement`): complete income / balance / cashflow at annual AND
  quarterly granularity, including single-quarter derivation for flow items
  (`Q2_single = Q2_YTD − Q1_YTD`, `Q4_single = FY − Q3_YTD`). Augments the
  existing `fetch_revenues` (single-concept, annual-only). Validated on SDGR
  (Schrödinger): FY2019-2025, 265 US-GAAP concepts, one round-trip.
- **`ir_adapter`** (new): Q4 Inc `PressRelease.svc` API — one call returns a
  company's full press-release history (validated on SDGR: 259 releases,
  2017-2026). `classify()` buckets headlines into 9 event categories (Earnings
  / Partnership / Pipeline / ...); ticker→IR-domain map (SDGR / NVDA). Pure
  stdlib + `http_get` injectable + cache, mirrors the sec/q4cdn contract. Data
  layer for news-impact modeling (Direction-3).

### Fixed
- **`sec_adapter` Q4-comparative bug** (bug A/B): a 10-K income statement's
  "three months ended Dec 31" comparative was mis-labeled as FY (same
  end-month), overwriting the real annual figure and corrupting single-quarter
  Q4 derivation. New `_is_true_annual` enforces ≥350-day duration for flow
  items (reuses the lesson from `_is_annual`).
- **M1**: `sa_adapter` now raises when segments exist but the total row is
  unrecognized (was: silent half-built model, `years()==[]` → `validate` KeyError).
- **M2**: `q4cdn_adapter` fiscal regex now matches "Fiscal Year" / "Fiscal Yr".
- **M3**: `q4cdn_adapter` raises on empty PDF text extraction (scanned/image
  PDF → OCR hint, not silent empty).
- **M4**: SEC `company_tickers.json` cache now TTL-aware (7d) via new
  `cache_get_timed` / `cache_set_timed`; new IPOs/delistings no longer invisible.
- **M5**: `q4cdn_adapter` `_is_note` now continues instead of break (mid-table
  footnotes no longer drop subsequent line items).
- **M6**: `cache_set` now atomic (temp file + `os.replace`); no half-written
  JSON under concurrent access.

### Changed
- **M7 (BREAKING)**: `fiscal_year_rollup` returns `(annual, complete_years)`
  instead of just `annual`. Callers must unpack: `annual, complete = ...`. Years
  with <4 quarters are flagged partial — feeding them to
  `RevenueModel.total_revenue` would severely understate revenue.

### Tests
- Suite 170 → 204 (+34: sec_adapter 13, ir_adapter 13, M1-M7 + bug-A/B regression 8).

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
