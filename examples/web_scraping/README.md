# Web Scraping Examples — Pulling Financial Data from the Web

These scripts accompany `revenue_model.sa_adapter` (v0.10.0). They show how to
collect reported financial data that the structured-API adapters
(`sec_adapter` / `tushare_adapter` / `akshare_adapter`) cannot reach —
specifically **segment revenue** and **company IR filings**.

## Why scrape (when there are APIs)?

The three total-revenue adapters pull from structured official sources (SEC
XBRL, tushare, AKShare). But **segment revenue** is hard to get from those APIs:
SEC's XBRL segment tags vary per issuer, so `sec_adapter` fills only
`total_revenue` and leaves segments as placeholder templates. Scraping fills
that gap.

## Scripts

| Script | What it does | Lesson |
|---|---|---|
| `sec_search.py` | Tries SEC EDGAR via playwright | **Blocked** — SEC flags the IP as an automated-tool network. SEC has a public API (`data.sec.gov`); use that, not scraping. Kept as a cautionary example. |
| `sa_segment.py` | Pulls the "Revenue by Segment" table from stockanalysis.com | JS-rendered → playwright required. This is the basis of `sa_adapter`. Change `TICKER` for any company. |
| `ir_reports.py` | Lists PDF download links from a company's IR page (NVDA) | PDFs hosted on `s201.q4cdn.com/{company_id}/...` (Q4 Inc platform) — a reusable URL pattern across many companies. Also surfaces **earnings-call transcripts** (a data source for event-driven forecasting). |
| `download_parse.py` | Downloads an IR PDF and extracts text with PyMuPDF | The PDF has a text layer 90% of the time → PyMuPDF direct extraction; only fall back to OCR for scanned/image PDFs. |

## Key findings (encoded for reuse)

1. **SEC → API, not scraping.** `data.sec.gov` is public and stable; `www.sec.gov` HTML pages block automated browsers (IP-level flag, not just UA).
2. **stockanalysis.com segment table** lives at `/stocks/{TICKER}/financials/` (the main financials page), **not** `/segment-revenue/` (that 404s).
3. **q4cdn URL pattern**: `s201.q4cdn.com/{company_id}/files/doc_financials/{year}/{quarter}/...` — many listed companies share this IR-hosting platform, so the pattern generalizes.
4. **Earnings-call transcripts** (found via IR scraping) are a free, compliant data source for event-driven / news-shock modeling — the missing input flagged in the rmb roadmap's "news shock" direction.
5. **PDF parsing order**: try PyMuPDF `get_text()` first (text-layer PDFs — 90% of financial PDFs); only use OCR for scanned/image PDFs.

## Setup

```bash
pip install -e ".[scrape]"   # playwright
pip install PyMuPDF           # for download_parse.py
playwright install chromium   # browser binary
```

## Usage

```bash
# Any company's segment revenue (change TICKER in the script)
python examples/web_scraping/sa_segment.py

# Company IR filing links (change URL in the script)
python examples/web_scraping/ir_reports.py

# Download + parse a PDF (change URL in the script)
python examples/web_scraping/download_parse.py
```

Outputs land in `out/` next to each script.

---

This is the **data-collection** layer; `sa_adapter` is the **data → model**
layer. Together they turn a ticker into a `RevenueModel` carrying real reported
segment anchors.
