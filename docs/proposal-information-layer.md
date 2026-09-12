# Proposal: information layer (v0.21) — "the engine spends its half-day reading"

Born from a live PLTR run: the pipeline produced a mechanism-correct
baseline in minutes, while the analyst's manual forecast (the ArcSoft
benchmark) takes half a day — because the half-day is spent *reading*
(10-K/10-Q/press/calls/upstream-downstream), not computing. The input
volume differs by 2–3 orders of magnitude. v0.21 closes that gap by
turning every step of the analyst's reading process into a pipeline
stage — with the human where automation genuinely breaks.

## Design principles (from the 2026-09-12 PLTR retrospective)

1. **Wiring first.** The modules exist (news_impact, macro_revision,
   extractor, fetch_fiscal_quarters) — the v0.20 spine simply never
   called them. Acceptance for every stage below is a *wiring test*: the
   pipeline log must show the stage ran, not merely that the module
   exists.
2. **Gate H — the human-download gate.** Some sources (IR press pages,
   transcripts behind logins) cannot be fetched by playwright reliably.
   When automation genuinely breaks, the pipeline *stops and delegates*:
   it prints a concrete download checklist into a watch directory,
   the user drops the files in, `--resume` picks up. Same status as
   gates 1/2: a human gate is design, not failure.
3. **Filings are the core; news is concentric.** Evidence is organized
   in rings around the filings (ground truth): self news (guidance,
   orders, management) → upstream/downstream (supply constraints,
   customer ramps) → macro (rates, FX, cycle). Extractor prompts and
   the Evidence appendix are organized by ring, and every EvidenceCard
   carries the original quote + source.
4. **Evidence changes the analyst's parameters, not the numbers.**
   EvidenceCards hang on drivers with citation; the human adjusts the
   extrapolation and the adjustment is recorded in the report.

## Stage map (analyst action → pipeline stage)

| analyst action | stage | parts | status |
|---|---|---|---|
| read quarterlies for momentum | **quarterly layer**: 10-Q totals via `fetch_fiscal_quarters`, momentum detector (recent-4Q vs prior-4Q CAGR, turning-point alarm) | wire + new detector | v0.21a |
| read press / calls / MD&A | **document layer**: SEC 8-K EX-99 (free, structured) auto-fetch → Gate H for the rest → Unlimited-OCR (local) → extractor signal mode → EvidenceCards | wire q4cdn/8-K, new Gate H, extractor signal prompts | v0.21b |
| scan self / upstream / macro news | **shock layer**: `news_impact` + `macro_revision` wired into the pipeline post-forecast; evidence organized by ring | wire (the omission that started this) | v0.21c |
| report | **Evidence appendix**: per driver — numeric extrapolation + evidence cards + the analyst's recorded adjustments | report builder extension | v0.21c |

## Phasing

- **v0.21a — quarterly layer** (cheapest, biggest single win): 4 annual
  points → 16+ quarterly points; momentum turning-point alarm feeds the
  profile checks.
- **v0.21b — document layer + Gate H**: 8-K EX-99 press auto-fetch;
  watch-directory checklist + `--resume`; Unlimited-OCR ingestion;
  extractor signal mode → EvidenceCards with quotes.
- **v0.21c — shock layer + Evidence appendix**: news/macro wired in;
  concentric-ring organization; report appendix.

## Non-goals

- No black-box number editing from evidence (cards inform, humans adjust).
- No transcript scraping from paywalled sources (Gate H: the user
  supplies what they have rights to).
- No new forecasting math (again — orchestration and ingestion only).

## Acceptance

1. Wiring tests: every stage above leaves a log/trace asserted in tests.
2. PLTR re-run (pre-registered comparison): information-layer pipeline
   vs today's pure-extrapolation baseline — forecast error and evidence
   coverage both reported. This quantifies what the reading is worth.
3. Gate H drill: an IR page that playwright cannot download must produce
   the checklist + resume flow, tested with fixtures.
