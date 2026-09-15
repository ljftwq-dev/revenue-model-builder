"""Four-segment quarterly revenue matrix — the trace method, codified
(v0.21b acceptance #2).

Generalizes the PLTR live drill into a reusable module:

- per-quarter segment revenue (Government / Commercial) and totals come
  from 10-Q filings; US splits come from the decks; international branches
  are BACKCAST (totals minus US);
- every quarter is double closed-loop checked — A: US_Comm + US_Gov ==
  geographic US revenue; B: the four segments == total revenue;
- a fiscal-year 10-K can backcast the missing Q4 (FY minus the sum of
  filed quarters).

Pure-text parsing lives in :func:`build_from_texts` (unit-testable, no
PDF dependency); :func:`build_matrix` wraps it with PyMuPDF page text
(needs the ``[pdf]`` extra, imported lazily).
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping

NUM = r"\$?\s*([\d][\d,]*)\xa0?"

DEFAULT_ANCHORS = {
    "gov": "Government revenue",
    "comm": "Commercial revenue",
    "total": "Total revenue",
    "geo_us": "United States",
}


class MatrixLoopError(ValueError):
    """A closed loop failed — the filing numbers do not reconcile."""


@dataclass(frozen=True)
class QuarterSpec:
    """One filed quarter: its 10-Q filename and the deck's US split ($M)."""
    tag: str
    filing: str
    us_split: tuple            # (us_commercial, us_government) from the deck


@dataclass(frozen=True)
class BackcastSpec:
    """The missing quarter derived as FY 10-K minus filed quarters."""
    tag: str
    us_split: tuple            # that quarter's deck split ($M)
    covered: tuple             # filed quarter tags subtracted from FY


@dataclass(frozen=True)
class MatrixSpec:
    """Everything needed to build the matrix for one company."""
    quarters: tuple            # QuarterSpec, chronological
    fy_10k: str = ""           # 10-K filename (drives the backcast)
    backcast: BackcastSpec = None
    anchors: dict = field(default_factory=lambda: dict(DEFAULT_ANCHORS))


def _nums(text: str, anchor: str, k: int, span: int = 300):
    """First k numbers >= $50M after the anchor (footnotes/percentages
    dropped). Returns None when fewer than k are found."""
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
        if v >= 50.0:
            out.append(v)
        if len(out) == k:
            break
    return out if len(out) == k else None


def _geo_us(text: str, anchor: str):
    """Geographic 'United States' revenue next to a 'Total revenue'
    column (i.e. the geographic table, not a random mention). $M."""
    for m in re.finditer(re.escape(anchor), text):
        tail = text[m.end(): m.end() + 400]
        if "Total revenue" in tail:
            pre = tail.split("Rest of world")[0]
            got = [float(x.group(1).replace(",", "").replace("\xa0", "")) / 1e3
                   for x in re.finditer(NUM, pre)][:1]
            if got:
                return got[0]
    return None


def _quarter_row(text: str, tag: str, us_split: tuple, anchors: dict) -> dict:
    """Parse one 10-Q text into a four-segment row with both loops."""
    gov = _nums(text, anchors["gov"], 2)
    comm = _nums(text, anchors["comm"], 2)
    total = _nums(text, anchors["total"], 2)
    us = _geo_us(text, anchors["geo_us"])
    if not all([gov, comm, total, us]):
        raise MatrixLoopError(
            f"{tag}: extraction incomplete — check the filing")
    usc, usg = us_split
    icomm, igov = round(comm[0] - usc, 1), round(gov[0] - usg, 1)
    s4 = round(usc + icomm + usg + igov, 1)
    if abs(usc + usg - us) >= 2.0:
        raise MatrixLoopError(
            f"{tag}: loop A broken (US branches {usc + usg:.1f} vs "
            f"geographic US {us:.1f})")
    if abs(s4 - total[0]) >= 2.0:
        raise MatrixLoopError(
            f"{tag}: loop B broken (sum4 {s4:.1f} vs total {total[0]:.1f})")
    return dict(usc=usc, icomm=icomm, usg=usg, igov=igov, total=s4,
                yoy_comm=round(comm[0] / comm[1] - 1, 4),
                yoy_gov=round(gov[0] / gov[1] - 1, 4))


def build_from_texts(texts: Mapping[str, str], spec: MatrixSpec) -> Dict[str, dict]:
    """Build the matrix from filing texts keyed by *filename*. Pure —
    no I/O, no PDF. Rows come back in chronological order."""
    rows: Dict[str, dict] = {}
    for q in spec.quarters:
        rows[q.tag] = _quarter_row(texts[q.filing], q.tag, q.us_split,
                                   spec.anchors)
    if spec.backcast is not None:
        bc = spec.backcast
        ktext = texts[spec.fy_10k]
        kgov = _nums(ktext, spec.anchors["gov"], 1)
        kcomm = _nums(ktext, spec.anchors["comm"], 1)
        if not (kgov and kcomm):
            raise MatrixLoopError("10-K extraction failed")
        usc, usg = bc.us_split
        sum_c = sum(rows[t]["usc"] + rows[t]["icomm"] for t in bc.covered)
        sum_g = sum(rows[t]["usg"] + rows[t]["igov"] for t in bc.covered)
        q4c, q4g = round(kcomm[0] - sum_c, 1), round(kgov[0] - sum_g, 1)
        row = dict(usc=usc, icomm=round(q4c - usc, 1), usg=usg,
                   igov=round(q4g - usg, 1), total=round(q4c + q4g, 1))
        # chronological insertion: right after the last covered quarter
        rebuilt = {}
        for t, v in rows.items():
            rebuilt[t] = v
            if t == bc.covered[-1]:
                rebuilt[bc.tag] = row
        rows = rebuilt
    return rows


def pltr_spec() -> MatrixSpec:
    """The verified PLTR live-drill configuration (2026-09): five 10-Qs,
    Q4'25 backcast from the FY2025 10-K. US splits verified against the
    decks' geographic tables."""
    return MatrixSpec(
        quarters=(
            QuarterSpec("Q1_25", "PLTR_Q1_2025_10Q.pdf", (255, 373)),
            QuarterSpec("Q2_25", "PLTR_Q2_2025_10Q.pdf", (306, 426)),
            QuarterSpec("Q3_25", "PLTR_Q3_2025_10Q.pdf", (397, 486)),
            QuarterSpec("Q1_26", "PLTR_Q1_2026_10Q.pdf", (595, 687)),
            QuarterSpec("Q2_26", "PLTR_Q2_2026_10Q.pdf", (764, 809)),
        ),
        fy_10k="PLTR_FY2025_10K.pdf",
        backcast=BackcastSpec("Q4_25", (507, 570),
                              ("Q1_25", "Q2_25", "Q3_25")),
    )


def build_matrix(queue_dir: Path, spec: MatrixSpec) -> Dict[str, dict]:
    """Read the queue PDFs and build the matrix (needs the [pdf] extra)."""
    import fitz  # lazy: PyMuPDF

    queue_dir = Path(queue_dir)
    filenames = {q.filing for q in spec.quarters}
    if spec.backcast is not None:
        filenames.add(spec.fy_10k)
    texts: Dict[str, str] = {}
    for name in sorted(filenames):
        doc = fitz.open(queue_dir / name)
        texts[name] = "\n".join(p.get_text() for p in doc)
        doc.close()
    return build_from_texts(texts, spec)


def yoy_summary(rows: Dict[str, dict]) -> str:
    """Year-over-year by segment for every quarter with a prior-year row
    (rows must already be chronological)."""
    tags = list(rows)
    lines = []
    for i, cur in enumerate(tags):
        if i >= 4:
            pri = tags[i - 4]
            parts = [f"{lbl} {rows[cur][f] / rows[pri][f] - 1:+.0%}"
                     for f, lbl in (("usc", "US_Comm"), ("icomm", "Int_Comm"),
                                    ("usg", "US_Gov"), ("igov", "Int_Gov"))]
            lines.append(f"  {cur} vs {pri}: " + "  ".join(parts))
    return "\n".join(lines)
