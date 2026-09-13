"""Extract key-metric series across PLTR decks (definition-drift check).

Principle 0 in action: single-deck numbers lie by omission; the six-quarter
series shows NRR's six straight rises and TCV's volatility (a -12% QoQ
dip in Q1'26 before the +81% spike in Q2'26).

Usage:
    python deck_series.py [queue_dir]
"""
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF; extra: pip install -e ".[pdf]"

DECKS = [
    ("Q1_25", "PLTR_Q1_2025_Business_Update.pdf"),
    ("Q2_25", "PLTR_Q2_2025_Business_Update.pdf"),
    ("Q3_25", "PLTR_Q3_2025_Business_Update.pdf"),
    ("Q4_25", "PLTR_Q4_2025_Business_Update.pdf"),
    ("Q1_26", "PLTR_Q1_2026_Business_Update.pdf"),
    ("Q2_26", "PLTR_Q2_2026_Business_Update.pdf"),
]
PATTERNS = {
    "NRR": r"[Nn]et dollar retention was (\d{1,3})%",
    "TCV_total": r"[Tt]otal contract value[^.]*?([\d.]+) billion",
    "US_comm_rev": r"U\.?S\.? commercial revenue (?:grew|of|increased)[^.]*?([\d.]+) (?:billion|million)",
    "customer_cnt": r"(\d{3})\s*\n?TTM",
}


def main() -> int:
    queue = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "queue"
    for tag, name in DECKS:
        p = queue / name
        if not p.exists():
            print(f"{tag}: MISSING {name}")
            continue
        doc = fitz.open(p)
        text = "\n".join(pg.get_text() for pg in doc)
        doc.close()
        out = {}
        for k, pat in PATTERNS.items():
            m = re.search(pat, text, re.S | re.I)
            if m:
                out[k] = m.group(1)
        print(f"{tag}: {out}")
    print("\nnote: deck revenue figures are chart-label text and unreliable "
          "under regex — numbers come from SEC XBRL; decks are for ratios.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
