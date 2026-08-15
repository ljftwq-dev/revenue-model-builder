# News-impact validation — what 8-K events do and do not predict

*Three rounds of honest event-study methodology on SEC 8-K filings: the
price dimension, the revenue dimension, and the customer→supplier chain.
Ships with the `revenue_model.news_impact` module and the
`revenue_model.form8k_adapter` data layer. Not investment advice.*

## 1. The question

Direction-3 of the roadmap asked: **can press-release / filing events improve
revenue forecasts?** The seductive version of this idea is a screen that
watches 8-K filings and nudges next-quarter revenue forecasts when a
"material agreement" or "M&A completion" lands. Before building that screen,
we ran the honest version of the test — three times, each round correcting
the last round's methodology.

## 2. Round 1: a single-company p-value is a mirage

The project's first pass (2026-08, SDGR case study) found exactly what a
researcher hopes for: **Partnership/M&A press releases → negative signal,
p = 0.033**. One number, one company, one story — biotech partnerships
dilute, the market knows something, headline categories carry information.

Rebuilding the analysis exposed the mirage piece by piece:

| Step | Finding |
|---|---|
| Rebuild the revenue series | Two adapter bugs (below) had corrupted the quarter data the original study ran on |
| Honest revenue dimension | Partnership/M&A events were followed by **+29.0%** YoY growth vs a +20.8% baseline — wrong direction, p = 0.11 (Welch) / 0.22 (MWU) |
| Price dimension (monthly, market-adjusted) | Event-month abnormal return **+8.1%**, p = 0.039/0.015 — significant! But *positive*, not negative as originally recorded |
| Pool across 6 issuers | The price effect **vanishes** (Agreement +1.6%, p = 0.76) — it was one company's idiosyncratic run |
| Check the "next-month drift" | Every category looked significant — because event-heavy months overlapped a bull market (a timing confound, not a signal) |

The p = 0.033 was never a lie — it was a **single-sample artifact**. SDGR
had 28 qualifying events; with ~20 categories × horizons to scan, a p < 0.05
shows up in noise almost surely. Pooling NVDA / AMD / SDGR / REGN / GILD /
GM (409 events, 2019-2026), adjusting returns for SPY, and correcting for
the family of tests: **no 8-K category carries robust monthly-horizon
information on these large caps.** Which is, on reflection, exactly what an
efficient market should do to the most public disclosure in existence.

## 3. Round 2: the revenue dimension — a selection effect, not a shock

Prices aside, the fundamental question is whether events move *revenue*. A
second pass pooled 18 issuers across 8 sectors (semis / software / biotech /
pharma / consumer / auto / industrial / energy; ~1,500 8-Ks, ~1,000 fiscal
quarters), excluded Earnings filings (mechanically contemporaneous with the
disclosure itself), and tested five outcomes including the **growth
acceleration** (Δ YoY, pre- vs post-event) — the right outcome for a
"shock", since growth *levels* are dominated by the company's regime.

The level results looked strong: post-event YoY ran 7-9pp below baseline,
direction-consistent across all eight sectors, with `fy_growth /
Other-RegFD` clearing Bonferroni (Welch p = 0.001). Three diagnostics then
exposed it as **selection, not causation**:

| Diagnostic | Result |
|---|---|
| Pre-event 4Q YoY | Already low (+12.7% vs +20% baseline, p = 0.013) — slow growers file more 8-Ks *before* anything happens |
| Paired delta (post − pre, within event) | ≈ 0 (+1.8%, p = 0.15) — the event does not bend the trajectory |
| Filing rate by growth tercile | Monotone: slow third 4.3 non-Earnings 8-Ks/yr, middle 3.4, fast 2.6 |

So the "signal" is a **reverse slow variable**: non-Earnings 8-K frequency
is a characteristic label of low-growth companies (reorganizations,
financing, management churn cluster in slow regimes). Useful as a screening
feature, meaningless as a shock. The one weak true effect — a +4.6% paired
acceleration after management changes (p = 0.033, "new-broom" CEO effect) —
does not survive correction but is the only direction with a story worth
following up (distressed-company subsamples).

## 4. Round 3: customer events → supplier revenue — the wave detector

The NVIDIA data-center story this project was born from is not "NVIDIA's
own 8-Ks predicted NVIDIA." It is *the customers'* capex wave (Microsoft,
Meta, Oracle announcing buildouts) arriving at the supplier 1-4 quarters
later. Round 3 tested exactly that chain — customer non-Earnings 8-K
density → supplier's lagged revenue — over eight pairs (MSFT/META/ORCL →
NVDA/AMD/AVGO, NVDA → AVGO):

| Customer high-activity quarter (≥2 filings) | Supplier YoY at lag | vs baseline |
|---|---|---|
| lag +1 .. +4 quarters | **+59% .. +62%** (n = 13) | +30% (n = 348), MWU p ≤ 0.008 |
| placebo lag −1 / −2 | +39% / +29% — **not significant** | time direction holds |
| dose-response (density 0 / 1 / 2 / 3+) | +29% / +35% / +40% / **+80%** | monotone |

The time structure is real and matches the mechanism (customers announce →
orders → revenue recognition 1-4 quarters later). But honesty demands the
fine print: those 13 high-activity quarters cluster entirely in **two
waves** (the 2020-21 post-COVID cloud buildout and the 2023+ AI capex
surge), and the acceleration placebo *fails* (lag −1 also significant) —
the wave lifts both sides of the event, so this is a **regime-level event
study with n = 1 wave family**, not a repeatable statistical regularity.

The correct product reading: **news is a wave detector, not a trading
signal.** Monitoring *ecosystem* (customer / upstream) event density marks
a driver regime shift 1-4 quarters before it shows up in the supplier's
reported revenue — which is precisely the "news → driver revision →
forecast update" loop this project's memo demo implemented by hand, and
why event→driver mapping (not event→revenue regressions) is the right
interface.

## 5. What shipped anyway

A null result with clean methodology is still a result. The validation
exercise produced four library-grade assets:

- **`form8k_adapter`** — 8-K events from SEC's submissions API: universal
  coverage (any ticker), official item codes (1.01 agreement, 2.01 M&A
  completion, 5.02 management, 2.02 earnings, ...), no key, no scraping.
  Strictly better than guessing IR-site domains.
- **`news_impact`** — the honest event-study toolkit: Welch's t and
  Mann-Whitney U hand-rolled in pure stdlib (verified against scipy to 8
  decimals), pooled `event_study()` with per-category rows, automatic
  Bonferroni family correction, and `min_n` guards that report small
  categories **without** a test instead of mining them.
- **Two `sec_adapter` bug fixes** found by the rebuild: revenue-concept
  switching silently dropped years (SDGR lost 2019-2023), and a YTD/discrete
  period collision corrupted single-quarter differencing (negative quarters).
- **`fetch_fiscal_quarters`** — a fiscal-year-general single-quarter series
  (NVDA's late-January FY handled), concept-merged, incomplete trailing
  years excluded per the M7 honesty rule.

## 6. Methodological checklist (encoded in `news_impact`)

1. **Pool.** One issuer is one draw from a noisy distribution. If the effect
   needs SDGR specifically, it is not an effect.
2. **Adjust.** Event months overlap market regimes; subtract the benchmark
   before calling anything abnormal.
3. **Count the tests.** k categories × h horizons is a family; report the
   Bonferroni threshold alongside every nominal p-value (`event_study` does
   this by construction).
4. **Respect small n.** A category with 5 events gets a number and a note,
   not a p-value.
5. **Verify the data pipeline first.** Both "findings" above sat on top of
   broken quarter derivation. Plot the series before you test the series.
6. **Diagnose the pre-event window.** A post-event level below baseline
   means nothing until you show the pre-event level was *at* baseline —
   otherwise you have selection (slow growers file more 8-Ks), not a shock.
   The paired post−pre delta is the honest shock estimate.
7. **Run placebo lags.** A real lead-lag effect must vanish at negative
   lags. If lag −1 is as significant as lag +2, you are dating a wave, not
   transmitting a signal.
8. **Ask what n means.** Thirteen significant quarters inside two industry
   waves is one draw of "wave happens", not thirteen independent
   confirmations.

## 7. Where news actually matters

Three rounds, three answers:

- **Own-company 8-Ks → own revenue next quarter: null** (efficient
  disclosure, plus a selection artifact that fakes a level effect).
- **Own-company 8-K *frequency*: a reverse slow variable** — a cheap
  screening feature for low-growth regimes, not a forecast input.
- **Ecosystem (customer/upstream) event density → supplier revenue 1-4
  quarters later: real time structure** — the wave detector. Statistically
  an n=1 wave family, operationally the trigger for driver revision.

The original vision stands, with the interface corrected: news feeds the
forecast through **event → driver revision → re-run**, never through
event → revenue regressions. The data layer for that loop
(`form8k_adapter` + `fetch_fiscal_quarters`) ships in this library; the
driver-mapping layer is the remaining build.

Not investment advice.
