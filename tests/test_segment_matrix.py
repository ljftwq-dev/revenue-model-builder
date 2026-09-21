"""Tests for revenue_model.segment_matrix — the declarative engine.

PLTR block: the original synthetic live-drill fixtures (same numbers,
same assertions) prove the generalization changed nothing observable.
CEG block: synthetic segment notes reproduce every real trap the
2026-09 second-company run hit — the notes-index scope decoy, prose
wrapping numbers onto an anchor's next line, the cash-flow-statement
"Acquisition of Calpine" line, ERCOT's second life in the ISO
contracts table, footnote markers like "Other(b)(c)", and the two
filing vintages (2025 five-column rows, 2026 three/six-column rows).
"""
import pytest

from revenue_model.segment_matrix import (
    BackcastSpec,
    CellSpec,
    DerivedSpec,
    LoopSpec,
    MatrixLoopError,
    MatrixSpec,
    QuarterSpec,
    build_from_texts,
    ceg_spec,
    yoy_summary,
)


# ---------------------------------------------------------------- pltr

def filing_text(comm_q, comm_prior, gov_q, gov_prior, total_q, total_prior,
                us_geo):
    """Synthetic 10-Q text with the three segment anchors in filing order
    (segment note first, geographic table last). All values in $K."""
    def k(v):
        return f"{int(v * 1000):,}"

    return (
        f"Commercial revenue $ {k(comm_q)} $ {k(comm_prior)}\n"
        f"Government revenue $ {k(gov_q)} $ {k(gov_prior)}\n"
        f"Total revenue $ {k(total_q)} $ {k(total_prior)}\n"
        "Some narrative in between.\n"
        f"United States $ {k(us_geo)} Rest of world $ 200,000 "
        f"Total revenue $ {k(total_q)} $ {k(total_prior)}\n"
    )


def make_spec():
    cells = {
        "comm": CellSpec("comm", r"Commercial revenue", k=2),
        "gov": CellSpec("gov", r"Government revenue", k=2),
        "total": CellSpec("total", r"Total revenue", k=2),
        "us": CellSpec("us", r"United States", k=1, span=400,
                       context="Total revenue", stop="Rest of world"),
    }
    return MatrixSpec(
        quarters=(
            QuarterSpec("Q1_25", "q1.pdf", constants={"usc": 255, "usg": 373}),
            QuarterSpec("Q2_25", "q2.pdf", constants={"usc": 306, "usg": 426}),
            QuarterSpec("Q3_25", "q3.pdf", constants={"usc": 397, "usg": 486}),
            QuarterSpec("Q1_26", "q4.pdf", constants={"usc": 595, "usg": 687}),
            QuarterSpec("Q2_26", "q5.pdf", constants={"usc": 764, "usg": 809}),
        ),
        cells=cells,
        derived=(DerivedSpec("icomm", "comm", "usc"),
                 DerivedSpec("igov", "gov", "usg")),
        loops=(LoopSpec("A", ("usc", "usg"), "us"),
               LoopSpec("B", ("usc", "icomm", "usg", "igov"), "total")),
        backcast=BackcastSpec("Q4_25", "10k.pdf", ("comm", "gov"),
                              ("Q1_25", "Q2_25", "Q3_25"),
                              constants={"usc": 507, "usg": 570}),
        min_v=50.0, unit_div=1000.0,
    )


def make_texts():
    """Five quarters where every closed loop ties exactly."""
    t = {}
    data = {
        "Q1_25": (396, 300, 661, 500, (255, 373)),
        "Q2_25": (487, 396, 779, 661, (306, 426)),
        "Q3_25": (538, 487, 883, 779, (397, 486)),
        "Q1_26": (736, 538, 1239, 883, (595, 687)),
        "Q2_26": (905, 736, 1445, 1239, (764, 809)),
    }
    filenames = {"Q1_25": "q1.pdf", "Q2_25": "q2.pdf", "Q3_25": "q3.pdf",
                 "Q1_26": "q4.pdf", "Q2_26": "q5.pdf"}
    for tag, (cq, cp, gq, gp, (usc, usg)) in data.items():
        us_geo = usc + usg
        total = cq + gq
        t[tag] = filing_text(cq, cp, gq, gp, total, total * 0.8, us_geo)
    fy_comm = (396 + 487 + 538) + 620
    fy_gov = (661 + 779 + 883) + 1000
    t["10k.pdf"] = (
        f"Commercial revenue $ {int(fy_comm * 1000):,}\n"
        f"Government revenue $ {int(fy_gov * 1000):,}\n"
    )
    return {filenames[tag]: text for tag, text in t.items() if tag != "10k.pdf"} \
        | {"10k.pdf": t["10k.pdf"]}


def test_quarterly_rows_and_loops():
    rows = build_from_texts(make_texts(), make_spec())
    assert list(rows) == ["Q1_25", "Q2_25", "Q3_25", "Q4_25",
                          "Q1_26", "Q2_26"]        # chronological, Q4 inserted
    q1 = rows["Q1_25"]
    assert q1["usc"] == 255 and q1["usg"] == 373
    assert q1["icomm"] == pytest.approx(141, abs=0.5)   # 396 - 255
    assert q1["igov"] == pytest.approx(288, abs=0.5)    # 661 - 373
    assert q1["total"] == pytest.approx(1057, abs=1.0)
    assert q1["yoy_comm"] == pytest.approx(396 / 300 - 1, abs=1e-3)


def test_q4_backcast_math():
    rows = build_from_texts(make_texts(), make_spec())
    q4 = rows["Q4_25"]
    assert q4["usc"] == 507 and q4["usg"] == 570
    assert q4["icomm"] == pytest.approx(620 - 507, abs=0.5)
    assert q4["igov"] == pytest.approx(1000 - 570, abs=0.5)
    assert q4["total"] == pytest.approx(620 + 1000, abs=1.0)


def test_loop_a_broken_raises():
    spec = make_spec()
    quarters = tuple(
        QuarterSpec(
            q.tag, q.filing,
            constants={"usc": 300, "usg": q.constants["usg"]}
            if q.tag == "Q1_25" else dict(q.constants))
        for q in spec.quarters)
    spec = MatrixSpec(quarters=quarters, cells=spec.cells,
                      derived=spec.derived, loops=spec.loops,
                      backcast=spec.backcast, min_v=spec.min_v,
                      unit_div=spec.unit_div)
    with pytest.raises(MatrixLoopError, match="loop A"):
        build_from_texts(make_texts(), spec)


def test_loop_b_broken_raises():
    texts = dict(make_texts())
    texts["q1.pdf"] = texts["q1.pdf"].replace(
        "Total revenue $ 1,057,000", "Total revenue $ 1,200,000", 1)
    spec = make_spec()
    with pytest.raises(MatrixLoopError, match="loop B"):
        build_from_texts(texts, spec)


def test_yoy_summary_uses_four_quarter_offset():
    rows = build_from_texts(make_texts(), make_spec())
    s = yoy_summary(rows)
    assert "Q1_26 vs Q1_25" in s and "Q2_26 vs Q2_25" in s
    assert "US_Comm" in s and "Int_Gov" in s


def test_pltr_spec_shapes_load():
    """The shipped PLTR spec builds (filenames/loops sanity)."""
    spec = None
    from revenue_model.segment_matrix import pltr_spec
    spec = pltr_spec()
    assert [q.tag for q in spec.quarters] == \
        ["Q1_25", "Q2_25", "Q3_25", "Q1_26", "Q2_26"]
    assert spec.backcast.tag == "Q4_25"


# ----------------------------------------------------------------- ceg

def ceg_note_text(segs, other, vintage):
    """Synthetic CEG note with the real traps baked in:
    - a notes INDEX line "5. Segment Information 21" before the real
      heading (scope must take the LAST match);
    - a cash-flow line "Acquisition of Calpine, net of cash...(2,537)"
      (label followed by words then a number - must not qualify);
    - ERCOT in the ISO contracts table ("ERCOT630 · · 630" - wrong
      row width for every vintage, must not qualify);
    - prose "...also in ERCOT." wrapping numbers onto the next line
      ("assets within 240 days... by September 4, 2026" - words in
      the label-to-number gap, must not qualify);
    - totals labels standing alone with numbers on the next line;
    - a double footnote marker "Other(b)(c)".
    ``segs``: {name: (row numbers tuple)}; ``other``: 5/3-tuple.
    """
    def row(nums):
        parts = [f"({abs(v):,})" if v < 0 else f"{v:,}" for v in nums]
        return " ".join(parts)

    lines = [
        "Combined Notes to Consolidated Financial Statements",
        "5. Segment Information 21",           # notes index decoy
        "6. Government Assistance 24",
        "Acquisition of Calpine, net of cash and restricted cash "
        "acquired (2,537)",
        "Other investing activities 148 (12)",
        "ERCOT630 · · 630",                    # ISO contracts table
        "Total Power revenues 9,935 54 · 9,988",
        "5. Segment Information",              # the real heading
        "We have five reportable segments. Details on the divestiture "
        "of certain assets in ERCOT.",
        "The DOJ resolution requires divestiture of these assets "
        "within 240 days of closing, by September 4, 2026.",
    ]
    for name, nums in segs.items():
        lines.append(f"{name}{row(nums)}")
    rep = tuple(sum(v[i] for v in segs.values()) for i in range(len(next(iter(segs.values())))))
    lines.append("Total Reportable Segments")
    lines.append(row(rep))
    lines.append("Other(b)(c)" if vintage == "foot" else "Other(b)")
    lines.append(row(other))
    cons = tuple(rep[i] + other[i] for i in range(len(rep)))
    lines.append("Total Consolidated Results")
    lines.append(row(cons))
    return "\n".join(lines) + "\n"


def ceg_texts():
    """Five filings tying by construction across both vintages."""
    t = {}
    # 2025 vintage: (contracts, other, total, expense, RNF) rows
    t["CEG_Q1_2025_10Q.pdf"] = ceg_note_text({
        "Mid-Atlantic": (1606, 59, 1665, -856, 809),
        "Midwest": (1310, 94, 1404, -554, 850),
        "New York": (675, -113, 562, -161, 401),
        "ERCOT": (301, 97, 398, -184, 214),
        "Other Power Regions": (1377, 179, 1556, -1362, 194),
    }, (837, 366, 1203, -1267, -64), "plain")
    t["CEG_Q2_2025_10Q.pdf"] = ceg_note_text({
        "Mid-Atlantic": (1435, 13, 1448, -666, 782),
        "Midwest": (1428, 96, 1524, -488, 1036),
        "New York": (514, 21, 535, -138, 397),
        "ERCOT": (328, 136, 464, -193, 271),
        "Other Power Regions": (1030, 148, 1178, -997, 181),
    }, (426, 526, 952, -650, 302), "plain")
    t["CEG_Q3_2025_10Q.pdf"] = ceg_note_text({
        "Mid-Atlantic": (1770, -7, 1763, -871, 892),
        "Midwest": (1222, 168, 1390, -447, 943),
        "New York": (582, -24, 558, -159, 399),
        "ERCOT": (375, 253, 628, -213, 415),
        "Other Power Regions": (1313, 230, 1543, -1200, 343),
    }, (441, 247, 688, -677, 11), "foot")   # tiny RNF 11 < 50 floor
    # 2026 vintage Q1: (rev, expense, RNF) rows
    t["CEG_Q1_2026_10Q.pdf"] = ceg_note_text({
        "Mid-Atlantic": (1847, -1035, 812),
        "Midwest": (1732, -878, 854),
        "New York": (569, -160, 409),
        "ERCOT": (370, -161, 209),
        "Other Power Regions": (1487, -1220, 267),
        "Calpine": (2395, -1269, 1126),
    }, (2722, -1629, 1093), "plain")
    # 2026 vintage Q2: six-number side-by-side rows (3M'26 + 3M'25)
    t["CEG_Q2_2026_10Q.pdf"] = ceg_note_text({
        "Mid-Atlantic": (1555, -400, 1155, 1448, -380, 1068),
        "Midwest": (1568, -380, 1188, 1524, -350, 1174),
        "New York": (564, -150, 414, 535, -140, 395),
        "ERCOT": (446, -120, 326, 464, -130, 334),
        "Other Power Regions": (964, -400, 564, 1178, -380, 798),
        "Calpine": (2147, -700, 1447, 200, -60, 140),
    }, (260, -100, 160, 580, -180, 400), "plain")
    # FY2025 10-K: same 5-column vintage as the 2025 10-Qs, FY totals
    # = Q1+Q2+Q3 (from the rows above) + the chosen Q4 values; a 2024
    # year-table sits below as the occurrence decoy
    t["CEG_FY2025_10K.pdf"] = ceg_note_text({
        "Mid-Atlantic": (6476, 400, 6876, -3076, 3800),
        "Midwest": (5218, 1200, 6418, -2102, 4316),
        "New York": (2255, 200, 2455, -590, 1865),
        "ERCOT": (1890, 500, 2390, -767, 1623),
        "Other Power Regions": (5277, 900, 6177, -4764, 1413),
    }, (3143, 700, 3843, -3382, 461), "foot") + (
        "2024\n"
        "Mid-Atlantic$5,429 $93 $5,522 $(2,442)$3,080\n"
        "Midwest3,848 957 4,805 (1,603)3,202\n"
        "New York1,937 113 2,050 (597)1,453\n"
        "ERCOT1,053 497 1,550 (503)1,047\n"
        "Other Power Regions4,749 757 5,506 (4,238)1,268\n"
        "Total Reportable Segments\n"
        "17,016 2,417 19,433 (9,383)10,050\n"
        "Other(b)\n"
        "1,948 2,187 4,135 (2,036)2,099\n"
        "Total Consolidated Results\n"
        "$18,964 $4,604 $23,568 $(11,419)$12,149\n")
    return t


def test_ceg_matrix_all_quarters_all_loops():
    rows = build_from_texts(ceg_texts(), ceg_spec())
    assert list(rows) == ["Q1_25", "Q2_25", "Q3_25", "Q4_25",
                          "Q1_26", "Q2_26"]    # Q4 backcast inserted
    q1 = rows["Q1_25"]
    assert q1["mid_atlantic"] == 1665 and q1["ercot"] == 398
    assert "calpine" not in q1                      # absent, not garbage
    assert q1["reportable"] == 5585 and q1["consolidated"] == 6788
    q3 = rows["Q3_25"]
    assert q3["other"] == 688                        # "(c)" marker survived
    q4 = rows["Q1_26"]
    assert q4["calpine"] == 2395                     # label-alone row read
    assert q4["reportable"] == 8400 and q4["consolidated"] == 11122
    q5 = rows["Q2_26"]
    assert q5["mid_atlantic"] == 1555 and q5["calpine"] == 2147
    assert q5["reportable"] == 7244 and q5["consolidated"] == 7504


def test_ceg_q4_backcast_math_and_year_table_decoy():
    rows = build_from_texts(ceg_texts(), ceg_spec())
    q4 = rows["Q4_25"]
    # FY − (Q1+Q2+Q3): e.g. Mid-Atlantic 6876 − (1665+1448+1763) = 2000
    assert q4["mid_atlantic"] == 2000 and q4["new_york"] == 800
    assert q4["midwest"] == 2100 and q4["ercot"] == 900
    assert q4["other_power"] == 1900
    # from the FY2025 table's occurrence-1, never the 2024 decoy below
    # (Mid-Atlantic FY2024 5,522 − 4,876 = 646 would be the wrong Q4)
    assert q4["mid_atlantic"] != 646
    # best-effort extras let both loops close on the backcast row
    assert q4["reportable"] == 7700 and q4["other"] == 1000
    assert q4["consolidated"] == 8700
    assert q4["total"] == 7700


def test_ceg_backcast_loop_broken_raises():
    texts = ceg_texts()
    # corrupt the FY2025 Mid-Atlantic row: total 6,876 -> 7,000 makes
    # the Q4 backcast sum miss the backcast reportable (loop S)
    texts["CEG_FY2025_10K.pdf"] = texts["CEG_FY2025_10K.pdf"].replace(
        "Mid-Atlantic6,476 400 6,876", "Mid-Atlantic6,476 400 7,000", 1)
    with pytest.raises(MatrixLoopError, match="Q4_25: loop S"):
        build_from_texts(texts, ceg_spec())


def test_ceg_loop_broken_raises():
    texts = ceg_texts()
    # corrupt one segment row: Mid-Atlantic total 1665 -> 1700
    texts["CEG_Q1_2025_10Q.pdf"] = texts["CEG_Q1_2025_10Q.pdf"].replace(
        "Mid-Atlantic1,606 59 1,665", "Mid-Atlantic1,606 59 1,700", 1)
    with pytest.raises(MatrixLoopError, match="loop S"):
        build_from_texts(texts, ceg_spec())


def test_ceg_missing_segment_raises():
    texts = ceg_texts()
    # drop the Calpine row from the 2026 filing -> required cell missing
    texts["CEG_Q1_2026_10Q.pdf"] = texts["CEG_Q1_2026_10Q.pdf"].replace(
        "Calpine2,395 (1,269) 1,126\n", "", 1)
    with pytest.raises(MatrixLoopError, match="extraction incomplete"):
        build_from_texts(texts, ceg_spec())
