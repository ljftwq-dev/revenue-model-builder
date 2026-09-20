"""Tests for revenue_model.chains_cli (pure chain building + rendering)
and llm_digest.load_cached_cards (cache-only card loading)."""
import json

import pytest

from revenue_model.chains_cli import (
    build_chainbook,
    filter_cards,
    render_cards_md,
    render_chains_md,
)
from revenue_model.evidence import EvidenceCard
from revenue_model import llm_digest


PAGE_1 = "Net dollar retention was 150% in Q1 2026, up from 139%."
PAGE_2 = "Customer count grew to 615 commercial customers on a TTM basis."
PAGE_3 = "Total contract value was 1.18 billion in the quarter."


def make_card(n: int, page_text: str, ring: str = "core",
              segment: str = "US_Comm") -> EvidenceCard:
    quotes = {
        1: "Net dollar retention was 150%",
        2: "Customer count grew to 615",
        3: "Total contract value was 1.18 billion",
    }
    clues = {
        1: "NRR 六季连升，存量复利引擎",
        2: "客户数逐季爬坡无减速",
        3: "TCV 波动大，单季读数不可靠",
    }
    c = EvidenceCard(
        clue=clues[n], anchor_file="deck.pdf", anchor_page=n,
        quote=quotes[n], ring=ring, segment=segment)
    out = c.verify(page_text)
    assert out.verified, "fixture quote must verify against fixture text"
    return out


def three_cards():
    return [make_card(1, PAGE_1), make_card(2, PAGE_2),
            make_card(3, PAGE_3, ring="updown", segment="")]


def five_cards_same_page_pair():
    """Two distinct verified cards sharing one anchor (deck.pdf·p1)."""
    extra = EvidenceCard(
        clue="另一条同页线索", anchor_file="deck.pdf", anchor_page=1,
        quote="up from 139%", ring="core", segment="US_Comm")
    assert extra.verify(PAGE_1).verified
    return three_cards() + [extra.verify(PAGE_1)]


def test_filter_cards():
    cards = three_cards()
    assert len(filter_cards(cards, ring="core")) == 2
    assert len(filter_cards(cards, ring="updown")) == 1
    assert len(filter_cards(cards, grep="NRR")) == 1
    assert len(filter_cards(cards, segment="us_comm")) == 2
    assert len(filter_cards(cards)) == 3


def test_build_chainbook_happy_path():
    cards = three_cards()
    spec = [{
        "cards": ["deck.pdf·p1", "deck.pdf·p2"],
        "verdict": "US commercial: customer adds x NRR compound engine",
        "parameter": "US_Comm QoQ 24/22%",
        "authority": "user",
    }]
    book = build_chainbook(cards, spec)
    assert len(book.chains) == 1
    cov = book.coverage_summary()
    assert cov["chains"] == 1 and cov["verified"] == 2
    assert cov["files"] == ["deck.pdf"]


def test_build_chainbook_missing_anchor_lists_all():
    cards = three_cards()
    spec = [{
        "cards": ["nope.pdf·p9", "deck.pdf·p1"], "verdict": "v",
        "parameter": "p", "authority": "user",
    }]
    with pytest.raises(ValueError, match="nope.pdf·p9"):
        build_chainbook(cards, spec)


def test_ambiguous_anchor_requires_quote_contains():
    cards = five_cards_same_page_pair()
    spec = [{
        "cards": ["deck.pdf·p1", "deck.pdf·p2"], "verdict": "v",
        "parameter": "p", "authority": "user",
    }]
    with pytest.raises(ValueError, match="ambiguous"):
        build_chainbook(cards, spec)


def test_quote_contains_disambiguates_same_page_cards():
    cards = five_cards_same_page_pair()
    spec = [{
        "cards": [{"anchor": "deck.pdf·p1",
                   "quote_contains": "Net dollar retention"},
                  "deck.pdf·p2"],
        "verdict": "v", "parameter": "p", "authority": "user",
    }]
    book = build_chainbook(cards, spec)
    assert len(book.chains) == 1
    quotes = [c.quote for c in book.chains[0].cards]
    assert any("Net dollar retention" in q for q in quotes)
    assert not any("up from 139%" == q for q in quotes)


def test_chain_constraints_enforced_through_spec():
    cards = three_cards()
    one_card = [{"cards": ["deck.pdf·p1"], "verdict": "v",
                 "parameter": "p", "authority": "user"}]
    with pytest.raises(ValueError, match=">= 2"):
        build_chainbook(cards, one_card)
    bad_auth = [{"cards": ["deck.pdf·p1", "deck.pdf·p2"], "verdict": "v",
                 "parameter": "p", "authority": "model"}]
    with pytest.raises(ValueError, match="authority"):
        build_chainbook(cards, bad_auth)


def test_render_chains_md_contains_anchors_and_params():
    cards = three_cards()
    spec = [{
        "cards": ["deck.pdf·p1", "deck.pdf·p2"],
        "verdict": "V", "parameter": "US_Comm QoQ 24/22%",
        "authority": "user",
    }]
    md = render_chains_md(build_chainbook(cards, spec), "T")
    assert "链条1" in md and "US_Comm QoQ 24/22%" in md
    assert "deck.pdf·p1" in md and "deck.pdf·p2" in md
    assert "user" in md


def test_render_cards_md_groups_by_ring():
    md = render_cards_md(three_cards(), "浏览")
    assert "## 环层: core" in md and "## 环层: updown" in md
    assert "3 张已验证证据卡" in md


def test_load_cached_cards_from_cache(tmp_path, monkeypatch):
    """Cache-only loading: monkeypatch page extraction, no PDF needed."""
    pdf = tmp_path / "deck.pdf"
    pdf.write_bytes(b"%PDF-fake")
    cache = tmp_path / "digest_cache"
    cache.mkdir()
    monkeypatch.setattr(
        llm_digest, "extract_pages", lambda p: [PAGE_1, PAGE_2])
    good = {"clue": "NRR 攀升", "quote": "Net dollar retention was 150%",
            "ring": "core", "segment": "US_Comm"}
    bad_quote = {"clue": "编造", "quote": "THIS QUOTE DOES NOT EXIST",
                 "ring": "core", "segment": ""}
    malformed = {"clue": "", "quote": "no clue"}          # _sanitize -> None
    (cache / "deck_p1.json").write_text(
        json.dumps({"raw": [good, bad_quote, malformed]}, ensure_ascii=False),
        encoding="utf-8")
    (cache / "deck_p2.json").write_text(
        json.dumps({"raw": [{"clue": "客户爬坡", "quote": "Customer count grew to 615",
                             "ring": "core", "segment": "US_Comm"}]},
                    ensure_ascii=False),
        encoding="utf-8")
    r = llm_digest.load_cached_cards(pdf, cache)
    assert r["pages"] == 2 and r["undigested"] == 0
    assert len(r["cards"]) == 2                    # good p1 + good p2
    kinds = {v.get("quote_not_found") is not None for v in r["voided"]}
    assert True in kinds                           # bad_quote voided
    anchors = {c.anchor() for c in r["cards"]}
    assert anchors == {"deck.pdf·p1", "deck.pdf·p2"}


def test_load_cached_cards_skips_undigested(tmp_path, monkeypatch):
    pdf = tmp_path / "deck.pdf"
    pdf.write_bytes(b"%PDF-fake")
    cache = tmp_path / "digest_cache"
    cache.mkdir()
    monkeypatch.setattr(
        llm_digest, "extract_pages", lambda p: [PAGE_1, PAGE_2, PAGE_3])
    r = llm_digest.load_cached_cards(pdf, cache)   # cache empty
    assert r["cards"] == [] and r["undigested"] == 3


# ---------------------------------------------------------------------------
# cache-only documents (8-K EX-99 style) through load_queue_cards
# ---------------------------------------------------------------------------

def test_load_queue_cards_cache_only_document(tmp_path):
    """A document digested via digest_pages with NO queue PDF still
    browses: the self-contained cache (text + confidence) re-verifies
    offline, primary stamp survives the round-trip."""
    from revenue_model.chains_cli import load_queue_cards
    from revenue_model.llm_digest import digest_pages

    queue = tmp_path / "queue"
    queue.mkdir()
    calls = []

    def backend(text, name, page):
        calls.append(page)
        return [{"clue": "Q2 调整后每股营业收益 2.55 美元",
                 "quote": "Adjusted Operating Earnings of 2.55",
                 "ring": "core", "segment": ""},
                {"clue": "编造", "quote": "NOT IN THE PAGE AT ALL",
                 "ring": "core", "segment": ""}]

    r = digest_pages(["GAAP Net Income of 1.42 and Adjusted Operating "
                      "Earnings of 2.55 per share." + " filler " * 80],
                     "8K_000186827526000097_ceg-20260806991.htm", backend,
                     cache_dir=queue / "digest_cache",
                     cache_stem="8K_000186827526000097_ceg-20260806991",
                     confidence="primary")
    assert len(r["cards"]) == 1 and r["cards"][0].confidence == "primary"
    assert calls == [1]

    cards = load_queue_cards(queue)
    assert len(cards) == 1                       # fabricated quote voided
    c = cards[0]
    assert c.verified and c.confidence == "primary"
    assert c.anchor_file == "8K_000186827526000097_ceg-20260806991.htm"
    assert c.anchor().endswith("p1")


def test_load_queue_cards_skips_legacy_cache_without_text(tmp_path):
    """Legacy page caches (raw only, no text) must not crash or lie:
    the cache-only branch skips them silently."""
    from revenue_model.chains_cli import load_queue_cards

    queue = tmp_path / "queue"
    cache = queue / "digest_cache"
    cache.mkdir(parents=True)
    (cache / "legacydoc_p1.json").write_text(
        json.dumps({"raw": [{"clue": "x", "quote": "y",
                             "ring": "core", "segment": ""}]}),
        encoding="utf-8")
    assert load_queue_cards(queue) == []
