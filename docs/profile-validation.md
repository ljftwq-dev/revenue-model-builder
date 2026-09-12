# Profile validation — does the industry-fit matrix survive its own pre-registered test?

*The v0.16 claim — "a driver tree's accuracy is a property of the industry's
growth mechanism" — was powered by two single-company natural experiments.
This is the multi-company, pre-registered, out-of-sample follow-up: 244
S&P 500 constituents (anti-survivorship anchor 2023-12-31) at the revenue
layer, six hand-built driver trees at the layer the claim is actually about.
Spec frozen before any test data was pulled
([proposal](proposal-profile-validation.md), commit 20f32fc). Not investment
advice.*

## 1. The pre-registered scorecard

Three hypotheses, one null, written before the data:

| ID | Hypothesis | Verdict |
|---|---|---|
| H1 | strong-fit: profile-default (trend family) beats naive | **Rejected** at the company-total layer; **directionally supported** at the driver layer, but on a single legacy tree (NVDA Gaming 3.0% vs 10.9%) |
| H2 | adapt-fit: damped/held factors beat one-size trend | **Partially supported** (revenue layer: p_adj = 0.020 validation, 0.064 test; driver layer: 2 of 3 trees win) |
| H3 | weak-fit: point forecasts fail **and the engine says so in advance** | **Supported, cleanly**: warning hit rate 2/2, false-alarm rate 0/4, MC P10–P90 framed all three weak-fit test years |
| H0 | profiles add nothing | **Rejected where it matters** (driver layer, weak-fit redirect) — but the revenue-total layer belongs to Naive, and the README claim is narrowed accordingly (§5) |

## 2. Track A — the revenue-total layer: statistics wins, one profile graduates

244 companies, 8 methods, expanding window, horizon 1. Validation FY2023-24
(method selection), test FY2025 (touched once, as-is). Pooled median sMAPE:

| method | strong (n=37 co-yr) | adapt (n=128) | weak (n=79) | FY2025 all | dir% |
|---|---|---|---|---|---|
| Naive | 12.3% | 5.2% | 6.8% | 6.7% | 0%† |
| Linear | 12.6% | 9.2% | 10.5% | 10.6% | 52% |
| ARIMA | 11.0% | 3.6% | 6.5% | 5.2% | 66% |
| **Damped** (profile-implied) | 7.4% | **4.5%** | **5.1%** | **5.1%** | **74%** |
| **DecelCAGR** (profile-implied) | 6.6% | 4.0% | 5.5% | 5.1% | 73% |
| GrowthRevert (profile-implied) | 7.2% | 3.6% | 7.0% | **4.3%** | 73% |

*full tables incl. P90 dispersion and Wilcoxon inference:
`examples/profile_validation/data/analysis_summary.txt`. † Naive predicts
flat, so YoY-direction is undefined-by-construction (scored 0).*

Findings, including the uncomfortable ones:

1. **H1 null at the totals layer.** On strong-fit companies (semis,
   consumer electronics — the *v0.16 flagship* fit classes), Naive's median
   beats the trend family on validation (10.0% vs 11.6-11.8%), and the
   Wilcoxon never clears Bonferroni in either direction. At the
   company-total layer, diversified issuers blur the mechanism — exactly the
   noise the spec pre-registered ("diversified issuers blur the mechanism at
   company level; attributed in the report").
2. **H2 partial.** Damped beats Naive on the adapt bucket on validation
   (−1.23pp, p_adj = 0.020, r = −0.22) and repeats the direction on test
   (−1.62pp, p_adj = 0.064, r = −0.28) — one notch short of surviving
   Bonferroni twice. Damped also posts the best directional accuracy on
   test (74%).
3. **The SaaS shape method graduates.** DecelCAGR — the revenue-layer
   translation of the saas/logistic default — beats Naive **on its home
   profile** with the two largest effect sizes in the entire battery:
   −5.74pp (p_adj = 0.0009, r = −0.68) validation, −7.18pp (p_adj = 0.0164,
   r = −0.77) test. This is the pre-registered graduation criterion,
   met twice. → v0.17: fold into `revenue_model.backtest` as a first-class
   method.
4. **GrowthRevert is honestly falsified at home.** On commodity_cyclical
   (its origin profile) it loses to Naive by **+9.28pp** on validation
   (p_adj < 0.0001, r = +0.76) — a decisive *negative*. On test the gap
   vanishes (−0.13pp) but that is regime luck, not vindication. It does not
   graduate; the null is published per the honest-failure clause.
5. **Industrial Damped does not clear at home** (+0.19pp, p = 0.75) — its
   value shows up pooled across the adapt bucket, not on its origin profile.
   Telecommunications has n = 3-6 company-years — no claim either way.

The layer conclusion echoes the project's own backtest finding: *on revenue
totals, statistics wins*. The profile story does not live at the totals
layer. It lives one layer down.

## 3. Track B — the driver layer: where the claim actually holds

Six hand-built trees, disclosed drivers, history ≤ FY2024, FY2025 opened
once. Profile-default forecast vs naive per-driver linear trend:

> **Scope note (honest deviation from the spec).** The proposal sketched
> 12-15 trees; five new ones were built before the list froze — the binding
> constraint was *disclosed* driver data (telecom connection counts failed
> source verification; only companies whose 10-K/8-K/releases expose real
> driver series qualified). The two NVDA trees carry the pre-existing demo
> split. n is small and each tree tests one year: Track B verdicts are
> **directional evidence, not a definitive sample**. Track A is the
> large-N leg; Track B is the mechanism leg.

| tree | profile (fit) | profile sMAPE | naive-trend sMAPE | winner |
|---|---|---|---|---|
| SBUX consolidated | retail_store (adapt) | **0.7%** | 3.6% | profile |
| META advertising | advertising (adapt) | **4.6%** | 6.7% | profile |
| NFLX streaming | saas_subscription (adapt) | 4.7% | **2.5%** | naive |
| NVDA Gaming | semiconductor (strong) | **3.0%** | 10.9% | profile |
| JPM NII | financial_interest (weak) | 17.7% | 3.8% | *neither — see below* |
| NVDA Data Center | regime_shift_tech (weak) | 57.9% | 57.9% | *neither, as designed* |

Reading:

1. **The mechanism, not the arithmetic, carries the accuracy.** The naive
   mode differs from the profile mode only in *which extrapolation each
   factor gets*. SBUX: mean-reverting sales-per-store beats trending it
   (0.7% vs 3.6%). NVDA Gaming: held ASP/share semantics beat
   everything-trends (3.0% vs 10.9%). Same numbers, same multiplication —
   the industry-aware defaults win because they encode how the factor moves.
2. **NFLX is the honest loss.** The logistic penetration (anchored at 0.232)
   under-forecasts 2025's ad-tier-driven reacceleration, and ARM's 2%
   escalator default trails the price-increase-heavy year. The naive trend
   happened to fit 2025's shape. One tree, one year — recorded, not excused.
3. **H3 is the cleanest result in the whole experiment.** Both weak-fit
   trees were flagged *before* the test opened:
   - JPM: *"anchor the yield to the forward policy-rate curve and run rate
     scenarios; treat balance-sheet growth as a credit-cycle variable, not
     a trend."* The profile point forecast then missed by +43% (yield
     mean-reverted toward its 4% target — structurally wrong for a
     rate-path asset), while the wide-band Monte Carlo placed the actual
     $95.4B at **P46** (P10 80.3, P90 113.4). The engine's advice was the
     correct forecast.
   - NVDA DC: both modes fail identically (57.9%) because regime-shift
     defaults are deliberately trend-based baselines — and the MC close-out
     framed both breakout years (FY24 P75, FY25 P66, both inside P10-P90,
     with the FY25 P90 tail at $164B framing the $115B actual).
   - Warning hit rate **2/2**, false-alarm rate **0/4** (adapt/strong trees
     got method *advice*, never "unreliable" alarms).

## 4. API findings (byproducts worth a v0.17 fix)

1. **`forecast_segment` param-resolves before checking coverage.** A driver
   already hand-extended to the forecast years still goes through
   `_apply_spec`, which anchors logistic `t0` on the last value — so a
   structural constant (1.0) on a logistic-default kind (saas penetration,
   L = 0.6) raises `ValueError` even though the hand extension should have
   won. Fix: skip spec resolution for years the driver already covers.
2. **Structural constants are semantically fragile.** Holding "ad load" at
   1.0 tripped the advertising check ("ad load 100% — well above the 10-30%
   platform norm") — correct check, artifact trigger. Trees should carry
   real fractions (the NFLX household-penetration restructure is the
   pattern) or the engine needs an explicit "structural" driver flag.

## 5. What this does to the README claim

The pre-registered clause said: *fail to beat naive on strong/adapt →
publish the null and downgrade*. The honest reading is narrower than either
triumph or null:

- At the **company-total** layer, profiles do not beat Naive (H1 null
  there) — and the README should not imply otherwise.
- At the **driver layer** — the layer the methodology actually teaches —
  profile defaults beat naive per-driver trending on 3 of 4 testable trees,
  including the flagship strong-fit case, and lose one honestly.
- The **weak-fit redirect is now a validated deliverable**, not a slogan:
  warnings fired 2/2 with 0/4 false alarms, and scenario bands framed all
  three weak-fit test years.
- **One shape method graduates** (DecelCAGR) with double significance; one
  is falsified at home (GrowthRevert) and stays out.

Claim wording updated in README backlink accordingly: *accuracy is a
property of the mechanism — at the driver layer the defaults encode it, at
the totals layer statistics dominates, and for weak-fit industries the
engine's redirect is the product.*

## 6. Artifacts

- `examples/profile_validation/` — universe builder, revenue pull, battery,
  profile methods, Track B trees + runner, all data CSVs/txt
- `data/analysis_summary.txt` (Track A inference), `data/track_b_results.txt`
  (driver-layer results + warning ledger)
- Sources: SEC XBRL (revenue panel, JPM NII/assets — end-year-mapped and
  re-verified), 10-K/8-K exhibits (SBUX stores: FY19/FY21-24 grepped from
  filings in-session; FY20 cited from the Q4 FY20 8-K), Q4 earnings
  releases (META impressions/price and 2022-2025 ad revenue fetched and
  read in-session; 2019-2021 ad revenue as published in the corresponding
  releases), 10-K/shareholder letters (NFLX memberships: FY23/FY24 counts
  grepped from 10-Ks in-session; earlier years as published). Driver
  grades A/B/C labeled per series in `track_b_trees.py`.

## 7. What goes into v0.17 (post-test discoveries — no retro-fitting)

1. Fold **DecelCAGR** (and **Damped** as runner-up) into
   `revenue_model.backtest` as first-class methods.
2. Fix `_apply_spec` coverage check (API finding #1).
3. Consider a "structural constant" driver flag (API finding #2).

---

## 中文摘要

- **预注册三假设的裁决**：H1（strong 档趋势法胜 naive）在公司总收入层**落空**、在 driver 层成立（NVDA Gaming 3.0% vs 10.9%）；H2（adapt 档阻尼族胜出）**部分成立**；H3（weak 档点预测失灵且引擎提前警告）**干净利落地成立**：警告命中 2/2、误报 0/4、蒙特卡洛 P10-P90 框住全部三个 weak 档测试年（JPM 实测落在 P46，NVDA DC 两年 P75/P66）。
- **SaaS 形状法毕业**：DecelCAGR 在主场两轮双显著（验证 -5.7pp p_adj=0.0009；测试 -7.2pp p_adj=0.0164，效应量 r≈-0.7），进 v0.17 一等方法；GrowthRevert 主场惨败（+9.3pp），按诚实条款公布否证。
- **收入层结论与项目既有发现同构**：总收入层统计基线（Naive/ARIMA/阻尼）难以击败，画像的价值主张在 driver 分解层——同乘法算式，只因每个因子拿到"符合行业机制的外推"而胜出。
- **README 声明收窄而非降级**：driver 层默认胜通用趋势（3/4）、weak 档重定向是验证过的交付物；绝不暗示"分行业预测总收入更准"。
