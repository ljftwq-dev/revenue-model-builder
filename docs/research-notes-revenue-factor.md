# Research notes — revenue as a multi-factor model

*Working research direction (post v0.16 / post Track-A validation). Framing,
literature anchors, two identified gaps with found solutions, and a concrete
minimal research design. Written 2026-09-11 from a literature + web sweep;
citations verified at time of writing.*

> 中文摘要见文末。

## 1. The framing

Sell-side and quant research decompose **returns** with multi-factor models
(`r_i = Σ β_k·f_k + ε`, factors priced cross-sectionally). The open question
this project keeps circling: can the **fundamental quantity itself** —
revenue — be modeled the same way?

```
g(i,t) = α + β₁·own-momentum(i,t) + β₂·growth-reversion(i,t)
       + β₃·industry-cycle(i,t) + β₄·macro(i,t) + γ_i + ε(i,t)
```

Three properties make this **more tractable** than return factor models:

1. **No pricing requirement** — factors are mechanical/causal inputs
   (GDP elasticity, penetration, ASP), not risk premia. Betas are physical
   quantities ("durable-goods orders +1% → revenue +0.4%") and far more
   stable than return betas.
2. **Signal-to-noise is inverted** — returns are near-zero-SNR daily; revenue
   is persistent at annual/quarterly frequency (Track A pooled sMAPE 4–7%
   ⇒ high R²). The hard part is not noise, it is **structural breaks**
   (the NVDA Data Center lesson: the future is not in the training data).
3. **The toolkit is panel econometrics, not asset pricing** — firm fixed
   effects, clustered standard errors, rolling validation; all standard.

## 2. What the project already has (≈40% of a thesis)

| Piece | In repo | Role in the factor framing |
|---|---|---|
| 244-company × FY2015-25 revenue panel | `examples/profile_validation/data/` | the estimation sample |
| 8-method battery incl. 3 profile-implied methods | backtest + `profile_methods.py` | the "experts" (factor realizations) |
| Industry profiles (fit classes, checks) | `revenue_model/industry.py` | cross-sectional conditioning (β₃) |
| Macro revision loop (elasticity, lag, evidence) | `qesa_adapter` / `macro_revision` | β₄ with transmission structure |
| Event layer (honest null at monthly/large-cap) | `news_impact` / `form8k_adapter` | event factor: documented zero |
| Pre-registered validation discipline | `proposal-profile-validation.md` | credibility |

Track-A test-year evidence that factor structure exists: the best
profile-implied method varies by fit class (DecelCAGR→strong 6.6%,
GrowthRevert→adapt 3.6%, Damped→weak 5.1%) — i.e., "method × industry"
behaves like **exposures**, not noise.

## 3. Gap 1 — formal estimation of method loadings

**The gap:** v0.16 hard-assigns one method family per industry profile. The
upgrade is *soft weights*: estimate, on the panel, how much of each expert
each industry (or series) should load on.

**Found solution — FFORMA.** Montero-Manso, Athanasopoulos, Hyndman &
Talagala (2020), *FFORMA: Feature-based forecast model averaging*,
International Journal of Forecasting 36(1), 86–92 (M4-competition winner;
450+ citations; R package `pmontman/fforma`). Two phases:

1. extract time-series **features** (trend strength, seasonality, curvature,
   volatility, …);
2. a gradient-boosting **meta-learner** predicts per-method weights
   minimizing combined loss — trained **globally across series**.

Mapping to us: features = damped-momentum score, mean-reversion score,
volatility, CAGR, fit-class dummies; experts = the 8-method battery.

**Honest clauses (from the forecast-combination literature):**

- **The combination puzzle** — four decades of evidence that *estimated
  optimal weights often lose to the simple average* (survey: Genre et al.
  2012, "Combining expert forecasts: Can anything beat the simple average?",
  IJF; theory: Claeskens, Magnus, Vasnev & Wang 2016, *A simple theoretical
  explanation of the forecast combination puzzle*; recent: Elliott 2026,
  *On why averaging beats optimal linear weights*, JASA/JABES). ⇒ an
  **equal-weight damped-family benchmark is mandatory**; the meta-learner
  must beat it to earn its complexity.
- **Globalization is the escape hatch** — Thompson (2024), *Flexible global
  forecast combinations*, IJF: pooling weight estimation across series is one
  of the few designs that beats equal weights. Our panel is exactly that
  setting.
- **Scale warning** — 244 series × 11 annual points is tiny vs M4. The
  meta-model must be minimal (multinomial logit or heavily-shrunk GBM); deep
  mixture-of-experts (LeMoLE 2412.00053, WaveMoE 2604.10544, Ziel & El
  Mahtout 2605.10330's expert-loss gating) would overfit — cite, do not ship.

## 4. Gap 2 — testing against expectations (the surprise layer)

**The gap:** revenue forecasting earns its keep at the moment it disagrees
with consensus. The test: `(model forecast − consensus)` vs realized
surprise vs post-announcement drift.

**Literature anchor.** Jegadeesh & Livnat (2006), *Revenue surprises and
stock returns*, **Journal of Accounting and Economics** 41(1-2), 147–171
(539+ citations). Four findings that double as our test-design checklist:

1. revenue surprises relate to contemporaneous **and future** returns;
2. analysts **under-react** to revenue surprises (slow revision);
3. PEAD is stronger when revenue and earnings surprises **align in
   direction** (interaction to replicate);
4. reactions are larger for **R&D-intensive** firms (context split).

**The novel bit (not in JL2006):** an *independent* bottom-up revenue model
as a third input. Question: does `(our forecast − pre-announcement
consensus)` predict (a) the signed surprise and (b) the drift, incremental to
consensus dispersion/revision momentum? A genuinely new angle — 2006 had no
such model.

**Data path.** WRDS / IBES Summary History (point-in-time monthly consensus,
**revenue** estimates included). UIUC holds a WRDS subscription (Gies
faculty publish with it; library data service `bis@library.illinois.edu`);
student account on request. Free fallback for a live/forward version only:
stockanalysis.com analyst estimates via the existing `sa_adapter` (no
history). Estimize on WRDS as robustness.

## 5. Minimal viable research design

1. **Panel A (done)**: battery × fit-class validation — ship as
   `docs/profile-validation.md`.
2. **Panel B**: FFORMA-mini — features → equal-weight benchmark vs shrunk
   multinomial-logit weights; pre-registered; report win/loss vs benchmark
   honestly (the puzzle clause).
3. **Panel C**: with WRDS/IBES — consensus alignment panel; surprise
   direction hit-rate of `(model − consensus)` gap; PEAD double-sort
   (gap × earnings-surprise alignment, replicating JL2006 finding 3 with a
   model-based twist).
4. Thesis-scale narrative: *industry is a factor-loading conditioner, not a
   label* — v0.16's profiles are the coarse prior, the estimated loadings
   the refinement, and the weak-fit redirect the risk model.

## 6. Reference list

- Montero-Manso P., Athanasopoulos G., Hyndman R.J., Talagala T.S. (2020).
  FFORMA: Feature-based forecast model averaging. *IJF* 36(1) 86–92.
- Genre V., Kenny G., Meyler A., Timmermann A. (2012). Combining expert
  forecasts: Can anything beat the simple average? *IJF*.
- Claeskens G., Magnus J.R., Vasnev A.L., Wang W. (2016). A simple
  theoretical explanation of the forecast combination puzzle.
- Elliott G. (2026). On why averaging beats optimal linear weights.
- Thompson R. (2024). Flexible global forecast combinations. *IJF*.
- Jegadeesh N., Livnat J. (2006). Revenue surprises and stock returns.
  *JAE* 41(1-2) 147–171.
- Ziel F., El Mahtout B. (2026). Fast training of MoE for TSF via expert
  loss integration. arXiv:2605.10330.

---

## 中文摘要

- **构想**：营收本身可做多因子模型——因子无需定价（是物理弹性）、信噪比远高于收益（难点在结构突变而非噪声）、工具是面板计量（公司固定效应+聚类SE）。
- **项目已有约四成**：244 家收入面板、8 方法电池、行业画像条件、宏观弹性链、事件层（诚实 null）、预注册纪律。
- **缺口一（方法载荷估计）→ FFORMA**（2020 IJF，M4 冠军，被引 450+）：序列特征→元学习器预测方法权重，全局训练。诚实条款：组合预测谜题（等权平均极难打败，Genre 2012 / Claeskens 2016 / Elliott 2026）——等权基准强制在场；全局化估计（Thompson 2024）是少数胜出路径恰为我们设定；样本小（244×11），元模型必须极小，深 MoE 只引不用。
- **缺口二（惊喜检验）→ JL2006**（JAE 被引 539，四发现=检验清单：营收惊喜预测当期+未来收益、分析师反应不足、营收盈利同向 PEAD 更强、R&D 密集反应大）。创新点：以独立自下而上模型为第三输入，"(模型−一致预期)"gap 能否增量预测惊喜与漂移。
- **数据钥匙**：UIUC 可申请 WRDS / IBES Summary History（含 point-in-time 营收预期；图书馆 bis@library.illinois.edu）。
- **最小可行设计**：A 面板（已完成）→ B 面板（FFORMA-mini vs 等权基准）→ C 面板（consensus 对齐 + PEAD 双排序）。
- **论文叙事**：行业不是标签，是因子载荷调节器——画像是粗先验，载荷估计是细化，weak 档重定向是风险模型。
