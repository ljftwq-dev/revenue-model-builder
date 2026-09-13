"""Fetch PLTR IR documents into a queue directory (v0.21b live-drill assets).

Downloads Business Update decks and filings from investors.palantir.com.
Link discovery is the hard part (naming drifts across quarters —
"Investor Presentation" vs "Business Update", hyphens appear and
disappear); this table records the *verified* names from the 2026-09-12
drill. For new quarters, open https://investors.palantir.com/financials
with playwright, switch the Year combobox, read the real links — then
add them here.

Usage:
    python fetch_docs.py [queue_dir]        # default: ./queue next to this file
"""
import sys
import urllib.request
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
BASE = "https://investors.palantir.com/files/"
# SEC-CDN mirrors for the 2025 10-Qs (links from the IR Financials page)
CDN = "https://d18rn0p25nwr6d.cloudfront.net/CIK-0001321655/"

FILES = {
    # decks — verified names from the live drill
    "PLTR_Q1_2025_Business_Update.pdf": BASE + "Palantir%20-%20Q1%202025%20Investor%20Presentation.pdf",
    "PLTR_Q2_2025_Business_Update.pdf": BASE + "Palantir%20Q2%202025%20Business%20Update.pdf",
    "PLTR_Q3_2025_Business_Update.pdf": BASE + "Palantir%20-%20Q3%202025%20Investor%20Presentation.pdf",
    "PLTR_Q4_2025_Business_Update.pdf": BASE + "Palantir%20-%20Q4%202025%20Investor%20Presentation.pdf",
    "PLTR_Q1_2026_Business_Update.pdf": BASE + "Palantir%20-%20Q1%202026%20Business%20Update.pdf",
    "PLTR_Q2_2026_Business_Update.pdf": BASE + "Palantir%20-%20Q2%202026%20Business%20Update.pdf",
    # filings
    "PLTR_FY2025_10K.pdf": BASE + "2025%20FY%20PLTR%2010-K.pdf",
    "PLTR_Q1_2026_10Q.pdf": BASE + "2026%20Q1%20PLTR%2010-Q.pdf",
    "PLTR_Q2_2026_10Q.pdf": BASE + "2026%20Q2%20PLTR%2010-Q.pdf",
    "PLTR_Q1_2025_10Q.pdf": CDN + "82969e9e-897c-4ac4-99ee-38a58af98d2c.pdf",
    "PLTR_Q2_2025_10Q.pdf": CDN + "e672795c-bf28-4956-9251-6da233852c18.pdf",
    "PLTR_Q3_2025_10Q.pdf": CDN + "3a83dd8a-00a1-49df-a72d-2f681f158c09.pdf",
}


def main() -> int:
    queue = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "queue"
    queue.mkdir(parents=True, exist_ok=True)
    ok = fail = skip = 0
    for name, url in FILES.items():
        target = queue / name
        if target.exists():
            skip += 1
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                data = r.read()
            if data[:4] == b"%PDF":
                target.write_bytes(data)
                print(f"OK   {name}  {len(data) / 1e6:.1f} MB")
                ok += 1
            else:
                print(f"FAIL {name}: not a PDF")
                fail += 1
        except Exception as exc:  # noqa: BLE001 — report, don't crash the batch
            print(f"FAIL {name}: {type(exc).__name__} {exc}")
            print("     -> Gate H: open the IR Financials page by hand and drop "
                  "the file in the queue directory")
            fail += 1
    print(f"\n{ok} fetched, {skip} skipped (present), {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
