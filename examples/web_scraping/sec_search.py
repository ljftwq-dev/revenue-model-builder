"""playwright 最小验证: SEC EDGAR 搜公司的 10-K，跑通「搜 → 找 → 爬」。

复刻当时美股财报任务的「找财报」环节，把 OCR/PDF 换成 playwright 抓网页。
换公司只需改 TICKER（先拿 NVDA 验证脚手架）。

验证点:
  1. chromium 能启动
  2. 能导航到 SEC EDGAR（设了合规 User-Agent）
  3. 能抓到 filing 列表（JS 渲染后）
  4. 能打开最新一份 filing
  5. 落盘 json + 截图
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

TICKER = "NVDA"
# SEC 政策要求 UA 含真实联系方式（非占位邮箱）；用项目 owner 的 GitHub noreply
UA = "revenue-model-builder-ljf ljftwq-dev@users.noreply.github.com"
OUT_DIR = Path(__file__).parent / "out"
OUT_DIR.mkdir(exist_ok=True)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=UA,
            locale="en-US",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        page = ctx.new_page()

        # 第1步: 搜公司 10-K（EDGAR browse-edgar 页）
        url = (
            "https://www.sec.gov/cgi-bin/browse-edgar?"
            f"action=getcompany&CIK={TICKER}&type=10-K&dateb=&owner=include&count=10"
        )
        print(f"[1/3] 搜索 {TICKER} 的 10-K:\n      {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        print(f"      页面标题: {page.title()}")

        # 第2步: 抓 filing 链接（Archives.edgar 开头的是文档入口）
        rows = page.eval_on_selector_all(
            'a[href*="Archives.edgar"]',
            "els => els.map(e => ({text: (e.innerText||'').trim(), href: e.href}))",
        )
        seen, filings = set(), []
        for r in rows:
            if not r["text"] or r["href"] in seen:
                continue
            seen.add(r["href"])
            filings.append(r)
        print(f"[2/3] 找到 {len(filings)} 份 filing:")
        for i, f in enumerate(filings[:8], 1):
            print(f"      {i}. {f['text'][:50]:<50} | {f['href'][:68]}")

        result = {"ticker": TICKER, "count": len(filings), "filings": filings[:10]}

        # 第3步: 打开最新一份，看能不能进（验证导航到二级页）
        if filings:
            latest = filings[0]["href"]
            print(f"[3/3] 打开最新 filing:\n      {latest[:90]}")
            page.goto(latest, wait_until="domcontentloaded", timeout=30000)
            result["latest_title"] = page.title()
            print(f"      filing 页标题: {result['latest_title']}")

        # 落盘 + 截图
        (OUT_DIR / f"{TICKER}_10k_list.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        page.screenshot(path=str(OUT_DIR / f"{TICKER}_edgar.png"), full_page=False)
        print(f"\n结果已存: {OUT_DIR / f'{TICKER}_10k_list.json'}")
        print(f"截图已存: {OUT_DIR / f'{TICKER}_edgar.png'}")
        browser.close()
        print("SMOKE TEST PASSED")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
