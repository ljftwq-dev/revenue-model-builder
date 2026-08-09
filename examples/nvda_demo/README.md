# NVIDIA (NVDA) — Driver-Tree Limits Demo (U.S. equity)

The **first U.S.-equity** demo for `revenue-model-builder`, and the sharpest
possible test of the driver-tree method's boundary: **one company, two segments,
same formula — opposite verdicts.**

## Why this matters
Gaming and Data Center are both NVIDIA, both modeled with the identical
`base × penetration × share × price` tree and the same extrapolation engine. Yet
on the FY2024-FY2025 hold-out, Gaming lands within **1.0% sMAPE** while Data
Center misses by **60%**. The only variable is whether the segment's growth is
trend-extrapolatable. That single result is the whole thesis of
[`docs/industry-fit-analysis.md`](../../docs/industry-fit-analysis.md): accuracy
is a property of the industry, not the model.

## What the demo shows
- **Gaming — trend holds.** A mature GPU market; shipments, attach rate, and ASP
  all continue their history. Hold-out sMAPE **1.0%** (FY2025 +4%).
- **Data Center — trend breaks.** The AI paradigm shift (FY2024+) is not in any
  pre-2024 trend. Hold-out sMAPE **60%**; FY2025 actual \$115.2B vs forecast
  \$18.4B — a 6× under-prediction.
- **Scenario close-out.** A wide Monte Carlo over honestly-uncertain Data Center
  drivers produces a distribution whose Bull tail (P90) frames the actual
  breakout — the point forecast collapsed, the scenario band captured the truth.

## Driver design
```
Gaming revenue       = PC shipments × dGPU attach × NVIDIA dGPU share × GeForce ASP
Data Center revenue  = accelerator shipments × AI penetration × NVIDIA AI share × GPU ASP
```
`base` / `penetration` / `share` are sourced & graded; `price` is back-solved to
tie each segment to its reported revenue (Principle 1). Every driver carries an
A/B/C credibility grade — see `data/sources.md`. Data Center drivers are almost
all C-grade, and that uncertainty is the *honest* input to the scenario bands.

## Data sources — all public
- Segment revenue (Data Center, Total): NVIDIA official quarterly disclosures,
  via [Our World in Data](https://ourworldindata.org/grapher/nvidia-quarterly-revenue-segment)
  (CC-BY). FY2024/FY2025 match NVIDIA's headline figures.
- Gaming: NVIDIA 10-K reported figures (FY2023 cross-checked against the 2023
  Annual Review).
- Drivers: IDC (PC shipments), JPR (dGPU share), plus C-grade estimates.

## Run
```bash
pip install -e ".[viz]"                          # core is zero-dep; [viz] for the chart
python examples/nvda_demo/build_model.py         # historical build + ABC validation
python examples/nvda_demo/backtest_nvda.py       # hold-out + scenario close-out
python examples/nvda_demo/plot_results.py        # -> nvda_backtest.png
```
Outputs: console tables for build/back-test, and `nvda_backtest.png` — a 1×2
panel (Gaming actual-vs-forecast overlap; Data Center gap + Bear-Bull band).

## Where to go next
- [`findings.md`](findings.md) — the short data-driven write-up.
- [`docs/industry-fit-analysis.md`](../../docs/industry-fit-analysis.md) — the
  flagship methodology doc: the industry-fit matrix, the five techniques for
  event-driven growth, and why this library chooses honesty.

## Compliance
Methodology back-test on public data — **not a forecast, not a buy/sell
recommendation**. See [DISCLAIMER.md](DISCLAIMER.md). Research / education tool,
not investment advice.
