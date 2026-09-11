# Profile validation — do industry defaults beat naive methods out-of-sample?

*Proposal for the v0.16 industry-profile validation experiment. Pre-registered
hypotheses, splits, selection protocol, and honest-failure clauses — written
and reviewed **before** the test set is touched. Not investment advice.*

> **Decisions (frozen 2026-09-11)**: both tracks run (A first, B follows);
> universe = US equities only (A-share extension out of scope for this round).
> This document is committed before any test-set data is pulled — that commit
> is the pre-registration timestamp.

> 中文摘要见文末。

## 1. The question

v0.16's central claim — *a driver tree's accuracy is a property of the
industry's growth mechanism* — rests on two natural experiments (NVDA Gaming
1.0% vs Data Center 60% sMAPE; Luxun consumer-electronics −0.1% vs automotive
−51%), both single-company. The claim powered a whole release; it deserves a
multi-company, pre-registered, out-of-sample test. Three hypotheses:

- **H1 (strong)**: on strong-fit segments, profile-default forecasts beat
  naive linear trend (sMAPE, 1-yr holdout).
- **H2 (adapt)**: on adapt-fit segments, profile defaults (mean-reverting /
  held factors) beat one-size-fits-all trend.
- **H3 (weak)**: point forecasts fail on weak-fit segments **and the engine
  says so in advance** — warning hit rate is part of the deliverable.
- **H0**: profiles add nothing over naive. If so, we report the null and
  downgrade the README claim — the news-impact precedent stands.

## 2. Two-track design (the honest constraint: filings disclose revenue, not drivers)

10-Ks disclose **segment revenue**, not `base × penetration × share × price`.
Track B (the real v0.16 API) needs hand-built driver trees; Track A (cheap,
large-N) tests what filings alone can test.

### Track A — revenue layer, automated, ~80–120 segments

> *Implementation refinement (recorded before any data pull)*: Track A
> operates on **company-level total revenue** (one companyfacts call per
> company, cached) rather than largest-segment revenue — parsing 10-K segment
> footnotes for 150+ issuers is a project in itself, and segment-level rigor
> is what hand-built Track B is for. Known noise: diversified issuers blur
> the mechanism at company level; attributed in the report.

1. **Fit-class validation**: run the existing backtest battery
   (Naive / Linear / CAGR / Holt / ARIMA) per segment, **grouped by profile
   fit class**. Prediction: strong segments are won by trend-family methods
   with tight sMAPE; adapt/weak by damped or naive, with fat tails. This
   validates the classification itself — v0.16's foundation — at scale.
2. **Profile-implied shape methods**: add two revenue-layer methods derived
   from v0.16 driver defaults — *damped trend* (mean-reverting growth, from
   `mean_revert`/retail/advertising/commodity profiles) and *decelerating
   growth* (from `logistic`/saas/telecom profiles) — and test whether they
   win on the profiles they came from. If they do, they graduate into the
   backtest module as first-class methods (v0.17 candidate).

### Track B — driver layer, manual, ~12–15 segments (the real API test)

Hand-built driver trees (C-grade, sourced, NVDA/Luxun style) — 1–2 new
segments per profile beyond the 4 already built. Tests the actual v0.16
loop: `forecast_segment` (profile defaults vs naive per-driver trend) and
`check_segment` warnings. Driver-data friendliness drives company choice:
several profiles have **disclosed** drivers (telecom subscribers + ARPU in
MD&A; bank NII tables; SBUX store counts + comps) — those anchor A/B-grade
drivers; the rest use industry data (IDC/Gartner-class) honestly tagged C.

## 3. Selection protocol (anti-survivorship)

- **Anchor date**: constituents/market-cap ranking **as of 2023-12-31**
  (S&P 500 list from that date) — never "companies I know in 2026".
- Universe: US equities (SEC adapter mature; fiscal-year misalignment like
  NVDA's late-Jan FY already handled by `fetch_fiscal_quarters`). A-share
  extension optional later via tushare (Luxun already exists).
- Rule: the **largest reported revenue segment** per company (10-K segment
  footnote).
- Proposed Track-B coverage (swap names freely at review time — final list
  freezes when the test set opens):

| profile | candidates | driver availability |
|---|---|---|
| consumer_electronics | HPQ, LOGI | IDC unit data (C) |
| semiconductor | TSM, QCOM | industry units (C) |
| saas_subscription | CRM, NOW | disclosed customers/rpo (B) |
| advertising | META-ads, GOOGL-Services | disclosed impressions/price (B) |
| retail_store | SBUX, WMT | disclosed stores + comps (A/B) |
| telecom_subscriber | VZ, T | disclosed subs + ARPU (A/B) |
| industrial_capacity | CAT, DE | disclosed volumes/rates (B) |
| financial_interest | JPM, BAC | disclosed NII + rate sensitivity (A) |
| commodity_cyclical | NUE, NEM | volumes disclosed, price = spot (B/C) |
| regime_shift_tech | NVDA (built), SMCI or TSLA | estimates (C) |

## 4. Splits & timeline

| split | data | role |
|---|---|---|
| Train | ≤ FY2022 | driver-tree history / revenue history (no fitted params — profiles are priors, not regressions) |
| Valid | FY2023–2024 | **method selection**: profile-default vs alternates; parameter sanity (erosion rate, revert speed); the only place tuning is allowed |
| Test | FY2025 + FY2026 disclosed quarters (Q1/H1) | touched **once**, published as-is, no re-tuning |

Test-year alignment: fiscal years **ending in calendar 2025** count as the
2025 test slice; 2026 = disclosed quarters only (full-year FY2026 annual
reports do not exist yet — A-share ones arrive 2027).

## 5. Metrics & statistics

- Primary: sMAPE (1-yr holdout), **pooled median by fit class** — single
  companies are noise; pooling is the design (news-impact discipline).
- Directional accuracy (YoY sign hit rate).
- Method-win rate per profile (does the profile-implied family win?).
- Track B only: **warning hit rate** (weak segments warned) and **false-alarm
  rate** (strong segments wrongly warned); scenario coverage for weak
  segments (did P10–P90 frame the actual?).
- Inference: paired Wilcoxon signed-rank (profile vs naive per segment —
  pure-stdlib implementation alongside news_impact's MWU), Bonferroni over
  the 10-profile family; effect sizes over p-values (annual data = tiny n).

## 6. Honest-failure clauses

- Profile defaults fail to beat naive on strong/adapt → publish the null and
  downgrade README claims; profiles keep pedagogical value only.
- 2025 known shocks (tariffs, AI-capex boom, rate path) will hit specific
  profiles — attributed per segment in the report, never dropped.
- Segment restatements: use as-reported-at-the-time where retrievable;
  reclassifications noted per company otherwise.
- The test set is never re-opened after results are computed. Discoveries →
  v0.17 work, not retro-fits.

## 7. Deliverables

- `examples/profile_validation/` — data CSVs, run scripts (Track A battery +
  Track B trees), README, findings
- `docs/profile-validation.md` — the report, news-impact style (results
  good or bad are the content)
- If Track A-2 shape methods prove out → folded into `backtest/` as methods
- CHANGELOG entry

## 8. Effort estimate

| piece | estimate |
|---|---|
| Track A: pull + battery + fit-class grouping | ~1 day |
| Track B: ~10 new driver trees × ~1.5h + runs | ~2 days |
| Statistics + report | ~1 day |

---

## 中文摘要

- **问题**：v0.16 的核心论点（精度是行业属性）只靠 NVDA/立讯两个单公司实验支撑，需要多公司、预注册、外样本的独立验证。
- **两线设计**：A 线（自动、80–120 段）——只用财报分部收入，验证"适配档分类"本身 + 两个从画像推导的收入层新方法（阻尼趋势/减速增长）；B 线（手工、12–15 段）——真实 driver 树 + v0.16 全链路（含警告命中率与情景覆盖率）。
- **防幸存者偏差**：以 2023-12-31 时点的标普成分选股，绝不用 2026 年的"知名公司"回选。
- **分割**：≤FY2022 训练（画像先验不拟合参数）→ FY2023–24 验证（唯一允许调方法/参数的地方）→ FY2025 + 2026 已披露季度只碰一次。
- **统计**：按适配档 pooled 中位 sMAPE + Wilcoxon 符号秩 + Bonferroni；效应量优先于 p 值。
- **诚实条款**：画像打不过 naive 就发 null 结果并降级 README 声明；2025 冲击逐段归因不隐藏；测试集开完不回头。
- **工作量**：A 线 1 天、B 线 2 天、统计报告 1 天，合计约 4 天。
