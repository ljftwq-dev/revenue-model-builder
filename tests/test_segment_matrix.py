"""Tests for revenue_model.segment_matrix (pure-text paths + loops)."""
import pytest

from revenue_model.segment_matrix import (
    BackcastSpec,
    MatrixLoopError,
    MatrixSpec,
    QuarterSpec,
    build_from_texts,
    yoy_summary,
)


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
    return MatrixSpec(
        quarters=(
            QuarterSpec("Q1_25", "q1.pdf", (255, 373)),
            QuarterSpec("Q2_25", "q2.pdf", (306, 426)),
            QuarterSpec("Q3_25", "q3.pdf", (397, 486)),
            QuarterSpec("Q1_26", "q4.pdf", (595, 687)),
            QuarterSpec("Q2_26", "q5.pdf", (764, 809)),
        ),
        fy_10k="10k.pdf",
        backcast=BackcastSpec("Q4_25", (507, 570), ("Q1_25", "Q2_25", "Q3_25")),
    )


def make_texts():
    """Five quarters where every closed loop ties exactly."""
    t = {}
    # tag: (comm_q, comm_prior, gov_q, gov_prior, us_split from deck)
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
        us_geo = usc + usg                       # loop A ties by construction
        total = cq + gq                          # loop B ties by construction
        t[tag] = filing_text(cq, cp, gq, gp, total, total * 0.8, us_geo)
    # FY 10-K: comm/gov totals = sum of Q1..Q3 totals + a chosen Q4
    fy_comm = (396 + 487 + 538) + 620
    fy_gov = (661 + 779 + 883) + 1000
    t["10k.pdf"] = (
        f"Commercial revenue $ {int(fy_comm * 1000):,}\n"
        f"Government revenue $ {int(fy_gov * 1000):,}\n"
    )
    out = {filenames[tag]: text for tag, text in t.items() if tag != "10k.pdf"}
    out["10k.pdf"] = t["10k.pdf"]
    return out


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
    texts = make_texts()
    # deck split says US comm 300 (not 255) -> US branches != geographic US
    spec = make_spec()
    spec = MatrixSpec(
        quarters=tuple(
            QuarterSpec(q.tag, q.filing,
                        (300, q.us_split[1]) if q.tag == "Q1_25" else q.us_split)
            for q in spec.quarters),
        fy_10k=spec.fy_10k, backcast=spec.backcast)
    with pytest.raises(MatrixLoopError, match="loop A"):
        build_from_texts(texts, spec)


def test_loop_b_broken_raises():
    texts = dict(make_texts())
    # break the total: restate total revenue upward in q1.pdf
    texts["q1.pdf"] = texts["q1.pdf"].replace(
        "Total revenue $ 1,057,000", "Total revenue $ 1,200,000", 1)
    spec = make_spec()
    spec = MatrixSpec(quarters=tuple(
        QuarterSpec(q.tag, q.filing, q.us_split) for q in spec.quarters),
        fy_10k=spec.fy_10k, backcast=spec.backcast)
    with pytest.raises(MatrixLoopError, match="loop B"):
        build_from_texts(texts, spec)


def test_yoy_summary_uses_four_quarter_offset():
    rows = build_from_texts(make_texts(), make_spec())
    s = yoy_summary(rows)
    assert "Q1_26 vs Q1_25" in s and "Q2_26 vs Q2_25" in s
    assert "US_Comm" in s and "Int_Gov" in s
