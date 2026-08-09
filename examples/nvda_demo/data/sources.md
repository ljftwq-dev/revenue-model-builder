# NVDA Demo — Data Sources & Credibility Grades

> Not investment advice. Public financial data only. See `../DISCLAIMER.md`.

This file documents **where every number comes from and how much to trust it**,
per `revenue-model-builder`'s ABC grading principle. A demo's honesty lives here.

## Fiscal-year convention

NVIDIA's fiscal year ends on the last Sunday of January. **FY2025 = ~Feb 2024
to Jan 2025** (covers most of calendar 2024). The AI breakout shows up in
**FY2024** (Data Center \$47.5B) and especially **FY2025** (\$115.2B). All years
below are NVIDIA fiscal years.

## Grade legend

| Grade | Meaning |
|---|---|
| **A** | Authoritative — from NVIDIA's official disclosure (10-K / quarterly PR) |
| **B** | Industry data — reputable third party (IDC / JPR / Mercury) |
| **C** | Estimate / back-solved — reasonable but uncertain |

## Segment revenue (`segments.csv`)

| Series | Grade | Source | Notes |
|---|---|---|---|
| `dc` (Data Center) | **A** | Our World in Data, aggregated from NVIDIA quarterly disclosures (FY2016-FY2025) | Verified: FY2024 \$47.5B, FY2025 \$115.2B match NVIDIA's headline figures |
| `total` | **A** | Same (OWID / NVIDIA) | Verified: FY2025 \$130.5B matches official total |
| `gaming` | **A*** | NVIDIA 10-K / annual report | FY2023 = \$9.067B confirmed verbatim in NVIDIA's 2023 Annual Review; FY2019-2022/24-25 are reported figures — **please double-check early years** |
| `other` | derived | `total − dc − gaming` | Residual = Pro Vis + Automotive + OEM & IP |

The A* on `gaming` flags: these are real NVIDIA-reported figures, but assembled
from memory + partial verification. If you have the 10-K segment table handy,
a quick cross-check of FY2019-FY2022 Gaming would harden the demo.

## Drivers — Gaming (`drivers_gaming.csv`)

`Gaming revenue = PC shipments (base) × dGPU attach (penetration) × NVIDIA dGPU share × GeForce ASP`

| Driver | Grade | Source / basis | Trend logic |
|---|---|---|---|
| `base` (global PC shipments, M units) | **B** | IDC, approximate | COVID bump FY2021-22, normalize after |
| `penetration` (dGPU attach rate) | **C** | Estimate (~13-18%) | Rises in crypto boom (FY2021-22 high), falls after |
| `share` (NVIDIA dGPU share) | **B/C** | JPR (~80-85%, AMD ~18%) | Stable NVIDIA dominance |
| `price` (GeForce ASP) | back-solved | `implied_driver` ties to reported Gaming revenue | — |

## Drivers — Data Center (`drivers_datacenter.csv`)

`DC revenue = accelerator shipments (base) × AI penetration × NVIDIA AI share × GPU ASP`

| Driver | Grade | Source / basis | Trend logic |
|---|---|---|---|
| `base` (accelerator shipments, M units) | **C** | Estimate | The "breakout" driver: ~0.5M (FY19) → ~8M (FY25); sharp jump FY2024+ on H100 |
| `penetration` | **C** | Structural ~1.0 (DC GPUs are all accelerators) | Held — not a swing driver |
| `share` (NVIDIA AI share) | **C** | Estimate (~60-90%) | Rose to ~90% in GenAI era; slight FY25 dip as competition enters |
| `price` (GPU ASP) | back-solved | `implied_driver` | Rises ~\$8k → ~\$16k as H100 dominates the mix |

**This is the whole point of the demo**: Data Center drivers are *almost all
C-grade* — the uncertainty is structural, not a modelling failure. The backtest
is expected to "fail" on DC hold-out precisely because a paradigm shift can't
be trend-extrapolated from C-grade historical drivers.

## What the demo does NOT claim

- Driver point values are illustrative; they carry the *trend*, not precision.
- `price` is force-aligned to history via back-solve — so in-sample fit is
  mechanical, and the real test is hold-out extrapolation.
- No forecast, no recommendation. Methodology demonstration only.
