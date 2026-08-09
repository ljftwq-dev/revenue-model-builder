# Industry-Fit Analysis — Where Driver Trees Work, and Where They Break

> The flagship methodology document. The NVIDIA demo proves the thesis on real
> U.S. equity data; this document generalizes it into a practitioner's framework
> for *when* a driver tree is the right tool, when it isn't, and what to do
> instead.
>
> 中文要点见文末 **中文摘要** 小节。

Most revenue-forecasting tools sell you on accuracy. This one sells you on
**where it is accurate, and just as importantly, where it isn't**. The honest
answer turns out to be more useful than a confident wrong one.

The central claim, proven two ways below:

> **A driver tree's accuracy is a property of the *industry's growth mechanism*,
> not of the formula.** It is excellent where growth continues its history, and
> structurally unreliable where a regime shift breaks that history — and no
> amount of trend-fitting closes the second gap, because the future is simply
> not in the training data.

---

## 1. The core claim

Driver-based (bottom-up) forecasting decomposes revenue into a product of
measurable factors:

```
segment_revenue = market_base × penetration × share × price
```

The method is internally sound — *if* each factor is independently forecastable
from its own history. That "if" does all the work. It holds cleanly for mature,
trend-driven industries and breaks for event-driven ones. The mistake is to
treat the method as universally right or universally wrong; it is neither. It is
**conditional**, and the condition is whether the industry's growth mechanism is
trend-extrapolatable.

Two natural experiments, one per market, make this unmistakable.

---

## 2. Industry-fit matrix

| Fit | Growth mechanism | Examples | Driver tree verdict |
|---|---|---|---|
| **Strong** | Secular trend — factors continue their history | Consumer electronics, semiconductors, auto parts, branded pharma | Use it; back-test will be tight |
| **Adapt** | Structured but different math | SaaS (`MAU × ARPU`), Ads (`traffic × eCPM`), Subscriptions (`churn × ARPU`) | Use the *form*, swap the factors |
| **Weak / avoid** | Event- or cycle-driven | Commodities (steel, shipping), Financials (balance-sheet driven), Resources (reserve-constrained), **regime-shift tech** | Point-forecast will fail; jump to scenarios |

The bottom row is not a condemnation — it is a redirect. For those industries the
honest move is not a more clever trend, it is the scenario framework in §4.

---

## 3. NVIDIA: one company, two verdicts

The NVIDIA demo (`examples/nvda_demo/`) is the strongest possible test, because
it removes every confounder: **the same company, the same fiscal years, the same
driver tree, the same engine, the same extrapolation rule.** The only thing that
differs between the two segments is the industry's growth mechanism.

Trained on FY2019-FY2023, hold-out FY2024-FY2025 (the AI breakout):

| Segment | Industry type | Hold-out sMAPE | FY2025 error |
|---|---|---|---|
| **Gaming** | mature, trend | **1.0%** | +4% |
| **Data Center** | AI regime shift | **60.0%** | **−84%** (actual \$115B vs forecast \$18B) |

A 60× error gap on the *same formula*. Gaming is a trend market — GPU shipments,
attach rates, and ASPs all continue their history, so the tree lands within 4%.
Data Center is a paradigm shift — the post-ChatGPT acceleration is not in any
pre-2024 trend, so extrapolation under-predicts by 6×.

This mirrors the earlier Luxun (立讯精密) result from v0.5.0: consumer electronics
driver tree at **−0.1%** sMAPE vs automotive at **−51%** (Leoni acquisition). One
A-share industrial, one U.S. mega-cap — the pattern holds across markets.

> **Insight:** when the same method gives 1% on one segment and 60% on another
> of the *same company*, the variable is unambiguous. It is the segment, not the
> model. Blaming the model here would be like blaming a thermometer for a fever.

---

## 4. What to do when growth is event-driven

Point forecasting from history is the wrong tool under a regime shift. Replace
it with **uncertainty management** — five techniques, ordered from cheapest to
richest. `revenue-model-builder` supports the first directly and the third by
API.

**1. Scenario analysis.** Stop asking "what is the number?" and ask "what range
could it take, and what triggers each branch?" Build Bear / Base / Bull with
explicit trigger conditions. The demo's close-out does exactly this: a wide
Monte Carlo over honestly-uncertain Data Center drivers produces a distribution
whose Bull tail (P90) captures the actual FY2024-FY2025 breakout — the point
forecast collapsed, the scenario band framed the truth.

```python
from revenue_model import simulate_segment, scenarios
mc = simulate_segment(seg, year, driver_ranges, n=5000, seed=0)
bear, base, bull = scenarios(mc)   # P10, median, P90 — straight from the distribution
```

**2. Leading-indicator monitoring.** Track the *drivers of the drivers* — the
upstream signals (capex commitments, order books, capacity announcements) that
telegraph a regime shift before it hits revenue. Pair with change-point
detection or Bayesian structural time series.

**3. S-curves / Bass diffusion.** When adoption follows a saturation path, a
logistic or Bass model beats a blind trend. The library ships
`Driver(...).fit_trend(...).extrapolate(...)` with a `logistic` option precisely
for S-curve adoption; use a prior industry's curve (e.g. cloud build-out) as a
template for the next one (AI accelerators).

**4. Causal / counterfactual reasoning.** Model the *mechanism* — the chain from
trigger to revenue — rather than fitting the historical pattern. "If hyperscaler
capex rises 40%, accelerator shipments rise X" is a causal claim you can stress
test, not a coefficient you extrapolate.

**5. Bayesian updating.** Under genuine uncertainty, start with an expert prior
and update it as the event unfolds. The first two quarters of a breakout are
worth more than five years of pre-breakout history; Bayesian updating lets the
model *learn* the shift instead of denying it.

> **Rule:** under a regime shift, point prediction is a category error. Switch
> to scenarios (bound it), leading indicators (anticipate it), S-curves (shape
> it), causal models (explain it), or Bayesian updating (learn it). The honest
> framework picks the right one instead of hiding behind a trend line.

---

## 5. Why revenue-model-builder chooses honesty

Most forecasting codebases report a number and a confidence interval and stop.
This one treats uncertainty as a first-class citizen, in four concrete ways:

- **ABC data grading** — every driver value carries a credibility tag (A =
  official filing, B = third-party industry data, C = estimate). A reviewer sees
  at a glance which columns are facts and which are guesses. The NVIDIA demo's
  Data Center drivers are *almost all C-grade* — and that is reflected openly in
  `data/sources.md`, not hidden.
- **A structural residual line** — penetration is never back-solved to force the
  segments to tie to the total. The gap stays visible, so the model never lies
  about its own completeness.
- **A certainty pyramid** — forecast inputs are ranked by how knowable they are,
  and the most certain inputs drive the forecast, not the most convenient ones.
- **Back-testing that exposes limits** — the library's own hold-out tests
  *publish* where it fails (1% on Gaming, 60% on Data Center), instead of only
  reporting where it succeeds.

The payoff is not pessimism. It is that a user of the model never gets
ambushed: they know exactly where to trust it and where to override it.

---

## 6. A practitioner's decision guide

```
Is the industry's growth a continuation of history?
│
├─ YES (mature, trend-driven) ─────► driver tree, point-forecast, back-test to confirm
│                                     (consumer electronics, semis, auto parts, pharma)
│
├─ STRUCTURED but different math ──► driver tree with swapped factors
│                                     (SaaS: MAU×ARPU, Ads: traffic×eCPM)
│
└─ NO (event / cycle / regime) ────► scenarios + leading indicators
                                      (commodities, financials, AI-inflection tech)
```

Three practical rules of thumb:

1. **Back-test before you trust.** If a one-year hold-out gives >25% sMAPE across
   methods, the industry is telling you it is not trend-extrapolatable. Listen.
2. **Grade your inputs.** A model is only as honest as its weakest-tagged column.
   If everything is C-grade, the wide scenario band is the deliverable, not the
   point forecast.
3. **Report the boundary, not just the center.** A forecast that says "Base \$18B,
   Bull \$115B, and here is why they differ" is more useful than one that says
   "\$18B" with a false sense of precision.

---

## The differentiator

The market is saturated with projects that advertise accuracy. Almost none use a
real, recognizable company to honestly demonstrate **the boundary of their own
method** — where it is sharp (Gaming, 1%) and where it goes dull (Data Center,
60%), and what to do in the dull region. That honesty is the product. A model
that admits "I don't know, but here is the range and the trigger" beats one that
prints a confident number and is wrong by 6×.

---

## 中文摘要

- **核心论点**：driver tree（自下而上收入分解）的准确性取决于**行业增长机制是否可趋势外推**，而非公式本身。趋势延续型行业（消费电子/半导体）极准，事件驱动型（AI 爆发/收购/周期）结构性失效——而任何趋势拟合都无法弥补后者，因为未来不在训练数据里。
- **NVDA 实证**：同一公司、同一公式、同一年份——Gaming sMAPE **1.0%**（趋势准），Data Center sMAPE **60%**（AI 爆发崩，真实 \$115B vs 预测 \$18B）。60 倍差距，变量只有行业。
- **行业适配性**：契合（趋势型）/ 改造（SaaS·MAU×ARPU、广告·流量×eCPM）/ 不契合（周期品、金融、资源、范式跳变科技）。
- **事件驱动怎么办**：点预测注定错，改用 5 招——情景分析（Bear/Base/Bull + 触发条件）、领先指标监测、S 曲线/Bass 扩散、因果推理、贝叶斯更新。
- **为什么 rmb 选择诚实**：ABC 数据分级 + 结构性 residual + certainty pyramid + 回测主动暴露局限——把不确定性当一等公民，让用户永远不被模型"突袭"。
- **差异化**：市面上几乎没有用真实美股案例诚实论证 driver tree 边界的方法论。多数项目只吹"多准"，rmb 敢说"哪里准、哪里崩、崩了怎么办"——这才是有用的。
