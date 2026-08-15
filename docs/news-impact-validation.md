# News-impact validation — what 8-K events do and do not predict

*A case study in honest event-study methodology. Ships with the
`revenue_model.news_impact` module and the `revenue_model.form8k_adapter`
data layer. Not investment advice.*

## 1. The question

Direction-3 of the roadmap asked: **can press-release / filing events improve
revenue forecasts?** The seductive version of this idea is a screen that
watches 8-K filings and nudges next-quarter revenue forecasts when a
"material agreement" or "M&A completion" lands. Before building that screen,
we ran the honest version of the test.

## 2. The lesson: a single-company p-value is a mirage

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

## 3. What shipped anyway

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

## 4. Methodological checklist (encoded in `news_impact`)

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

## 5. Where news *might* still matter

The null result is scoped: **large caps, monthly returns, headline-level
categories**. It does not close the direction — it redirects it:

- **Small caps** where 8-Ks are less pre-digested by analysts;
- **Finer horizons** (daily event windows) where monthly data cannot see;
- **Text, not items** — an 8-K's *content* (a real contract vs. a routine
  extension) carries more than its item code;
- **Driver-level mapping** — the original vision (news → specific driver
  revision → forecast update) remains the right product shape; it needs
  event→driver grounding, not event→revenue regressions.

The honest conclusion: the *data layer* is now good (universal, official,
cached); the *signal*, for liquid large caps at monthly granularity, is not
there. Build the driver-mapping product when there is a signal worth
mapping.
