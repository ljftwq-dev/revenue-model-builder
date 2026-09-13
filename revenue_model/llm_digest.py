"""Document digestion (v0.21b): PDF -> per-page clue candidates -> verified
EvidenceCards.

Pipeline per document:
  PyMuPDF extracts page texts (local, zero-cost — the text source is
  always local; scanned PDFs would need an OCR pre-pass, not needed by
  the pilot) -> a digest backend proposes clue cards for ONE page at a
  time -> each card's quote is verified verbatim against that page's
  text -> verified cards only.

Backends (the model is a data source like any other — missing backend is
a Gate H question, never a hard-coded default):
  - "glm":  cloud GLM (Zhipu) via secrets_loader key; strongest semantics
  - "fake": injected callable for tests (zero network, deterministic)
Backends are page-cached to <workdir>/digest_cache/ so re-runs only pay
for unseen pages (also what makes --resume cheap).

Anti-hallucination: candidates whose quote cannot be found verbatim in
the anchored page are voided into a reject log (kept for inspection).
"""
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .evidence import EvidenceCard, RINGS

# keys a backend's per-page JSON must provide (ring/segment optional)
_REQUIRED = ("clue", "quote")


class MissingBackendError(RuntimeError):
    """Raised when no digest backend is available — the caller should turn
    this into a Gate H question, not crash."""

    def __init__(self) -> None:
        super().__init__(
            "no digest backend configured — find yourself a PDF-reading "
            "model (a cloud LLM key via secrets_loader, or point the "
            "pipeline at a local service), then --resume")


# ---------------------------------------------------------------------------
# page extraction (local, always)
# ---------------------------------------------------------------------------

def extract_pages(pdf_path: Path) -> List[str]:
    """PDF -> list of page texts (index 0 == page 1)."""
    import fitz  # PyMuPDF; extra: pip install -e ".[pdf]"

    doc = fitz.open(str(pdf_path))
    try:
        return [page.get_text() for page in doc]
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# backends
# ---------------------------------------------------------------------------

def glm_backend(page_text: str, file_name: str, page_no: int,
                model: str = "glm-4-flash") -> List[dict]:
    """One page -> candidate clue dicts via the Zhipu API. Lands with the
    pilot wiring (the pilot's offline acceptance runs on the injected
    backend); declared here so the backend contract is a type, not prose."""
    raise NotImplementedError(
        "cloud GLM backend lands with the pilot wiring; the pilot's "
        "offline acceptance runs on the injected backend")


def _sanitize(cand: dict, file_name: str, page_no: int) -> Optional[EvidenceCard]:
    """Backend dict -> EvidenceCard, or None if malformed."""
    if not isinstance(cand, dict):
        return None
    if any(not cand.get(k) for k in _REQUIRED):
        return None
    ring = cand.get("ring", "self")
    if ring not in RINGS:
        ring = "self"
    try:
        return EvidenceCard(
            clue=str(cand["clue"])[:500],
            anchor_file=file_name,
            anchor_page=page_no,
            quote=str(cand["quote"])[:2000],
            ring=ring,
            segment=str(cand.get("segment", ""))[:100],
        )
    except ValueError:
        return None


def digest_document(pdf_path: Path, backend: Callable[[str, str, int], List[dict]],
                    *, cache_dir: Optional[Path] = None) -> dict:
    """Digest one PDF: per-page backend call (cached) + verification.

    Returns {"cards": [verified EvidenceCard], "voided": [rejected raw
    candidates], "pages": n, "cached_pages": n}.
    """
    pdf_path = Path(pdf_path)
    pages = extract_pages(pdf_path)
    cache: Optional[Path] = None
    if cache_dir is not None:
        cache = Path(cache_dir)
        cache.mkdir(parents=True, exist_ok=True)
    cards: List[EvidenceCard] = []
    voided: List[dict] = []
    cached_pages = 0
    for i, text in enumerate(pages, start=1):
        page_key = f"{pdf_path.stem}_p{i}.json"
        cached_result = None
        if cache is not None and (cache / page_key).exists():
            try:
                cached_result = json.loads((cache / page_key).read_text(
                    encoding="utf-8"))
                cached_pages += 1
            except (json.JSONDecodeError, OSError):
                cached_result = None
        if cached_result is None:
            try:
                raw = backend(text, pdf_path.name, i)
            except Exception as exc:  # backend failure voids the page, not the run
                voided.append({"page": i, "error": f"{type(exc).__name__}: {exc}"})
                continue
            cached_result = {"raw": raw}
            if cache is not None:
                tmp = cache / f".{page_key}.tmp"
                tmp.write_text(json.dumps(cached_result, ensure_ascii=False),
                               encoding="utf-8")
                tmp.replace(cache / page_key)
        for cand in cached_result.get("raw", []):
            card = _sanitize(cand, pdf_path.name, i)
            if card is None:
                voided.append({"page": i, "candidate": cand})
                continue
            verified = card.verify(text)
            if verified.verified:
                cards.append(verified)
            else:
                voided.append({"page": i, "quote_not_found": cand})
    return {"cards": cards, "voided": voided, "pages": len(pages),
            "cached_pages": cached_pages}


def digest_queue(queue_dir: Path, backend: Callable,
                 *, cache_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Digest every PDF in the queue directory."""
    queue_dir = Path(queue_dir)
    out: Dict[str, Any] = {"cards": [], "voided": [], "documents": {}}
    for pdf in sorted(queue_dir.glob("*.pdf")):
        r = digest_document(pdf, backend, cache_dir=cache_dir)
        out["cards"].extend(r["cards"])
        out["voided"].extend(r["voided"])
        out["documents"][pdf.name] = {
            "pages": r["pages"], "cached": r["cached_pages"],
            "cards": len(r["cards"]), "voided": len(r["voided"])}
    return out
