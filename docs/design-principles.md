# Design Principles — Driver-Based Revenue Forecasting

> The engineering choices in `revenue-model-builder` encode five hard-won
> modeling rules that sell-side analysts and PE associates apply by hand.
> This document explains *why* each rule exists and what goes wrong without it.
>
> 中文要点见文末 [中文摘要](#中文摘要)。

Driver-based (bottom-up) revenue forecasting decomposes a company's revenue
into product-level drivers, then rebuilds the total:

```
segment_revenue = market_base × penetration × share × price
total_revenue   = Σ(segments) + residual
```

Unit derivation (the part most spreadsheets get silent): market base in
**million units**, price in **yuan**, penetration & share as fractions:

```
(M units) × (fraction) × (fraction) × (yuan/unit)
 = (million units) × yuan/unit × fraction × fraction
 = million yuan          (when both fractions ∈ [0, 1])
```

So `Segment.revenue()` returns **million yuan** by construction. Get the units
wrong and every downstream number is silently off by a factor of 10⁶.

The five principles below are the actual differentiators. They are rare in
open source not because they are secret, but because you only discover them
after building a model that *doesn't* tie out to the annual report.

---

## Principle 1 — The residual line is structural, never back-solved

When you use **industry-realistic** penetration values (from third-party
research, not fitted to the company), the modeled segments will **never**
exactly equal the company's reported total revenue. There is always
un-modeled business — aftermarket services, IoT modules, custom development,
one-off engineering fees.

```
residual = total_revenue (annual report) − Σ(segment_revenue)
```

**The temptation (and why it is wrong):** analysts hate a model that "doesn't
tie out." The lazy fix is to *back-solve* penetration — tweak it until the
segments sum to the reported total. **This destroys the model.**

Why? Because that back-solved penetration then flows into the **forecast**
period. If you inflated penetration from a realistic 9% to 11% just to make
2024 tie out, your 2025–2027 forecast is now built on an 11% base that was
never true. You have traded a small, honest, *visible* residual for a large,
dishonest, *invisible* error in the future.

`RevenueModel.residual()` makes the residual a **first-class output**, and the
alignment check (`validate()`) explicitly flags three failure modes:

| Condition | Warning | Meaning |
|---|---|---|
| `residual < 0` | "segments exceed total revenue" | structure is wrong, not a rounding issue |
| `residual_ratio > 0.5` | "un-modeled business dominates" | you are missing major segments |
| `0 < residual_ratio < 0.05` | "suspiciously small — penetration may have been back-solved" | the trap from above |

> **Rule:** keep penetration realistic; let the residual absorb the gap. A 10–30%
> residual is normal and healthy. A 0% residual is a red flag.

---

## Principle 2 — Data grading (A / B / C) makes every number auditable

The hardest question in any financial model is *"where did this number come
from?"* Spreadsheets answer it with cryptic cell comments, or not at all.

`revenue-model-builder` tags **every driver value** with a credibility grade:

| Grade | Meaning | Color (Excel output) | Example |
|---|---|---|---|
| **A** | Hard data — annual report / official filing | black | China passenger car sales (CAAM) |
| **B** | Third-party industry data | blue | DMS penetration (research institute) |
| **C** | Estimate / judgment / back-solved | red | market share, ASP |

`Driver.level` carries this, and `excel_builder` colors the cells accordingly.
The payoff: a reviewer can **see at a glance** which columns are facts (black)
versus guesses (red). It turns an opaque spreadsheet into an auditable model —
exactly what an investment committee or a buy-side client demands.

---

## Principle 3 — Forecast penetration in increments, not growth rates

This is the subtlety almost no textbook mentions.

**Wrong:** forecast penetration as $p_{n} = p_{n-1} \times (1 + g)$ with a constant
growth rate $g$.

**Right:** forecast as $p_{n} = p_{n-1} + \Delta p$ with a constant **increment** $\Delta p$.

Why? Because penetration is a **bounded** variable (it approaches 100%). A
constant growth rate $g$ produces *exponential* growth — penetration rockets
past physical limits within a few years. A constant increment produces
*linear* growth that naturally decelerates in rate terms as the base grows,
which matches real adoption curves (S-curves are nearly linear in the middle).

Concretely: from 9%, a "20% growth rate" rule gives 10.8% → 12.96% → 15.6% (still
accelerating in absolute terms). A "+3 percentage points" rule gives 12% → 15% →
18% (steady, believable, and easy to defend with policy/industry logic).

> **Rule:** forecast bounded ratios (penetration, share) in **absolute increments**,
> never in growth rates.

---

## Principle 4 — Forecast methodology priority (the certainty pyramid)

Not all forecast inputs are created equal. `revenue-model-builder` ranks
forecast drivers by **how knowable** they are, highest certainty first:

```
┌─────────────────────────────────┐
│ 1. Regulation / policy catalyst │  ← e.g. EU GSR mandating DMS, China L2
│    (highest certainty)          │     ADAS standard — a regulatory floor
├─────────────────────────────────┤
│ 2. Industry anchor data         │  ← e.g. "DMS will hit 10M vehicles by
│                                 │     2027" (third-party forecast)
├─────────────────────────────────┤
│ 3. Historical trend (increment) │  ← YoY extrapolation via Principle 3
├─────────────────────────────────┤
│ 4. Product timeline             │  ← e.g. "SouthLake chip mass-production
│                                 │     H2 2026" (capacity ramp)
├─────────────────────────────────┤
│ 5. Competitor benchmark         │  ← e.g. Mobileye ASP as a price ceiling
│    (lowest certainty)           │     (lowest certainty — prices are sticky)
└─────────────────────────────────┘
```

When two methods conflict, **the higher-certainty one wins** and you document
the override. This is why the model's `source` field on every `Driver` matters:
it records *which rung of the pyramid* produced the number, so the forecast is
defensible in front of a PM.

---

## Principle 5 — History first, then forecast (never simultaneously)

The Excel builder physically separates historical and forecast columns, and
**leaves forecast values blank until the historical model ties out**:

- Historical columns: filled with **input data + formulas** (the model must
  reproduce history before you trust it with the future).
- Forecast columns (orange tint): **structure reserved, values blank**.

This enforces a discipline that manual modeling constantly violates: people
start filling in 2027 guesses before they've checked whether 2022–2024 even
adds up. By forcing "history must tie out first," `excel_builder` turns the
workflow into a verification gate. The `IF(OR(...=""),"",...)` revenue formula
means a forecast column stays empty until **all four drivers** are filled — no
half-entered garbage revenue numbers.

---

## Why this is rare on GitHub

Most open-source finance tools cover **trading / backtesting** (zipline,
backtrader, QuantLib, vnpy) — they answer *"does this signal make money?"*
Driver-based revenue forecasting answers a different question:
*"what will this company's revenue be, and how do I defend each assumption?"*
That is fundamental analysis — what sell-side research notes and PE
investment memos are built on — and it has almost **no open-source tooling**.

`revenue-model-builder` is a minimal, runnable encoding of that workflow. It
will not replace a junior analyst, but it makes the methodology explicit,
auditable, and reusable — and it is a starting point others can extend with
real data sources, multi-market drivers, and automated driver extraction.

---

## Validation layer — cross-checks beyond the core five

The five principles above are about *building* the model. Three more are about
*not trusting it blindly*:

### Triangulation

Forecast the same number **three independent ways** and cross-check:

| Method | Starts from | Formula |
|---|---|---|
| **Bottom-up** (this engine) | unit economics | `base × penetration × share × price` |
| **Top-down** | total market size | `market_size × segment_%` |
| **Value theory** | value delivered | `(value_per_customer × customers) × capture_%` |

If they disagree by **>2–3×**, your assumptions need scrutiny — not averaging.
This is why `Driver.source` matters: it records *which method* produced each
number, so triangulation is auditable instead of hand-waved.

### Assumption documentation

Every `Driver` already carries `source` + `level`. Take the habit further: for
each C-grade estimate, record not just *where it came from*, but *how wrong it
could be* (a ± range) and *the revenue impact* if it is wrong. This turns
sensitivity analysis from an afterthought into a structured discipline — and is
exactly what the planned Monte Carlo module consumes.

```python
# target API for the planned sensitivity layer:
Driver("penetration", PENETRATION, {2024: 0.09}, level="C",
       source="research institute",
       range=(0.07, 0.12),        # ± uncertainty, for Monte Carlo
       impact="direct")            # how it propagates to revenue
```

### S-curve adoption (the deeper why behind Principle 3)

Principle 3 says "increment, not growth rate." That's the **linear middle** of
an adoption S-curve. Real adoption is S-shaped — slow start (early adopters),
near-linear middle (mass market), plateau (saturation toward 100%).

```
penetration
  │            ___________  ← plateau (saturation)
  │           /
  │          /  ← linear middle (increment rule ≈ this)
  │         /
  │    ___/  ← slow start
  │___
  └────────────────────── time
```

For **short** horizons the linear increment is an excellent approximation. For
**long** horizons (10+ years toward saturation), model penetration as a logistic
curve $p(t) = \dfrac{L}{1 + e^{-k(t-t_0)}}$ — but **never** as a constant growth rate,
which explodes past 100%. The invariant: *bounded ratios grow toward an
asymptote, not exponentially.*

---

## 中文摘要

- **差额行是结构性设计，绝不反推**：用行业真实渗透率，模型分项必然 ≠ 年报总收入。差额行吸收未建模业务（售后、IoT、定制开发）。反推渗透率看似"对齐"了，实则把失真的参数带进预测期，未来全错。健康差额比例 10–30%，0% 才是危险信号。
- **ABC 数据等级**：A=年报硬数据(黑)、B=第三方(蓝)、C=估算(红)。每个数字标注来源，让模型可追溯、可审计。
- **渗透率用增量法不用增速法**：有界变量（趋近100%）用「+X个百分点」线性外推，符合S曲线中段；用增速法会指数爆炸、不可信。
- **预测方法论优先级（确定性金字塔）**：法规政策催化 > 行业锚点 > 历史趋势 > 产品时间线 > 竞品对标。冲突时高确定性优先，并在 source 字段记录依据。
- **先历史后预测**：历史列必须先对齐（输入+公式），预测列保留结构留空（橙色），直到历史 tie out。收入公式用 IF 保护，避免半填数据产生垃圾结果。

这些是卖方分析师和 PE 投资经理手工建模时的硬核 know-how，踩过坑才写得出来——也正是本库区别于市面量化回测工具的核心价值。
