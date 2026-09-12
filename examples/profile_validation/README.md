# Profile validation experiment — data, scripts, results

Pre-registered out-of-sample test of the v0.16 industry-fit matrix
(spec: [`docs/proposal-profile-validation.md`](../../docs/proposal-profile-validation.md),
frozen 2026-09-11 before any test-set pull; results:
[`docs/profile-validation.md`](../../docs/profile-validation.md)).

## Layout

| file | what it does |
|---|---|
| `build_universe.py` | anti-survivorship universe (anchor 2023-12-31), GICS sub-industry → mechanism profile, full exclusion audit (raw S&P lists cached under `data_raw/`) |
| `pull_revenue.py` | SEC XBRL revenue panel (cached), spine-year quality filter |
| `profile_methods.py` | the three pre-registered profile-implied revenue-layer methods (Damped / DecelCAGR / GrowthRevert, pure stdlib) |
| `run_battery.py` | Track A: 8 methods × 244 companies × FY2023-25 |
| `analyze_battery.py` | pooled medians, win counts, Wilcoxon + Bonferroni + rank-biserial (pure stdlib) |
| `pull_drivers.py` | Track B data verification (JPM XBRL NII/assets; NFLX/SBUX 10-K greps) |
| `track_b_trees.py` | six hand-built driver trees, every series sourced + A/B/C graded |
| `run_track_b.py` | Track B: warnings ledger, profile-default vs naive per-driver trend, MC coverage |

## Data

- `data/universe_2023.csv` — 244 companies, profile + fit class
- `data/universe_audit.txt` — every exclusion, with reason
- `data/revenue_panel.csv` — annual revenue, FY2015-FY2025
- `data/battery_results.csv` — 5,856 rows (ticker × year × method × sMAPE × dir)
- `data/analysis_summary.txt` — Track A inference (validation + test)
- `data/track_b_results.txt` / `data/track_b_summary.csv` — driver-layer results
- `data/drivers_verified.json` — XBRL/10-K verification trail

## Reproduce

```bash
python run_battery.py       # ~4 min (statsmodels ARIMA)
python analyze_battery.py
python run_track_b.py       # FY2025 touched once -- do not re-tune after
```

The test set (FY2025) is never re-opened after results are computed —
discoveries go to v0.17 work, not retro-fits.
