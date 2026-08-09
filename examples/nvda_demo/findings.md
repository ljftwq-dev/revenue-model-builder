# NVIDIA Driver Demo — Findings

> The short, data-driven write-up. For the full methodology treatment see
> `../../docs/industry-fit-analysis.md`. Not investment advice.

## TL;DR

The **same driver tree** (`base × penetration × share × price`), the **same
engine**, the **same extrapolation rule** — applied to NVIDIA's two main
segments. Trained on FY2019-FY2023, tested on the FY2024-FY2025 AI breakout:

| Segment | Hold-out sMAPE | FY2024 err | FY2025 err |
|---|---|---|---|
| **Gaming** | **1.0%** | +0% | +4% |
| **Data Center** | **60.0%** | **−64%** | **−84%** |

Data Center's error is **60× Gaming's**. The formula didn't change. The
industry did.

## Setup

- **Data**: NVIDIA segment revenue FY2019-FY2025 (Data Center + Total are
  A-grade, aggregated from NVIDIA's official quarterly disclosures via Our World
  in Data; Gaming is NVIDIA 10-K reported figures; drivers are B/C-grade
  estimates — see `data/sources.md`).
- **Split**: train FY2019-FY2023, hold-out FY2024-FY2025. The split is the AI
  breakout itself (Data Center \$15.0B → \$47.5B → \$115.2B).
- **Rule**: `base`/`share`/`price` extrapolated by OLS trend on the training
  window; `penetration` held (structural). `share` clipped to a valid band.
  `price` back-solved to tie each segment to its reported revenue in-sample.

## Result 1 — Gaming: the trend holds

Gaming is a mature, trend-extrapolatable market. The driver tree lands the
hold-out within ~4%:

```
predicted ($B): FY2024=10.5  FY2025=11.5
actual    ($B): FY2024=10.4  FY2025=11.0
```

Driver-tree forecasting works when the industry's growth mechanism is a
continuation of history.

## Result 2 — Data Center: the trend breaks

Data Center is an AI regime shift. Trend extrapolation from the pre-breakout
window *structurally* under-predicts — and no amount of trend-fitting fixes
that, because the future is not in the training data:

```
predicted ($B): FY2024=16.9  FY2025=18.4
actual    ($B): FY2024=47.5  FY2025=115.2
```

FY2025 actual (\$115.2B) is **6×** the extrapolated forecast (\$18.4B). This is
not a model that needs tuning — it is a class of situation where point
forecasting from history is the wrong tool.

## Result 3 — Scenario close-out: bound what you can't point-forecast

The demo does not stop at "it broke." We replace the point forecast with a
**scenario distribution**: Monte Carlo over wide, honestly-uncertain driver
bands (C-grade Data Center drivers genuinely *are* this uncertain). The actual
lands inside the distribution:

| | Bear (P10) | Base (P50) | Bull (P90) | Actual | Actual's percentile |
|---|---|---|---|---|---|
| FY2024 | \$23.9B | \$37.3B | \$56.6B | \$47.5B | ~P75 (near Bull) |
| FY2025 | \$48.0B | \$93.5B | \$163.9B | \$115.2B | ~P66 |

The trend point-forecast collapsed near Base; the Bull tail of an honestly-wide
distribution captured the breakout. Under a regime shift you will not get the
point right — but you **can** bound it, and that is the entire job of scenario
analysis.

## Why this matters

This is the U.S.-equity mirror of the Luxun (立讯精密) finding from v0.5.0:
consumer electronics driver tree at −0.1% sMAPE (trend), automotive at −51%
(Leoni acquisition event). NVIDIA sharpens the contrast to **1% vs 60%** on the
*same company, same year, same formula* — the only variable is whether the
segment's growth is trend-extrapolatable.

**Accuracy is a property of the industry, not of the model.** A driver tree is
neither universally right nor universally wrong; it is right *where growth
continues its history* and wrong *where a paradigm shift breaks it*. The honest
framework says which is which, and what to do in each case.

## Data honesty

- Data Center + Total: A-grade (NVIDIA official, via Our World in Data).
- Gaming: A-grade reported figures (FY2023 cross-checked against NVIDIA's 2023
  Annual Review); early years worth a 10-K re-confirm.
- All Data Center drivers are C-grade estimates — the wide scenario bands are
  not a bug, they are the *honest representation* of that uncertainty.

See `data/sources.md` for the full ABC grading.
