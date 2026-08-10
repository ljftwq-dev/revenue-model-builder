"""playwright 验证2: stockanalysis.com 抓公司财务主页（含 Revenue by Segment）。

主页 /stocks/{TICKER}/financials/ 含多张表：Revenue & Profits、Revenue by Segment、
Cash & Debt、Cash Flow、Margins 等。segment 数据正好补 rmb sec_adapter 的缺口
（sec_adapter 只抓 total_revenue，segment 是模板占位）。
换公司只改 TICKER。

注意: print 不用 unicode 特殊符号（PowerShell gbk 控制台编码不认）。
"""
import csv
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

TICKER = "NVDA"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")
URL = f"https://stockanalysis.com/stocks/{TICKER}/financials/"
OUT_DIR = Path(__file__).parent / "out"
OUT_DIR.mkdir(exist_ok=True)

# segment 表的行关键词（识别用，不依赖 caption）
SEG_KEYS = ("compute & networking", "graphics", "gaming", "data center",
            "professional", "automotive", "oem", "product", "service")


def is_segment_table(rows):
    if not rows:
        return False
    joined = " ".join(c.lower() for r in rows[:8] for c in r)
    return any(k in joined for k in SEG_KEYS) and "revenue" not in joined.split("\n")[0][:20].lower()


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=UA, locale="en-US",
            viewport={"width": 1366, "height": 900},
        )
        page = ctx.new_page()

        print(f"[1] navigate: {URL}")
        page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        print(f"    title: {page.title()}")

        print("[2] wait for tables...")
        try:
            page.wait_for_selector("table tbody tr", timeout=20000)
        except Exception:
            print("    warn: no tbody tr in 20s (paywall/anti-bot?)")
        time.sleep(2)

        # 抓所有表 + caption（table 所在 section 的 h2/h3）
        tables = page.eval_on_selector_all(
            "table",
            """ts => ts.map(t => {
                let cap = '';
                let sec = t.closest('section') || t.parentElement;
                if (sec) {
                    let h = sec.querySelector('h2,h3');
                    if (h) cap = h.innerText.trim();
                }
                return {
                    caption: cap,
                    headers: Array.from(t.querySelectorAll('thead th')).map(e => (e.innerText||'').trim()),
                    rows: Array.from(t.querySelectorAll('tbody tr')).map(tr => Array.from(tr.querySelectorAll('td')).map(td => (td.innerText||'').trim()))
                };
            })"""
        )
        print(f"[3] found {len(tables)} tables:")
        seg_idx = -1
        for i, t in enumerate(tables):
            ncol, nrow = len(t["headers"]), len(t["rows"])
            print(f"    table {i}: {ncol}col x {nrow}row  caption={t['caption'][:42]!r}")
            if seg_idx < 0 and is_segment_table(t["rows"]):
                seg_idx = i

        if seg_idx >= 0:
            t = tables[seg_idx]
            print(f"\n[4] === Revenue by Segment (table {seg_idx}) ===")
            print(f"    headers: {t['headers']}")
            for r in t["rows"]:
                print(f"      {r}")
        else:
            print("\n[4] segment table NOT auto-identified (inspect tables above)")

        # 落盘
        result = {"ticker": TICKER, "url": URL, "title": page.title(), "tables": tables}
        (OUT_DIR / f"{TICKER}_segment.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        exp = tables[seg_idx] if seg_idx >= 0 else (tables[0] if tables else None)
        fn = "segment" if seg_idx >= 0 else "table0"
        if exp:
            with open(OUT_DIR / f"{TICKER}_{fn}.csv", "w", newline="",
                      encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(exp["headers"])
                w.writerows(exp["rows"])
        page.screenshot(path=str(OUT_DIR / f"{TICKER}_segment.png"), full_page=False)

        print(f"\n[OK] json: {OUT_DIR / f'{TICKER}_segment.json'}")
        print(f"[OK] csv:  {OUT_DIR / f'{TICKER}_{fn}.csv'}")
        print(f"[OK] png:  {OUT_DIR / f'{TICKER}_segment.png'}")
        browser.close()
        print("DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
