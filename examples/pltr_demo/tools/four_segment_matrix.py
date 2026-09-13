"""Build the PLTR four-segment quarterly matrix (trace method, v0.21b).

Segments (growth-logic heterogeneous — see docs/proposal-information-
layer.md): US Comm / Intl Comm / US Gov / Intl Gov.

Data recipe per quarter:
  - deck (Business Update) discloses US commercial & US government revenue
  - 10-Q segment note gives Gov / Commercial totals
  - Intl branches are BACKCAST (totals minus US), double closed-loop
    checked: A) US_Comm + US_Gov == geographic US  B) sum4 == total revenue
  - 2025 filings list the UK separately once it passed 10% of revenue
    (a trace of its own: it drops out of the table in 2026 — denominator
    effect as US explodes; recorded, watch the politics)

Usage:
    python four_segment_matrix.py [queue_dir]
Reads the queue produced by fetch_docs.py; writes four_segment_matrix.txt.
"""
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF; extra: pip install -e ".[pdf]"

QTRS = [
    ("Q1_25", "PLTR_Q1_2025_10Q.pdf"),
    ("Q2_25", "PLTR_Q2_2025_10Q.pdf"),
    ("Q3_25", "PLTR_Q3_2025_10Q.pdf"),
    ("Q1_26", "PLTR_Q1_2026_10Q.pdf"),
    ("Q2_26", "PLTR_Q2_2026_10Q.pdf"),
]
# US splits from the decks (verified against the geographic table)
DECK_US = {
    "Q1_25": (255, 373), "Q2_25": (306, 426), "Q3_25": (397, 486),
    "Q4_25": (507, 570), "Q1_26": (595, 687), "Q2_26": (764, 809),
}
NUM = r"\$?\s*([\d][\d,]*)\xa0?"


def nums(text: str, anchor: str, k: int, span: int = 300):
    i = text.find(anchor)
    if i < 0:
        return None
    seg = text[i + len(anchor): i + len(anchor) + span]
    out = []
    for m in re.finditer(NUM, seg):
        try:
            v = float(m.group(1).replace(",", "")) / 1e3
        except ValueError:
            continue
        if v >= 50.0:                       # drop footnotes / percentages
            out.append(v)
        if len(out) == k:
            break
    return out if len(out) == k else None


def build(queue: Path) -> dict:
    rows = {}
    for tag, fname in QTRS:
        doc = fitz.open(queue / fname)
        text = "\n".join(p.get_text() for p in doc)
        doc.close()
        gov = nums(text, "Government revenue", 2)
        comm = nums(text, "Commercial revenue", 2)
        total = nums(text, "Total revenue", 2)
        us = None
        for m in re.finditer(r"United States", text):
            tail = text[m.end(): m.end() + 400]
            if "Total revenue" in tail:
                pre = tail.split("Rest of world")[0]
                got = [float(x.group(1).replace(",", "").replace("\xa0", "")) / 1e3
                       for x in re.finditer(NUM, pre)][:1]
                if got:
                    us = got
                break
        if not all([gov, comm, total, us]):
            raise SystemExit(f"{tag}: extraction incomplete — check the filing")
        usc, usg = DECK_US[tag]
        icomm, igov = round(comm[0] - usc, 1), round(gov[0] - usg, 1)
        s4 = round(usc + icomm + usg + igov, 1)
        assert abs(usc + usg - us[0]) < 2.0, f"{tag}: loop A broken"
        assert abs(s4 - total[0]) < 2.0, f"{tag}: loop B broken"
        rows[tag] = dict(usc=usc, icomm=icomm, usg=usg, igov=igov, total=s4,
                         yoy_comm=round(comm[0] / comm[1] - 1, 4),
                         yoy_gov=round(gov[0] / gov[1] - 1, 4))
        print(f"{tag}: {usc:6.0f} {icomm:6.1f} {usg:6.0f} {igov:6.1f} "
              f"sum={s4:7.1f} loops OK")
    # Q4_25 = FY 10-K minus Q1-Q3
    k = fitz.open(queue / "PLTR_FY2025_10K.pdf")
    ktext = "\n".join(p.get_text() for p in k)
    k.close()
    kgov = nums(ktext, "Government revenue", 1)
    kcomm = nums(ktext, "Commercial revenue", 1)
    if not (kgov and kcomm):
        raise SystemExit("10-K extraction failed")
    usc, usg = DECK_US["Q4_25"]
    q3c = sum(rows[t]["usc"] + rows[t]["icomm"] for t in ("Q1_25", "Q2_25", "Q3_25"))
    q3g = sum(rows[t]["usg"] + rows[t]["igov"] for t in ("Q1_25", "Q2_25", "Q3_25"))
    q4c, q4g = round(kcomm[0] - q3c, 1), round(kgov[0] - q3g, 1)
    rows["Q4_25"] = dict(usc=usc, icomm=round(q4c - usc, 1), usg=usg,
                         igov=round(q4g - usg, 1), total=round(q4c + q4g, 1))
    print(f"Q4_25: backcast from FY 10-K minus Q1-Q3, total "
          f"{rows['Q4_25']['total']:.1f}")
    return rows


def main() -> int:
    queue = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "queue"
    rows = build(queue)
    out = queue / "four_segment_matrix.txt"
    out.write_text("\n".join(f"{t}: {v}" for t, v in rows.items()),
                   encoding="utf-8")
    print(f"\nY/Y by segment:")
    for cur, pri in (("Q1_26", "Q1_25"), ("Q2_26", "Q2_25")):
        parts = [f"{lbl} {rows[cur][f] / rows[pri][f] - 1:+.0%}"
                 for f, lbl in (("usc", "US_Comm"), ("icomm", "Int_Comm"),
                                ("usg", "US_Gov"), ("igov", "Int_Gov"))]
        print(f"  {cur} vs {pri}: " + "  ".join(parts))
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
