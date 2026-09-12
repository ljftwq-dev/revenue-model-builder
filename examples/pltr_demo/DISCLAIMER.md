# Disclaimer

This demo uses **publicly disclosed** data from NVIDIA Corporation (NVDA) —
segment revenue from NVIDIA's official quarterly disclosures and 10-K filings,
aggregated and redistributed by [Our World in Data](https://ourworldindata.org)
under the Creative Commons BY license, plus industry driver estimates from
third-party sources (IDC, JPR).

## What this is
A **methodology back-test**: the model is trained on FY2019-FY2023 segment
revenue and driver history, then *held-out* on FY2024-FY2025 to test whether a
driver tree extrapolates well. It demonstrates where the method works (Gaming)
and where it structurally fails (Data Center, AI regime shift).

## What this is NOT
- **Not investment advice.** No buy/sell recommendation, target price, or rating
  is expressed or implied.
- Driver `base` / `share` values are **industry estimates (B/C-grade)**; `price`
  is an **implied back-solve (C-grade)** to tie the tree to reported revenue.
  They exist to make the methodology demonstration work, not to assert NVIDIA's
  true market share or unit ASPs.
- Hold-out "predictions" are a **retrospective test**, not a forward forecast.

## Data use
- Segment revenue (Data Center, Total) is A-grade, traced to NVIDIA's official
  disclosures. Gaming is NVIDIA-reported (FY2023 cross-checked against the 2023
  Annual Review).
- All drivers cite their source and grade in `data/sources.md`.
- No proprietary or non-public information is used.

## Audience
Research and education — demonstrating driver-based revenue modeling and its
limits on real U.S. equity disclosure. The authors have no position in NVDA.
