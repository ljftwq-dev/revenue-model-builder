# Luxun Precision (002475) — Real A-share Historical-Alignment Demo

The first **real-company** demo for `revenue-model-builder`: proves the engine
builds a driver-based revenue model from **public annual-report data** and
aligns it to reported historical totals — not just the fictional NovaTech.

## Why this matters
A real company that ties out is the credibility watershed for a modeling tool.
The fictional NovaTech shows the *mechanics*; Luxun shows it works on genuine,
noisy, restated disclosure.

## What the driver tree captures
- **A cross-border acquisition, in one number.** Automotive `share` jumps
  `4.5% → 12%` in 2025, capturing Luxun's Leoni acquisition — which nearly
  tripled segment revenue (`+185%`). The driver doesn't narrate the deal; it
  *is* the deal's footprint.
- **A caliber change, handled.** In 2025 Luxun merged "PC interconnect" into
  "consumer electronics" (5 → 4 segments, renamed lines). History is restated
  to the new 4-segment taxonomy so cross-period comparison stays valid.
- **ABC grading = auditable.** Every driver carries a credibility grade: **B**
  = industry data (IDC / EVTank / CAICT), **C** = estimate / implied. You can
  see exactly which number is hard and which is a judgment call.
- **Implied-driver alignment (Principle 1).** `base` / `penetration` / `share`
  are set from industry data; `price` is back-solved to tie to reported segment
  revenue. Penetration is **never** back-solved.

## Driver design (2024, consumer electronics)
```
revenue = global smartphones (1.22 B) × Apple share (18.9%)
        × Luxun's Apple-supply-chain share (31%) × per-device value (¥3,261)
```
Each factor is sourced & graded; only `price` is implied (C).

## Data sources — all public
- Annual reports 2023–2025 from [cninfo.com.cn](http://www.cninfo.com.cn) (the
  statutory disclosure platform).
- Industry bases: IDC (smartphones), CAICT/TrendForce (AI servers), EVTank (NEVs).

## Run
```bash
pip install -e ".[excel]"     # from repo root
python examples/luxun-real-demo/luxun_demo.py
```
Writes `立讯精密_收入模型.xlsx` (ABC color coding, IF-protected revenue
formulas, residual line, 2026–2028E forecast columns reserved).

## The full pipeline (this script is the modeling step)
This self-contained script does **steps 4–5** with drivers embedded, so it runs
offline with no API key. Steps 1–3 are how the data was obtained:

1. **Fetch** reports from cninfo (`szse_stock.json` → orgId → `hisAnnouncement/query`)
2. **Extract** the "main business analysis" section via PyMuPDF
3. **Skeleton** segments via `extract_segments` (LLM, OpenAI-compatible)
4. **Model** — `luxun_demo.py`: fill drivers + `implied_driver` alignment
5. **Render** Excel via `excel_builder`

## Compliance
Historical alignment only — **no forecasts, no buy/sell recommendations**. See
[DISCLAIMER.md](DISCLAIMER.md). Research / education tool, not investment advice.
