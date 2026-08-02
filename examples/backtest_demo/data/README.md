# Backtest data cache

Annual total-revenue series for the ten companies in the cross-company
backtest, cached as CSV (`{symbol}.csv`, columns `year, revenue_million`).

- **Source**: akshare 同花顺 annual abstract
  (`stock_financial_abstract_ths`, indicator=`按年度`), drawn from audited
  annual filings.
- **Grade**: B (public, audited). Tag accordingly when fed into a model.
- **Units**: million yuan (matches the engine convention).
- **Why cached**: reproducibility — clone and run `backtest_ten_companies.py`
  offline without akshare or network. Refresh a single series with
  `load_annual_revenue(..., refresh=True)`.

`backtest_summary.json` is the aggregated result written by
`backtest_ten_companies.py` and read by `plot_backtest.py` (so plotting needs
no refit).

Public **total** revenue only — no proprietary or segment-level data. See the
root [DISCLAIMER.md](../../DISCLAIMER.md).
