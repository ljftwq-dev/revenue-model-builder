# docx_builder · Design

> Word memo rendering for `RevenueModel`. v0.7.0 design, validated via
> brainstorming on 2026-08-10. Companion to `excel_builder.py`: the .xlsx is
> the **working paper** (calc), this is the **deliverable** (narrative).

## Motivation

Sell-side research notes and PE investment memos are delivered as Word
documents. `excel_builder` already renders the calculation; without a Word
counterpart the library can produce the *process* but not the *story*. This
module closes that gap while preserving rmb's honesty philosophy.

## Requirements (brainstorming outcome)

| Decision | Choice | Rationale |
|---|---|---|
| Audience | Analyst internal working paper | Maximally honest: all drivers laid out, MC params listed, residual/limitations front and center |
| Language | `lang: "zh" \| "en" = "en"` default, user-selectable | Open-source, global market (PyPI/GitHub) — English is lingua franca; CN users pass `lang="zh"` |
| Charts | Embed (reuse `viz.py`) | MC distribution + tornado + forecast trajectory; matplotlib already verified on NovaTech demo |
| Dependency | optional extra `docx = [python-docx, matplotlib]` | Zero-dependency core untouched (same pattern as `excel`/`viz`) |

**Language discoverability** (the "must remind the user" requirement) is
enforced at three touchpoints: `build_docx` docstring `.. tip::` block, the
`docx` CLI subcommand `--lang` help, and a footnote on every generated memo
(`Language: en (set lang="zh" for 中文版)`).

## API

```python
def build_docx(
    model: RevenueModel,
    path: str,
    *,
    forecast_years: Optional[Sequence[int]] = None,
    ranges: Optional[Dict[str, tuple]] = None,
    include_charts: bool = True,
    company_overview: Optional[str] = None,
    lang: Literal["zh", "en"] = "en",
) -> str
```

Mirrors `build_excel(model, path, *, forecast_years)` for zero learning cost.

## Document structure (7 sections + appendix)

1. **Executive Summary** — 1 page: company, year range, total revenue
   trajectory, Σ-segments vs reported residual ratio, key warnings, Bear/Base/Bull
   one-liner. → `validate_all()`
2. **Company & Segment Overview** — `company_overview` param (or `[TODO:
   overview]` placeholder) + segment list with revenue-share table. → `segments`
3. **Segment Driver Tables** (body) — one table per segment: driver/kind/unit/
   **ABC-colored values**/source column. Fully expanded (working paper). → `seg.drivers()`
4. **Residual Alignment** — per year: Σ segments / reported total / residual /
   ratio / warnings. The honesty core. → `YearResult`
5. **Uncertainty & Scenarios** — MC distribution chart + tornado + forecast
   trajectory + Bear/Base/Bull table. **Range source annotated.** → `monte_carlo` + `viz`
6. **Limitations & Caveats** — template text + dynamic: list all C-grade
   drivers, residual share, unmodeled business, whether MC intervals are defaults.
7. **Appendix: Methodology** — driver formula, ABC definitions, increment vs
   growth-rate, history-first. **Default included** (self-contained for circulation).

ABC color coding mirrors `excel_builder`: A=black, B=blue, C=red (applied to
table cell font color).

## Two honest defaults (the core decisions)

### Default 1 — `ranges=None`

`Driver` has no `range` field (design-principles lists it as *planned*). Monte
Carlo cannot run without per-driver `(low, high)` intervals. Three options:

| Option | Behavior | Verdict |
|---|---|---|
| A. Raise | force user to supply real ranges | too frictional for quick preview |
| B. Silent ±10% | use `viz._default_ranges`, say nothing | **dishonest** — reader assumes it's real uncertainty |
| C. ±10% + annotate ✅ | use defaults but flag prominently | honest default |

**Why C over B** (NovaTech numbers): ±10% treats all drivers uniformly but real
uncertainty tracks the ABC grade — A-grade `市场基数 24.0` gets an over-wide band
(21.6–26.4 vs real 23.5–24.5, 5× too wide); C-grade `市占率 0.14` gets an
under-wide band (0.126–0.154 vs real 0.10–0.18, 3× too narrow). The shape is
structurally valid, the absolute spread is misleading — so it must be labeled.

Annotation appears at two places: a yellow callout next to the MC chart
(`⚠ Ranges: default ±10% bands (illustrative only). Pass ranges= with
A/B/C-reflective intervals for real analysis.`) and an auto-added bullet in
section 6 (Limitations).

### Default 2 — `forecast_years=None`

Encodes Principle 5 (history first, then forecast). Three cases:

| Case | Trigger | Behavior |
|---|---|---|
| A | `forecast_years=None` | historical-only memo; forecast chart draws solid history, no dashed forecast |
| B | passed + drivers have values | full forecast: solid history + same-color dashed future |
| C | passed but drivers missing values | prominent red placeholder `[Forecast drivers not yet populated — run extrapolate_* for <years> before regenerating memo]` |

Case C is deliberate: silently skipping the forecast section would let a user
ship a half-built memo thinking it was complete. The placeholder is an active
alarm, mirroring `excel_builder`'s `IF(OR(...=""),"",...)` revenue guard.

## i18n (3-file impact)

| File | Change | Size |
|---|---|---|
| `docx_builder.py` (new) | native bilingual, `_STRINGS` dict | built-in |
| `driver.py` | `_KIND_LABELS` → bilingual dict, `kind_label(lang="zh")` adds param (default zh = backward compatible) | ~10 lines |
| `viz.py` | 5 plot funcs add `lang="zh"` param; titles/labels/legends via `_VIZ_STRINGS`; default zh backward compatible | ~40 lines |

Units: driver tables keep native units (百万辆 / 小数 / 元); rollups and charts use
亿元 (zh) / RMB 100mn (en) — matches `viz._YI = 100`. Font: Microsoft YaHei
throughout (zh + east-asian font set, per project convention).

## Files

| Op | File |
|---|---|
| new | `revenue_model/docx_builder.py` |
| edit | `revenue_model/driver.py` |
| edit | `revenue_model/viz.py` |
| edit | `revenue_model/__main__.py` — add `docx` subcommand |
| edit | `pyproject.toml` — add `docx` extra |
| new | `tests/test_docx_builder.py` |
| edit | `tests/test_driver.py`, `tests/test_viz.py` — i18n cases |
| edit | `CHANGELOG.md` — `[0.7.0]` |
| edit | `README.md`, `README-zh.md` — docx section + lang callout |

## Testing

`pytest.importorskip("docx")` / `("matplotlib")` so the suite stays CI-friendly
when extras are absent. Verified: file generates + reopens with python-docx, all
7 section headings present, ABC coloring correct (`run.font.color.rgb`),
`ranges=None` produces "illustrative" annotation, `forecast_years` three cases,
both languages run, `include_charts=False` yields table-only, missing matplotlib
raises `ImportError` with install hint.

## Versioning

`0.6.0 → 0.7.0` (minor bump). Backward compatible — `kind_label` and all plot
functions add `lang` with a default, no existing call breaks.

## Out of scope (explicit)

- No template engine (jinja2 would add a dependency; YAGNI for 7 fixed sections).
- No `model.currency` field (NovaTech is RMB; future US-market adapter will add
  it — for now units default to RMB phrasing).
- No streaming/fluent builder API (`build_docx(...)` mirrors `build_excel`).
