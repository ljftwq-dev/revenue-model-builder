"""Chains workflow — browse verified cards, cross-link them into
parameter-justifying chains (v0.21b acceptance #3: 看卡、拉链、定参数).

Two layers:

- pure functions (:func:`build_chainbook`, :func:`render_chains_md`) —
  unit-testable, no I/O. The hard constraints (>= 2 verified cards, a
  verdict, a parameter, a valid authority) are enforced by
  ``revenue_model.evidence.Chain`` itself — chainless parameter
  revisions never reach the report;
- queue-facing helpers (:func:`load_queue_cards`) that pull verified
  cards out of a digest cache (via ``llm_digest.load_cached_cards``).

A chain spec is a JSON list of dicts::

    [{"cards": ["PLTR_Q2_2026_10Q.pdf·p19",
                {"anchor": "PLTR_Q2_2026_Business_Update.pdf·p29",
                 "quote_contains": "Net dollar retention"}],
      "verdict": "US commercial compounds: customer adds x NRR, no sales
                  headcount",
      "parameter": "US_Comm QoQ 24/22%, 2027 range 1.70-2.05",
      "authority": "user"}]

Anchor strings must match ``EvidenceCard.anchor()`` exactly
(``filename·pN``). Pages usually carry SEVERAL cards, so a bare anchor is
only accepted when it resolves to exactly one card; otherwise
disambiguate with ``quote_contains`` (unique substring of the card's
quote). See ``cards`` / ``chain`` under ``python -m revenue_model``.
"""
import json
from pathlib import Path
from typing import List

from .evidence import Chain, ChainBook, EvidenceCard


def load_queue_cards(queue_dir: Path,
                     cache_name: str = "digest_cache") -> List[EvidenceCard]:
    """All verified cards across every digested PDF in the queue, plus
    cache-only documents (8-K EX-99 exhibits and any other source that
    digested through ``digest_pages`` with no queue PDF — their page
    caches are self-contained: text + confidence travel with the raw),
    plus the news layer's cards when ``news_cache`` exists next to it.
    Needs the [pdf] extra only for the PDF branch."""
    from .llm_digest import load_cached_cards

    queue_dir = Path(queue_dir)
    cache = queue_dir / cache_name
    cards: List[EvidenceCard] = []
    pdf_stems = set()
    for pdf in sorted(queue_dir.glob("*.pdf")):
        pdf_stems.add(pdf.stem)
        if (cache / f"{pdf.stem}_p1.json").exists():
            cards.extend(load_cached_cards(pdf, cache)["cards"])
    cards.extend(_load_cache_only_documents(cache, pdf_stems))
    news_cache = queue_dir.parent / "news_cache"
    if news_cache.exists():
        from .news_layer import load_news_cards
        cards.extend(load_news_cards(news_cache))
    return cards


def _load_cache_only_documents(cache: Path,
                               pdf_stems: set) -> List[EvidenceCard]:
    """Documents living purely in the page cache (no queue PDF). Each
    page cache carries its own ``text`` so the verbatim gate re-verifies
    offline; legacy caches without ``text`` are skipped (the owning
    source path can still read them)."""
    if not cache.exists():
        return []
    from .llm_digest import _sanitize

    cards: List[EvidenceCard] = []
    for p1 in sorted(cache.glob("*_p1.json")):
        stem = p1.name[:-len("_p1.json")]
        if stem in pdf_stems or stem.startswith("."):
            continue
        i = 1
        while (cache / f"{stem}_p{i}.json").exists():
            try:
                d = json.loads((cache / f"{stem}_p{i}.json").read_text(
                    encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                break
            text = d.get("text")
            if text is None:
                break                    # legacy cache: no offline verify
            conf = d.get("confidence", "single")
            for cand in d.get("raw", []):
                card = _sanitize(cand, f"{stem}.htm", i)
                if card is None:
                    continue
                if card.verify(text).verified:
                    from dataclasses import replace
                    cards.append(replace(card, verified=True,
                                         confidence=conf))
            i += 1
    return cards


def filter_cards(cards: List[EvidenceCard], *, ring: str = None,
                 segment: str = None, grep: str = None) -> List[EvidenceCard]:
    """Ring / segment / free-text substring filters for card browsing."""
    out = cards
    if ring:
        out = [c for c in out if c.ring == ring]
    if segment:
        out = [c for c in out if segment.lower() in c.segment.lower()]
    if grep:
        needle = grep.lower()
        out = [c for c in out if needle in c.clue.lower()
               or needle in c.quote.lower()]
    return out


def _resolve(cards: List[EvidenceCard], ref) -> EvidenceCard:
    """One spec entry -> one card. Bare anchor must be unambiguous;
    dicts may add quote_contains to pick among same-page cards."""
    if isinstance(ref, str):
        anchor = ref
        sub = ""
    elif isinstance(ref, dict):
        anchor = ref.get("anchor", "")
        sub = ref.get("quote_contains", "")
    else:
        raise ValueError(f"card reference must be a string or dict, "
                         f"got {type(ref).__name__}")
    on_page = [c for c in cards if c.anchor() == anchor]
    if sub:
        hits = [c for c in on_page if sub.lower() in c.quote.lower()]
    else:
        hits = on_page
    if len(hits) == 1:
        return hits[0]
    if not hits:
        if on_page:
            raise ValueError(
                f"{anchor}: quote_contains matches nothing on that page "
                f"(page has {len(on_page)} cards)")
        raise ValueError(f"anchor not found among verified cards: {anchor}")
    heads = "; ".join(f'"{c.quote[:40]}"' for c in hits[:4])
    raise ValueError(
        f"{anchor}: ambiguous — {len(hits)} cards on that page match "
        f"({heads}...) — disambiguate with quote_contains")


def build_chainbook(cards: List[EvidenceCard], specs: List[dict]) -> ChainBook:
    """Resolve card references into chains and validate them. Raises
    ValueError describing the first unresolved/ambiguous reference."""
    book = ChainBook()
    seen = set()
    for s in specs:
        chain_cards = tuple(_resolve(cards, ref) for ref in s["cards"])
        for c in chain_cards:
            if c.anchor() not in seen:
                seen.add(c.anchor())
                book.add_card(c)
        book.add_chain(Chain(cards=chain_cards, verdict=s["verdict"],
                             parameter=s["parameter"],
                             authority=s["authority"]))
    return book


def render_cards_md(cards: List[EvidenceCard], title: str) -> str:
    """Card browsing list — anchor + clue + quote head (news cards also
    show their source line)."""
    lines = [f"# {title}", "", f"{len(cards)} 张已验证证据卡", ""]
    last_ring = None
    for c in cards:
        if c.ring != last_ring:
            lines += [f"## 环层: {c.ring}", ""]
            last_ring = c.ring
        lines.append(f"- **{c.anchor()}** {c.clue} `{c.confidence}`"
                     if c.url else f"- **{c.anchor()}** {c.clue}")
        lines.append(f'  > "{c.quote[:120]}"')
        if c.url:
            lines.append(f"  来源: {c.url} ({c.published or '日期未知'})")
    lines.append("")
    return "\n".join(lines)


def render_chains_md(book: ChainBook, title: str) -> str:
    """The run's evidence section: chains in the 线索→链条→参数 style,
    plus the coverage summary. Chains leaning on single-source news
    cards carry a visible marker (a label, never a block)."""
    lines = [f"# {title}", "",
             "标注规则: 每条线索带【文件·页码】锚点，引文逐字可回验", ""]
    for i, ch in enumerate(book.chains, start=1):
        lines += ["=" * 46,
                  f"链条{i}: {ch.verdict}",
                  "=" * 46]
        for c in ch.cards:
            lines.append(f"线索【{c.anchor()}】{c.clue}")
            lines.append(f'  > "{c.quote[:160]}"')
            if c.url:
                lines.append(f"  来源: {c.url} ({c.published or '日期未知'})")
        lines.append(f"参数 → {ch.parameter}")
        lines.append(f"权限 → {ch.authority}")
        if any(c.confidence == "single" for c in ch.cards):
            lines.append("⚠ [含单源] 本链条依赖单源新闻卡——请把一眼关再定参数")
        lines.append("")
    cov = book.coverage_summary()
    lines += ["## 覆盖", "",
              f"- 链条 {cov['chains']} 条 / 卡 {cov['verified']} 张已验证",
              f"- 文件: {', '.join(cov['files'])}", ""]
    return "\n".join(lines)


def load_spec(path: Path) -> List[dict]:
    """Read a chains spec JSON (list of {cards, verdict, parameter,
    authority})."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(x, dict) for x in data):
        raise ValueError("spec must be a JSON list of chain dicts")
    return data
