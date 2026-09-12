# Proposal: auto_pipeline (v0.20) — "one company name in, one model out"

## Vision

```
>>> from revenue_model import auto_pipeline
>>> result = auto_pipeline("PLTR", fiscal_year=2027)
[fetched]   Government / Commercial segments, 3y history each
[suggested] Government -> trend-family candidates (evidence attached)
[suggested] Commercial -> saas_subscription (band + battery evidence)
[gate-1]    confirm tags: [enter] accept  /  [edit] retag
[forecast]  Government: point + intervals; Commercial: point + MC scenarios
[checked]   Commercial revenue CAGR +55% ABOVE software band 16-28% — story required
[gate-2]    review out-of-band assumptions
[report]    docs/PLTR_revenue_model.docx written
```

Five versions laid every component. v0.20 is the orchestration that strings
them into one command — with two human gates that are *design*, not TODO.

## Parts already on the shelf (built v0.12–v0.19)

| stage | component | status |
|---|---|---|
| fetch | `sec_adapter` / `q4cdn_adapter` / `ir_adapter` | shipped |
| parse | `extractor` (LLM: text → segment trees) | shipped |
| suggest | `suggest_profile` (battery + band + prior) | v0.19 |
| forecast | `forecast_segment` + 10 mechanism profiles | v0.16–0.17 |
| check | `benchmark_warnings` + heuristic checks | v0.18 |
| assemble | `RevenueModel` (residual + alignment) | early |
| report | `docx_builder` / `excel_builder` | shipped |

The missing piece is one function with a state machine, offline-testable,
that a non-coder can drive.

## The two human gates (never automated away)

- **Gate 1 — tag confirmation.** The engine suggests with evidence; the
  analyst accepts or retags. Rationale: a wrong mechanism label poisons
  everything downstream (NVDA DC: 60x sMAPE). Implementation: config-file
  driven for scripts (`tags={"Commercial": "saas_subscription"}`), or
  interactive confirm for CLI use; unattended runs *require* explicit tags
  and say so loudly.
- **Gate 2 — out-of-band story.** When benchmark warnings fire ABOVE the
  industry band, the pipeline refuses to silently ship the point forecast:
  the report renders the warning plus an empty "assumption" slot the
  analyst must fill (or explicitly accept with `--accept-band-risk`).

## Phasing

- **v0.20a — offline spine (the core deliverable).** `auto_pipeline(
  segments=..., tags=..., years=...)`: parse/suggest/forecast/check/
  assemble/report from local data only. Offline fixtures in tests; PLTR +
  NVDA + Luxun as acceptance cases. No network, no LLM required (LLM parse
  optional when text provided).
- **v0.20b — fetch wiring.** `auto_pipeline("PLTR")` resolves via
  `sec_adapter` with disk cache; graceful degradation to manual input when
  the network or disclosure is missing.
- **v0.20c — the loop closer.** Interactive gate prompts; config file
  round-trip (a run serializes its state so `--resume` continues after the
  human gates).

## Non-goals

- No auto-tagging without confirmation (Gate 1 is permanent).
- No silent point forecasts on hypergrowth segments (regime-shift redirect
  stays loud).
- No new forecasting math — orchestration only.

## Acceptance

1. `tests/test_auto_pipeline.py` — offline fixture in, `.docx` out, gates
   respected, 340+ existing tests untouched.
2. PLTR demo: Government (trend) + Commercial (saas + ABOVE-band story)
   end-to-end in one command — the third showcase after NVDA/Luxun.
3. Docs: `docs/auto-pipeline.md` cookbook page.

## Road to 1.0.0

v0.20 completes the 0.x mission (methodology validated across 0.16–0.19;
API de-facto stable with zero breaking changes since 0.16). Once the
pipeline closes the loop, the project declares its first stable release:

- **Path**: v0.20a/b/c (interfaces free to settle during orchestration work)
  → *if* core APIs needed surgery, insert a v0.21 hardening release →
  **1.0.0** otherwise directly.
- **1.0.0 means**: semver contract starts — no breaking public-API changes
  within 1.x without a deprecation cycle.
- **1.0.0 acceptance** (on top of v0.20's):
  1. Fresh `pip install` → first model within 5 minutes (quickstart,
     actually timed on a clean venv).
  2. README declares the stability policy.
  3. PLTR / NVDA / Luxun all reproduce with one command each.
