# PLTR demo data sources

All figures from Palantir's public SEC filings (education/research use only).

| item | years | source |
|---|---|---|
| Government revenue ($M): 920 / 1100 / 1222 / 1570 | FY2021–FY2024 | 10-K segment disclosure |
| Commercial revenue ($M): 621 / 806 / 1002 / 1299 | FY2021–FY2024 | 10-K segment disclosure |
| Total revenue ($M): 1542 / 1906 / 2225 / 2866 | FY2021–FY2024 | 10-K |
| Commercial customers: 207 / 225 / 280 / 382 | FY2021–FY2024 | 10-K / earnings letters (count at year end) |
| Commercial ARPU ($M/customer) | derived | Commercial revenue ÷ customer count (rounded) |

Notes:
- Government segment is modeled as a single trend base (its disclosed
  revenue IS the driver) — an explicit approximation: budget-cycle
  contracts proxied by the trend family.
- Commercial tree: customers (base) × ARPU (price); ARPU 2024 dipped as
  smaller-customer onboarding diluted the average — visible in the data
  and part of the gate-2 story.
- FY2025–26 are pure forecast years; no forward guidance is encoded.
