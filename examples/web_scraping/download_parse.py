"""完整链路验证: playwright 找链接 -> 下载 PDF -> PyMuPDF 提文字 -> 看结构。

目标: NVDA Quarterly Revenue Trend (按市场维度的季度收入趋势), 最新 Q1 FY27。
q4cdn 是 CDN, 无反爬, urllib 直下。PDF 优先 PyMuPDF 直抠文字层(90% 财务 PDF 有字)。
"""
import sys
import urllib.request
from pathlib import Path

OUT_DIR = Path(__file__).parent / "out"
PDF_DIR = OUT_DIR / "pdfs"
PDF_DIR.mkdir(parents=True, exist_ok=True)

# 最新季度 Q1 FY27 (Rev by Mkt Qtrly Trend)
URL = ("https://s201.q4cdn.com/141608511/files/doc_financials/2027/Q127/"
       "Rev_by_Mkt_Qtrly_Trend_Q127-NEW-v3.pdf")
PDF_PATH = PDF_DIR / "NVDA_Rev_by_Mkt_Q127.pdf"
TXT_PATH = OUT_DIR / "NVDA_Rev_by_Mkt_Q127.txt"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")


def download():
    print(f"[1] 下载: {URL}")
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    PDF_PATH.write_bytes(data)
    print(f"    已存: {PDF_PATH} ({PDF_PATH.stat().st_size / 1024:.1f} KB)")


def parse():
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("    PyMuPDF 未装, 请: pip install PyMuPDF", file=sys.stderr)
        sys.exit(2)
    print("[2] PyMuPDF 探文字层...")
    doc = fitz.open(PDF_PATH)
    parts = []
    for i, page in enumerate(doc):
        parts.append(f"\n===== Page {i+1} =====\n{page.get_text()}")
    text = "".join(parts)
    TXT_PATH.write_text(text, encoding="utf-8")
    nchar = len(text.strip())
    print(f"    {len(doc)} 页, {nchar} 字符 -> {TXT_PATH}")
    print(f"    文字层判定: {'有字 (PyMuPDF 直抠成功)' if nchar > 50 else '空 (扫描件, 需 Unlimited-OCR)'}")
    doc.close()
    # 打印前若干行, 看数据结构
    print("\n[3] 前 60 行预览:")
    for line in text.splitlines()[:60]:
        if line.strip():
            print(f"    {line[:90]}")


if __name__ == "__main__":
    try:
        download()
        parse()
        print("\nDONE")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
