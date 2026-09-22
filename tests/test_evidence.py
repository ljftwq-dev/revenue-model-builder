"""Tests for revenue_model.evidence — cards, verification, chains."""
import pytest

from revenue_model.evidence import Chain, ChainBook, EvidenceCard

PAGE = """Revenue grew +93% Y/Y to $1.94 billion this quarter.
The board approved a new buyback program."""


def card(quote="Revenue grew +93% Y/Y", **kw) -> EvidenceCard:
    kw.setdefault("clue", "record quarter")
    kw.setdefault("anchor_file", "demo.pdf")
    kw.setdefault("anchor_page", 4)
    kw.setdefault("ring", "core")
    kw.setdefault("segment", "")
    return EvidenceCard(quote=quote, **kw)


class TestCard:
    def test_verify_true_on_verbatim_quote(self):
        assert card().verify(PAGE).verified

    def test_verify_tolerates_whitespace_only_difference(self):
        # PDF keeps a line break mid-sentence; the quote uses a space
        assert card(quote="grew +93% Y/Y to $1.94 billion").verify(PAGE).verified

    def test_verify_false_on_invented_quote(self):
        assert not card(quote="CFO said growth will double").verify(PAGE).verified

    def test_verify_tolerates_asr_timestamps_in_page(self):
        # ASR transcript PDFs embed [00:02:43.98] markers mid-sentence;
        # a quote spanning one is still verbatim
        ts_page = ("Revenue grew [00:01:02.35] +93% Y/Y to $1.94 billion "
                   "this quarter.")
        assert card(quote="grew +93% Y/Y to $1.94 billion") \
            .verify(ts_page).verified

    def test_verify_strips_timestamps_symmetrically(self):
        # a quote that itself carries the marker still verifies against
        # a page carrying a different one
        ts_page = "The board [00:04:10] approved a new buyback program."
        assert card(quote="approved a new [00:09:59.99] buyback",
                    clue="buyback", ring="self") \
            .verify(ts_page).verified

    def test_bad_ring_rejected(self):
        with pytest.raises(ValueError, match="ring"):
            card(ring="gossip")

    def test_anchor_renders(self):
        assert card().anchor() == "demo.pdf·p4"


class TestChain:
    def _verified(self):
        c = card().verify(PAGE)
        c2 = card(quote="approved a new buyback", clue="buyback",
                  anchor_page=4, ring="self").verify(PAGE)
        return c, c2

    def test_valid_chain(self):
        c1, c2 = self._verified()
        ch = Chain(cards=(c1, c2), verdict="record + capital return",
                   parameter="US_Comm.qoq", authority="user")
        assert ch.anchors() == ("demo.pdf·p4", "demo.pdf·p4")

    def test_single_card_chain_rejected(self):
        c1, _ = self._verified()
        with pytest.raises(ValueError, match=">= 2"):
            Chain(cards=(c1,), verdict="v", parameter="p", authority="user")

    def test_unverified_card_cannot_chain(self):
        c1, _ = self._verified()
        bad = card(quote="never said")          # unverified
        with pytest.raises(ValueError, match="unverified"):
            Chain(cards=(c1, bad), verdict="v", parameter="p",
                  authority="user")

    def test_authority_must_be_valid(self):
        c1, c2 = self._verified()
        with pytest.raises(ValueError, match="authority"):
            Chain(cards=(c1, c2), verdict="v", parameter="p",
                  authority="machine")


class TestChainBook:
    def test_summary_counts(self):
        book = ChainBook()
        good = card().verify(PAGE)
        bad = card(quote="invented")
        book.add_card(good)
        book.add_card(bad)
        s = book.coverage_summary()
        assert s == {"cards": 2, "verified": 1, "chains": 0,
                     "files": ["demo.pdf"]}
        assert len(book.unverified()) == 1
