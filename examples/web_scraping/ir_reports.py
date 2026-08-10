"""playwright 验证3: 公司官网 IR 抓财报（NVDA）。

验证「公司官网 -> 找财报 PDF/链接」流程，复刻当时美股财报任务的 PDF 来源。
第一方信源（每家结构不同），这里拿 NVDA 验证脚手架对 IR 页有效。
抓两类: PDF 下载链接 + 财报相关链接（10-K/10-Q/annual/quarter/proxy）。
"""
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

COMPANY = "NVDA"
URL = "https://investor.nvidia.com/financial-info/financial-reports/default.aspx"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")
OUT_DIR = Path(__file__).parent / "out"
OUT_DIR.mkdir(exist_ok=True)

FIN_KEYWORDS = ("10-k", "10-q", "annual", "quarter", "financial",
                "report", "proxy", "earnings")


def dedup(xs):
    seen, out = set(), []
    for x in xs:
        if x["href"] in seen:
            continue
        seen.add(x["href"])
        out.append(x)
    return out


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
        time.sleep(2.5)  # .aspx 可能有部分动态加载

        # 抓所有 a[href]
        links = page.eval_on_selector_all(
            "a[href]",
            """els => els.map(e => ({text: (e.innerText||'').trim(), href: e.href}))
                     .filter(x => x.href && x.text)"""
        )
        print(f"[2] 页面共 {len(links)} 个有文字链接")

        pdf_links = [l for l in links if ".pdf" in l["href"].lower()]
        fin_links = [l for l in links
                     if any(k in (l["text"] + " " + l["href"]).lower() for k in FIN_KEYWORDS)]
        pdf_links, fin_links = dedup(pdf_links), dedup(fin_links)

        print(f"\n[3] PDF 下载链接 ({len(pdf_links)}):")
        for l in pdf_links[:20]:
            print(f"    {l['text'][:48]:<48} | {l['href'][:70]}")

        print(f"\n[4] 财报相关链接 ({len(fin_links)}):")
        for l in fin_links[:20]:
            print(f"    {l['text'][:48]:<48} | {l['href'][:70]}")

        result = {
            "company": COMPANY, "url": URL, "title": page.title(),
            "total_links": len(links), "pdf_links": pdf_links, "finance_links": fin_links,
        }
        (OUT_DIR / f"{COMPANY}_ir_links.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        page.screenshot(path=str(OUT_DIR / f"{COMPANY}_ir.png"), full_page=False)

        print(f"\n[OK] json: {OUT_DIR / f'{COMPANY}_ir_links.json'}")
        print(f"[OK] png:  {OUT_DIR / f'{COMPANY}_ir.png'}")
        browser.close()
        print("DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
