"""Declarative segment-revenue matrix — the trace method, generalized
(v0.21b acceptance #2; second-company generalization 2026-09-21).

Every quarter of every company gets one filing text and yields one
matrix row of segment revenues, double closed-loop checked. What used
to be PLTR-shaped machinery (Gov/Comm four-cell split, hard-coded
anchors) is now **data**: a :class:`MatrixSpec` declares the cells
(regex anchors + which row number is the value), derived cells, the
closed-loop equations, and per-quarter shapes — the engine below
contains zero company knowledge.

- PLTR: 2 segments × US/Intl, US splits from decks (constants),
  derived international cells, loops A/B, Q4 backcast from the 10-K.
- CEG: 6 regional segments straight from the 10-Q segment note
  (Mid-Atlantic / Midwest / New York / ERCOT / Other Power Regions /
  Calpine from the 2026 merger; 2025 quarters have five), loops =
  segments vs "Total Reportable Segments", + "Other" vs "Total
  Consolidated Results".

Anchor semantics (row-qualified): a cell matches at the n-th
occurrence of its pattern where the anchor's line — extended by one
line when the numbers sit below the label — holds k numbers ≥ min_v.
Prose mentions never qualify (no numbers on the line); a same-named
table elsewhere with a different row width (CEG's ERCOT in the
ISO-contracts note) never qualifies either. An optional scope regex
(e.g. the "N. Segment Information" note heading) bounds the search.

Pure-text parsing lives in :func:`build_from_texts` (unit-testable,
no PDF dependency); :func:`build_matrix` wraps it with PyMuPDF page
text (needs the ``[pdf]`` extra, imported lazily).
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping, Optional


class MatrixLoopError(ValueError):
    """A closed loop failed — the filing numbers do not reconcile."""


@dataclass(frozen=True)
class CellSpec:
    """One anchor: where a number lives in the filing text.

    ``mode="window"`` (the original PLTR semantics): the first k
    numbers >= min_v anywhere within ``span`` chars after the match —
    PDF text layers that put each number on its own line need the
    window. ``mode="row"`` (CEG): k numbers must sit on the anchor's
    line, extended by one line when the label stands alone — this
    row-width qualification is what keeps same-named rows in other
    tables (ERCOT in the ISO-contracts note) from qualifying.
    ``context`` (a substring required within 400 chars after the
    match) and ``stop`` (number scan ends before it) gate ambiguous
    tables in both modes. ``occurrence`` picks the n-th qualified
    match (2 = the prior-year comparative table).
    """
    key: str
    pattern: str
    k: int = 1
    idx: int = 0
    mode: str = "window"
    span: int = 300
    context: str = ""
    stop: str = ""
    occurrence: int = 1


@dataclass(frozen=True)
class DerivedSpec:
    """row[key] = row[base] - row[minus] (PLTR: Intl = seg - US)."""
    key: str
    base: str
    minus: str = ""


@dataclass(frozen=True)
class LoopSpec:
    """sum(parts) must equal the ``equals`` cell within ``tol``."""
    name: str
    parts: tuple
    equals: str
    tol: float = 2.0


@dataclass(frozen=True)
class QuarterSpec:
    """One filed quarter: filing text key, expected segment cells,
    per-quarter (k, idx) shape override, and constant injections
    (PLTR deck US splits)."""
    tag: str
    filing: str
    segments: tuple = ()          # required cell keys (None -> all)
    shape: Optional[tuple] = None  # (k, idx) overriding every cell
    constants: dict = field(default_factory=dict)


@dataclass(frozen=True)
class BackcastSpec:
    """The missing quarter derived as FY 10-K minus filed quarters.

    ``cells`` are required anchors read from the 10-K (segment
    values); ``extras`` are best-effort anchors (loop totals like
    CEG's "reportable") — parsed when present so the closed loops
    also validate the backcast row, skipped silently when not.
    ``shape`` is the (k, idx) row width for reading the 10-K tables
    (a 10-K note carries its own vintage — e.g. CEG's FY2025 note is
    the 5-column revenue-components table, value = 3rd number).
    """
    tag: str
    fy_filing: str
    cells: tuple                  # anchor cells read from the 10-K
    covered: tuple                # filed quarter tags subtracted
    constants: dict = field(default_factory=dict)
    shape: Optional[tuple] = None  # (k, idx) for the 10-K rows
    extras: tuple = ()            # best-effort loop-total anchors


@dataclass(frozen=True)
class MatrixSpec:
    """Everything needed to build the matrix for one company."""
    quarters: tuple               # QuarterSpec, chronological
    cells: dict = field(default_factory=dict)   # key -> CellSpec
    derived: tuple = ()           # DerivedSpec
    loops: tuple = ()             # LoopSpec
    backcast: Optional[BackcastSpec] = None
    min_v: float = 50.0           # $M magnitude floor per number
    unit_div: float = 1000.0      # filing units -> $M (PLTR: $K)
    scope: str = ""               # regex bounding all cell searches
    segment_cells: tuple = ()     # cells whose existence is per-quarter


_NUM_RE = re.compile(r"\(?\$?\s*([\d][\d,]*(?:\.\d+)?)\)?")
_SCOPE_OWN_LINE = 0  # re.search without M flag; patterns bring their own


def _row_numbers(seg: str, min_v: float):
    """Numbers in a row segment; parentheses mean negative."""
    seg = seg.replace("\xa0", " ")
    out = []
    for m in _NUM_RE.finditer(seg):
        v = float(m.group(1).replace(",", ""))
        if seg[m.start():m.end()].lstrip("$ \t").startswith("("):
            v = -v
        if abs(v) >= min_v:
            out.append(v)
    return out


def _cell_row(text: str, cell: CellSpec, min_v: float,
              k: int, idx: int, start: int):
    """Qualified numbers for one cell, or None."""
    qualified = []
    for m in re.finditer(cell.pattern, text):
        if m.start() < start:
            continue
        if cell.context and cell.context not in text[m.end():m.end() + 400]:
            continue
        if cell.mode == "row":
            eol = text.find("\n", m.end())
            line_end = eol if eol >= 0 else len(text)
            region = text[m.end():line_end]
            if len(_row_numbers(region, min_v)) < k:
                eol2 = text.find("\n", line_end + 1)
                region += "\n" + text[line_end + 1:
                                      eol2 if eol2 >= 0 else len(text)]
            # a table row's numbers directly follow the label (same
            # line, or alone on the next); prose wrapping puts words
            # in between ("...in ERCOT. / assets within 240 days...").
            # Footnote markers like the "(c)" in "Other(b)(c)" are
            # part of the label, not prose.
            first = _NUM_RE.search(region)
            gap = re.sub(r"\([a-z]\)", "", region[:first.start()]) \
                if first is not None else "x"
            if first is None or re.search(r"[A-Za-z]", gap):
                continue
        else:
            region = text[m.end():m.end() + cell.span]
        if cell.stop:
            region = region.split(cell.stop)[0]
        nums = _row_numbers(region, min_v)
        if len(nums) >= k:
            qualified.append(nums[:max(k, idx + 1)])
        if len(qualified) >= cell.occurrence:
            break
    if len(qualified) < cell.occurrence:
        return None
    return qualified[cell.occurrence - 1]


def _quarter_row(text: str, tag: str, q: QuarterSpec, spec: MatrixSpec) -> dict:
    """Parse one filing text into a matrix row with every loop checked."""
    start = 0
    if spec.scope:
        hits = list(re.finditer(spec.scope, text))
        if not hits:
            raise MatrixLoopError(f"{tag}: scope marker not found "
                                  f"({spec.scope!r}) — check the filing")
        start = hits[-1].end()   # the note heading, not the notes index
    k_over, idx_over = q.shape if q.shape else (None, None)
    # Parse what this quarter declares plus every always-on cell: a
    # segment that does not exist yet (CEG's Calpine before the 2026
    # merger) must stay ABSENT, never garbage-parsed from merger prose
    # that happens to carry five numbers.
    if q.segments:
        wanted = set(q.segments)
        wanted |= set(spec.cells) - set(spec.segment_cells)
    else:
        wanted = set(spec.cells)
    wanted |= {lp.equals for lp in spec.loops}
    wanted |= {d.base for d in spec.derived if d.base}
    # derived minus-keys may be injected constants (PLTR deck splits),
    # not cells — never try to parse those.
    wanted &= set(spec.cells)
    values, nums_by_key = {}, {}
    for key in wanted:
        cell = spec.cells[key]
        k = k_over if k_over is not None else cell.k
        idx = idx_over if idx_over is not None else cell.idx
        nums = _cell_row(text, cell, spec.min_v, k, idx, start)
        nums_by_key[key] = nums
        values[key] = (nums[idx] / spec.unit_div
                       if nums is not None else None)
    required = q.segments or tuple(spec.cells)
    holes = [k_ for k_ in required if values.get(k_) is None]
    if holes:
        raise MatrixLoopError(
            f"{tag}: extraction incomplete ({', '.join(holes)}) — "
            f"check the filing")
    row = {k_: v for k_, v in values.items() if v is not None}
    row.update(q.constants)
    for d in spec.derived:
        base = row.get(d.base)
        minus = row.get(d.minus, 0.0) if d.minus else 0.0
        if base is None:
            raise MatrixLoopError(
                f"{tag}: derived {d.key} has no base cell {d.base}")
        row[d.key] = round(base - (minus or 0.0), 1)
    for lp in spec.loops:
        parts = [p for p in lp.parts if row.get(p) is not None]
        s = round(sum(row[p] for p in parts), 1)
        if abs(s - row[lp.equals]) >= lp.tol:
            raise MatrixLoopError(
                f"{tag}: loop {lp.name} broken (sum {s:,.1f} vs "
                f"{lp.equals} {row[lp.equals]:,.1f})")
    # YoY only where k>=2 MEANS current/prior comparatives (PLTR rows);
    # width-shaped rows (CEG 5/6-column notes) carry other semantics.
    if q.shape is None:
        for key, nums in nums_by_key.items():
            if nums is not None and len(nums) >= 2:
                row[f"yoy_{key}"] = round(nums[0] / nums[1] - 1, 4)
    return row


def build_from_texts(texts: Mapping[str, str], spec: MatrixSpec) -> Dict[str, dict]:
    """Build the matrix from filing texts keyed by *filename*. Pure —
    no I/O, no PDF. Rows come back in chronological order."""
    rows: Dict[str, dict] = {}
    for q in spec.quarters:
        rows[q.tag] = _quarter_row(texts[q.filing], q.tag, q, spec)
    bc = spec.backcast
    if bc is not None:
        ktext = texts[bc.fy_filing]
        start = 0
        if spec.scope:
            hits = list(re.finditer(spec.scope, ktext))
            if hits:
                start = hits[-1].end()
        k_over, idx_over = bc.shape if bc.shape else (1, 0)
        row = dict(bc.constants)
        for key in bc.cells:
            cell = spec.cells[key]
            nums = _cell_row(ktext, cell, spec.min_v, k_over, idx_over,
                             start)
            if not nums:
                raise MatrixLoopError("10-K extraction failed "
                                      f"({key}) — check the filing")
            row[key] = nums[idx_over] / spec.unit_div   # raw; rounded
        for key in bc.extras:                          # best effort
            cell = spec.cells[key]
            nums = _cell_row(ktext, cell, spec.min_v, k_over, idx_over,
                             start)
            if nums:
                row[key] = nums[idx_over] / spec.unit_div
        for key in (*bc.cells, *bc.extras):            # after subtraction
            if key not in row:
                continue
            covered_sum = sum(rows[t][key] for t in bc.covered)
            row[key] = round(row[key] - covered_sum, 1)
        for d in spec.derived:
            if d.key not in bc.constants and row.get(d.base) is not None:
                minus = row.get(d.minus, 0.0) if d.minus else 0.0
                row[d.key] = round(row[d.base] - (minus or 0.0), 1)
        row["total"] = round(sum(row[k_] for k_ in bc.cells), 1)
        # the closed loops validate the backcast row too. Per-quarter
        # segment cells may be legitimately absent (CEG's Calpine
        # before the 2026 merger) and are filtered like quarterly rows;
        # any other missing part means the anchor never parsed — skip
        # that loop rather than fail it on incomplete data.
        optional = set(spec.segment_cells)
        for lp in spec.loops:
            if lp.equals not in row:
                continue
            if any(row.get(p) is None and p not in optional
                   for p in lp.parts):
                continue
            s = round(sum(row[p] for p in lp.parts
                          if row.get(p) is not None), 1)
            if abs(s - row[lp.equals]) >= lp.tol:
                raise MatrixLoopError(
                    f"{bc.tag}: loop {lp.name} broken (sum {s:,.1f} vs "
                    f"{lp.equals} {row[lp.equals]:,.1f})")
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
    cells = {
        "comm": CellSpec("comm", r"Commercial revenue", k=2),
        "gov": CellSpec("gov", r"Government revenue", k=2),
        "total": CellSpec("total", r"Total revenue", k=2),
        "us": CellSpec("us", r"United States", k=1, span=400,
                       context="Total revenue", stop="Rest of world"),
    }
    return MatrixSpec(
        quarters=(
            QuarterSpec("Q1_25", "PLTR_Q1_2025_10Q.pdf",
                        constants={"usc": 255, "usg": 373}),
            QuarterSpec("Q2_25", "PLTR_Q2_2025_10Q.pdf",
                        constants={"usc": 306, "usg": 426}),
            QuarterSpec("Q3_25", "PLTR_Q3_2025_10Q.pdf",
                        constants={"usc": 397, "usg": 486}),
            QuarterSpec("Q1_26", "PLTR_Q1_2026_10Q.pdf",
                        constants={"usc": 595, "usg": 687}),
            QuarterSpec("Q2_26", "PLTR_Q2_2026_10Q.pdf",
                        constants={"usc": 764, "usg": 809}),
        ),
        cells=cells,
        derived=(
            DerivedSpec("icomm", "comm", "usc"),
            DerivedSpec("igov", "gov", "usg"),
        ),
        loops=(
            LoopSpec("A", ("usc", "usg"), "us"),
            LoopSpec("B", ("usc", "icomm", "usg", "igov"), "total"),
        ),
        backcast=BackcastSpec(
            "Q4_25", "PLTR_FY2025_10K.pdf", ("comm", "gov"),
            ("Q1_25", "Q2_25", "Q3_25"),
            constants={"usc": 507, "usg": 570}),
        min_v=50.0, unit_div=1000.0,
    )


def ceg_spec() -> MatrixSpec:
    """Constellation Energy (2026-09 generalization): regional segments
    straight from the 10-Q segment note (Note "5. Segment Information").
    2025 quarters file five segments in 5-column RNF rows (value =
    3rd number); 2026 quarters add Calpine (Jan 7 merger) in 3/6-column
    rows (value = 1st number). Loops: segments vs Total Reportable
    Segments; + Other vs Total Consolidated Results. Q4'25 never gets a
    10-Q — backcast from the FY2025 10-K, whose note is the same
    5-column vintage (2025 table first, then 2024/2023)."""
    seg = [
        CellSpec("mid_atlantic", r"Mid-Atlantic", mode="row"),
        CellSpec("midwest", r"Midwest", mode="row"),
        CellSpec("new_york", r"New York", mode="row"),
        CellSpec("ercot", r"ERCOT", mode="row"),
        CellSpec("other_power", r"Other Power Regions", mode="row"),
        CellSpec("calpine", r"Calpine", mode="row"),
    ]
    cells = {c.key: c for c in seg}
    cells["reportable"] = CellSpec("reportable",
                                   r"Total Reportable Segments", mode="row")
    cells["other"] = CellSpec("other", r"Other\([a-z]\)", mode="row")
    cells["consolidated"] = CellSpec("consolidated",
                                     r"Total Consolidated Results",
                                     mode="row")
    five = ("mid_atlantic", "midwest", "new_york", "ercot", "other_power")
    six = five + ("calpine",)
    seg_keys = ("mid_atlantic", "midwest", "new_york", "ercot",
                "other_power", "calpine")
    return MatrixSpec(
        quarters=(
            QuarterSpec("Q1_25", "CEG_Q1_2025_10Q.pdf", five, (5, 2)),
            QuarterSpec("Q2_25", "CEG_Q2_2025_10Q.pdf", five, (5, 2)),
            QuarterSpec("Q3_25", "CEG_Q3_2025_10Q.pdf", five, (5, 2)),
            QuarterSpec("Q1_26", "CEG_Q1_2026_10Q.pdf", six, (3, 0)),
            QuarterSpec("Q2_26", "CEG_Q2_2026_10Q.pdf", six, (6, 0)),
        ),
        cells=cells,
        loops=(
            LoopSpec("S", seg_keys, "reportable"),
            LoopSpec("C", ("reportable", "other"), "consolidated"),
        ),
        backcast=BackcastSpec(
            "Q4_25", "CEG_FY2025_10K.pdf", five,
            ("Q1_25", "Q2_25", "Q3_25"),
            shape=(5, 2),       # FY2025 note: same 5-column vintage
            extras=("reportable", "other", "consolidated")),
        min_v=1.0, unit_div=1.0,
        segment_cells=seg_keys,
        scope=r"(?m)^\d+\.\s+Segment Information\s*$",
    )


def build_matrix(queue_dir: Path, spec: MatrixSpec) -> Dict[str, dict]:
    """Read the queue PDFs and build the matrix (needs the [pdf] extra)."""
    import fitz  # lazy: PyMuPDF

    queue_dir = Path(queue_dir)
    filenames = {q.filing for q in spec.quarters}
    if spec.backcast is not None:
        filenames.add(spec.backcast.fy_filing)
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
