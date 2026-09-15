"""Evidence cards and chains (v0.21b) — the codified trace method.

Every clue carries a precise anchor (file · page · verbatim quote); every
chain links >= 2 verified clues into a verdict that justifies exactly one
parameter, recording whether the authority is the user or a user-delegated
self-judgment (the Gate H protocol).

Hard constraints, enforced structurally:
- a card is only *verified* if its quote appears verbatim (modulo
  whitespace) in the anchored page's text — unverified cards cannot enter
  a chain;
- a chain needs >= 2 verified cards, a verdict, a parameter, and a valid
  authority — chainless parameter revisions never reach the report.
"""
import re
from dataclasses import dataclass, field, replace
from typing import Tuple

RINGS = ("core", "self", "updown", "macro")
AUTHORITIES = ("user", "user-delegated")
CONFIDENCES = ("primary", "dual", "single")


def _norm_ws(s: str) -> str:
    """Collapse all whitespace runs to single spaces (PDF text keeps
    line breaks mid-sentence; a verbatim quote may differ only in ws)."""
    return re.sub(r"\s+", " ", s).strip()


@dataclass(frozen=True)
class EvidenceCard:
    """One clue with its precise, verifiable anchor.

    Filings anchor on file + page; news cards anchor on a domain slug
    with page 1 and carry ``url`` / ``published`` / ``confidence``
    (v0.22 news layer: primary = underlying document, dual = >= 2
    independent origins, single = everything else — a label, never a
    deletion)."""
    clue: str
    anchor_file: str
    anchor_page: int
    quote: str
    ring: str                 # RINGS
    segment: str              # branch the clue hangs on ("" = company-level)
    verified: bool = False
    url: str = ""
    published: str = ""
    confidence: str = "single"    # CONFIDENCES

    def __post_init__(self) -> None:
        if not self.clue or not self.quote:
            raise ValueError("clue and quote are required")
        if self.anchor_page < 1:
            raise ValueError("anchor_page is 1-based")
        if self.ring not in RINGS:
            raise ValueError(f"ring must be one of {RINGS}")
        if self.confidence not in CONFIDENCES:
            raise ValueError(f"confidence must be one of {CONFIDENCES}")

    def verify(self, page_text: str) -> "EvidenceCard":
        """Return a copy with verified set by verbatim quote search."""
        return replace(self, verified=_norm_ws(self.quote) in _norm_ws(page_text))

    def anchor(self) -> str:
        return f"{self.anchor_file}·p{self.anchor_page}"


@dataclass(frozen=True)
class Chain:
    """Clues cross-linked into one verdict justifying one parameter."""
    cards: Tuple[EvidenceCard, ...]
    verdict: str
    parameter: str
    authority: str            # AUTHORITIES

    def __post_init__(self) -> None:
        if len(self.cards) < 2:
            raise ValueError("a chain needs >= 2 clues")
        if any(not c.verified for c in self.cards):
            raise ValueError("unverified cards cannot enter a chain "
                             "(call .verify(page_text) first)")
        if not self.verdict or not self.parameter:
            raise ValueError("verdict and parameter are required")
        if self.authority not in AUTHORITIES:
            raise ValueError(f"authority must be one of {AUTHORITIES}")

    def anchors(self) -> Tuple[str, ...]:
        return tuple(c.anchor() for c in self.cards)


@dataclass
class ChainBook:
    """The run's cards and chains — what the report's evidence section
    renders and what parameter revisions must cite."""
    cards: list = field(default_factory=list)
    chains: list = field(default_factory=list)

    def add_card(self, card: EvidenceCard) -> None:
        self.cards.append(card)

    def add_chain(self, chain: Chain) -> None:
        self.chains.append(chain)

    def unverified(self) -> list:
        return [c for c in self.cards if not c.verified]

    def coverage_summary(self) -> dict:
        files = sorted({c.anchor_file for c in self.cards})
        return {"cards": len(self.cards),
                "verified": len(self.cards) - len(self.unverified()),
                "chains": len(self.chains),
                "files": files}
