# Industry profiles demo — the fit matrix, executable

> Requires **v0.16+**. Same data as [`../nvda_demo`](../nvda_demo/) — train
> FY2019-FY2023, hold out FY2024-25. Run: `python industry_demo.py`

Before v0.16, the industry-fit lesson (a driver tree's accuracy is a property
of the industry's growth mechanism) lived in a **hand-written backtest
script** — the analyst had to know which method to apply per segment. v0.16
moves that knowledge into the engine:

| step | API | what happens |
|---|---|---|
| 1 | `list_profiles()` | catalog: 10 mechanism profiles, each tagged strong / adapt / weak |
| 2 | `check_segment()` | **mis-tag teaching moment**: Data Center tagged `semiconductor` trips the hypergrowth check (`base compounding +58%/yr → consider regime_shift_tech`) *before any forecast is made* |
| 3 | `forecast_segment()` | profile-default forecasts — no hand tuning; Gaming gets trend/hold/held ASP, DC gets the naive-trend baseline |
| 4 | hold-out | Gaming **sMAPE 3.0%** (strong fit tracks); DC **57.9%**, FY2025 −82% (weak fit collapses — and the engine already said so) |
| 5 | `simulate_segment()` | the weak-fit redirect: Monte Carlo with honest wide bands — actual FY2024 \$47.5B sits ~P75, FY2025 \$115.2B ~P66, framed by the distribution |

The one new input versus the v0.15 demo is the **industry tag** — and it
changed which defaults applied, which warnings fired, and which forecast mode
(point vs scenarios) is even meaningful.

Methodology: [`docs/industry-fit-analysis.md`](../../docs/industry-fit-analysis.md)
