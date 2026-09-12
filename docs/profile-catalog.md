# Profile catalog

*Generated from `INDUSTRY_PROFILES` — run `examples/profile_catalog/render_catalog.py` after changing the registry; the page never drifts from code.*

| key | industry | fit | base default | checks | benchmarks |
|---|---|---|---|---|---|
| [consumer_electronics](#consumer_electronics) | Consumer electronics / hardware | strong | trend | asp_rising | 2 bands |
| [semiconductor](#semiconductor) | Semiconductors (mature cycles) | strong | trend | hypergrowth_base | 2 bands |
| [saas_subscription](#saas_subscription) | SaaS / subscription | adapt | net_growth | arpu_accelerating, net_churn_positive | 2 bands |
| [advertising](#advertising) | Advertising | adapt | trend | adload_high | 2 bands |
| [retail_store](#retail_store) | Retail (store network) | adapt | trend | shrinking_base | 2 bands |
| [telecom_subscriber](#telecom_subscriber) | Telecom / subscribers | adapt | net_growth | base_saturated, net_churn_positive | 2 bands |
| [industrial_capacity](#industrial_capacity) | Industrial / capacity-driven | adapt | trend | utilization_cap | 2 bands |
| [financial_interest](#financial_interest) | Financials (interest income) | weak | growth | balance_growth_hot | 2 bands |
| [commodity_cyclical](#commodity_cyclical) | Commodities / cyclical | weak | hold | cycle_top | 2 bands |
| [regime_shift_tech](#regime_shift_tech) | Regime-shift tech (AI inflection) | weak | trend | regime_always | — |

## consumer_electronics

**Consumer electronics / hardware** · 消费电子 / 硬件 · **fit: strong** — trend-driven: shipments, attach rates and ASPs continue their history (Luxun consumer-electronics hold-out −0.1% sMAPE)

| driver | default method | params |
|---|---|---|
| base | `trend` | — |
| penetration | `incremental` | delta_pp=0.02 |
| share | `hold` | — |
| price | `erosion` | rate=0.05 |

**checks**: `asp_rising`

**benchmarks** (Damodaran US clusters, 2026-01, grade B):

| metric | P25 | P50 | P75 | cluster |
|---|---|---|---|---|
| revenue_cagr_5y | 4.2% | 7.0% | 7.5% | Electronics (Consumer & Office), Electronics (General), Computers/Peripherals, Office Equipment & Services |
| revenue_exp_growth_2y | 1.2% | 10.2% | 19.8% | Electronics (Consumer & Office), Electronics (General), Computers/Peripherals, Office Equipment & Services |

## semiconductor

**Semiconductors (mature cycles)** · 半导体（成熟周期） · **fit: strong** — mature-semi factors trend until they don't (NVDA Gaming 1.0% sMAPE); ASPs hold rather than erode (pricing power per node), attach rates are structural product-cycle choices (held)

| driver | default method | params |
|---|---|---|
| base | `trend` | — |
| penetration | `hold` | — |
| share | `hold` | — |
| price | `hold` | — |

**checks**: `hypergrowth_base`

**benchmarks** (Damodaran US clusters, 2026-01, grade B):

| metric | P25 | P50 | P75 | cluster |
|---|---|---|---|---|
| revenue_cagr_5y | 9.8% | 10.3% | 10.7% | Semiconductor, Semiconductor Equip |
| revenue_exp_growth_2y | 19.2% | 26.4% | 33.7% | Semiconductor, Semiconductor Equip |

## saas_subscription

**SaaS / subscription** · SaaS / 订阅 · **fit: adapt** — MAU/customers × ARPU: adoption follows an S-curve, ARPU grows by escalator — the tree works with swapped factors

| driver | default method | params |
|---|---|---|
| base | `net_growth` | gross_rate=0.3, churn=0.12 |
| penetration | `logistic` | L=0.6, k=0.35, t0=anchor_last |
| share | `hold` | — |
| price | `growth` | rate=0.02 |

**checks**: `arpu_accelerating`, `net_churn_positive`

**benchmarks** (Damodaran US clusters, 2026-01, grade B):

| metric | P25 | P50 | P75 | cluster |
|---|---|---|---|---|
| revenue_cagr_5y | 16.4% | 23.3% | 27.6% | Software (System & Application), Software (Internet), Computer Services, Information Services |
| revenue_exp_growth_2y | 11.9% | 18.7% | 26.4% | Software (System & Application), Software (Internet), Computer Services, Information Services |

## advertising

**Advertising** · 广告 · **fit: adapt** — traffic × ad-load × eCPM: ad load is sticky (product choice), eCPM is cyclical and mean-reverts with the ad market

| driver | default method | params |
|---|---|---|
| base | `trend` | — |
| penetration | `hold` | — |
| share | `hold` | — |
| price | `mean_revert` | target=None, speed=0.3 |

**checks**: `adload_high`

**benchmarks** (Damodaran US clusters, 2026-01, grade B):

| metric | P25 | P50 | P75 | cluster |
|---|---|---|---|---|
| revenue_cagr_5y | 6.3% | 12.4% | 16.7% | Advertising, Entertainment, Publishing & Newspapers, Broadcasting |
| revenue_exp_growth_2y | 0.5% | 4.6% | 8.3% | Advertising, Entertainment, Publishing & Newspapers, Broadcasting |

## retail_store

**Retail (store network)** · 零售（门店网络） · **fit: adapt** — stores × sales-per-store: openings are company-controlled (trend), same-store sales mean-revert to CPI + low single digits

| driver | default method | params |
|---|---|---|
| base | `trend` | — |
| penetration | `hold` | — |
| share | `hold` | — |
| price | `mean_revert` | target=None, speed=0.5 |

**checks**: `shrinking_base`

**benchmarks** (Damodaran US clusters, 2026-01, grade B):

| metric | P25 | P50 | P75 | cluster |
|---|---|---|---|---|
| revenue_cagr_5y | 2.3% | 8.4% | 10.1% | Retail (General), Retail (Special Lines), Retail (Automotive), Retail (Building Supply), Retail (Grocery and Food), Retail (Distributors) |
| revenue_exp_growth_2y | 4.2% | 4.9% | 7.0% | Retail (General), Retail (Special Lines), Retail (Automotive), Retail (Building Supply), Retail (Grocery and Food), Retail (Distributors) |

## telecom_subscriber

**Telecom / subscribers** · 电信 / 用户数 · **fit: adapt** — subscribers × ARPU: subscriber growth saturates (logistic), ARPU drifts slowly and is policy-capped

| driver | default method | params |
|---|---|---|
| base | `net_growth` | gross_rate=0.05, churn=0.035 |
| penetration | `hold` | — |
| share | `hold` | — |
| price | `hold` | — |

**checks**: `base_saturated`, `net_churn_positive`

**benchmarks** (Damodaran US clusters, 2026-01, grade B):

| metric | P25 | P50 | P75 | cluster |
|---|---|---|---|---|
| revenue_cagr_5y | 8.6% | 13.6% | 20.3% | Telecom (Wireless), Telecom. Services, Cable TV |
| revenue_exp_growth_2y | -4.2% | -2.9% | 25.9% | Telecom (Wireless), Telecom. Services, Cable TV |

## industrial_capacity

**Industrial / capacity-driven** · 工业 / 产能驱动 · **fit: adapt** — capacity × utilization × price: utilization is bounded and mean-reverts (70–90%); capacity is a capex decision (trend)

| driver | default method | params |
|---|---|---|
| base | `trend` | — |
| penetration | `mean_revert` | target=0.8, speed=0.4 |
| share | `hold` | — |
| price | `trend` | — |

**checks**: `utilization_cap`

**benchmarks** (Damodaran US clusters, 2026-01, grade B):

| metric | P25 | P50 | P75 | cluster |
|---|---|---|---|---|
| revenue_cagr_5y | 8.8% | 11.0% | 13.6% | Machinery, Electrical Equipment, Engineering/Construction, Building Materials |
| revenue_exp_growth_2y | 8.6% | 11.4% | 28.4% | Machinery, Electrical Equipment, Engineering/Construction, Building Materials |

## financial_interest

**Financials (interest income)** · 金融（利息收入） · **fit: weak** — interest-earning assets × yield: the rate cycle is not in the historical window — point forecasts structurally unreliable

| driver | default method | params |
|---|---|---|
| base | `growth` | rate=0.08 |
| penetration | `hold` | — |
| share | `hold` | — |
| price | `mean_revert` | target=0.04, speed=0.5 |

**checks**: `balance_growth_hot`

**benchmarks** (Damodaran US clusters, 2026-01, grade B):

| metric | P25 | P50 | P75 | cluster |
|---|---|---|---|---|
| revenue_cagr_5y | 8.3% | 8.6% | 8.8% | Bank (Money Center), Banks (Regional) |
| revenue_exp_growth_2y | 9.8% | 11.0% | 12.2% | Bank (Money Center), Banks (Regional) |

> **When fit is weak**: anchor the yield to the forward policy-rate curve and run rate scenarios; treat the balance-sheet growth as a credit-cycle variable, not a trend

## commodity_cyclical

**Commodities / cyclical** · 大宗商品 / 周期 · **fit: weak** — price is cyclical around marginal cost — trend extrapolation peaks the forecast at exactly the wrong moment of the cycle

| driver | default method | params |
|---|---|---|
| base | `hold` | — |
| penetration | `hold` | — |
| share | `hold` | — |
| price | `mean_revert` | target=None, speed=0.3 |

**checks**: `cycle_top`

**benchmarks** (Damodaran US clusters, 2026-01, grade B):

| metric | P25 | P50 | P75 | cluster |
|---|---|---|---|---|
| revenue_cagr_5y | 9.3% | 14.5% | 18.8% | Metals & Mining, Coal & Related Energy, Oil/Gas (Integrated), Oil/Gas (Production and Exploration), Steel, Precious Metals |
| revenue_exp_growth_2y | 6.8% | 23.4% | 46.8% | Metals & Mining, Coal & Related Energy, Oil/Gas (Integrated), Oil/Gas (Production and Exploration), Steel, Precious Metals |

> **When fit is weak**: mean-revert price to marginal cost and run demand/capacity-shock scenarios; watch leading indicators (inventories, spreads) instead of fitting the trend

## regime_shift_tech

**Regime-shift tech (AI inflection)** · 范式跳变科技（AI 拐点） · **fit: weak** — NVDA Data Center: same formula as Gaming, 60% hold-out sMAPE (actual $115B vs trend $18B) — the breakout is not in the training data, and no trend fit can recover it

| driver | default method | params |
|---|---|---|
| base | `trend` | — |
| penetration | `trend` | — |
| share | `trend` | — |
| price | `trend` | — |

**checks**: `regime_always`

*No industry benchmarks by design — the profile's heuristic checks are the only layer.*

> **When fit is weak**: the point forecast below is a *baseline, not a forecast*: report Monte Carlo scenarios (simulate_segment) with wide honest ranges plus explicit trigger conditions; update fast as the regime reveals itself

