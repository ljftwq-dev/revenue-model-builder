"""form10q — 10-Q filings from EDGAR into the workspace queue.

PLTR's queue 10-Qs came from IR-site PDF links; the second-company run
(CEG, 2026-09) needs the EDGAR route instead — the quarterly report
lives there as iXBRL HTML. This adapter lands those filings in the
queue as text-layer PDFs so downstream consumers stay uniform:

    queue PDF  ->  segment_matrix.build_matrix  (text layer)
               ->  llm_digest.digest_document  (per-page cards)

Stages (resumable, mirroring form8k_adapter / form8k_exhibit):

    list    submissions API -> 10-Q filings; an amendment (10-Q/A)
            supersedes the original for the same report period
    land    primary-document HTML -> extracted text (the 8-K exhibit
            extractor) -> text-layer PDF (the webcast transcript
            renderer) written as ``{TICKER}_{Q#}_{YYYY}_10Q.pdf``
    digest  the standard per-page digest + verbatim-verify channel

Design (mirrors the sibling adapters):
- **Pure stdlib** (``urllib`` + ``html.parser``). No SDK, no key.
- **Injectable getters** (``http_get`` for the submissions JSON,
  ``http_get_text`` for the filing HTML) and an injectable
  ``pdf_writer`` — offline tests never touch the network or fitz.
- The primary document name comes straight from the submissions API
  (``primaryDocument``), so no filing-index guesswork is needed.
- ``quarter_tag`` only recognizes calendar quarter ends (Mar/Jun/
  Sep/Dec); a non-calendar filer's periods are skipped, not guessed.
- Idempotent: an existing queue PDF is kept unless ``refresh=True``.
"""
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from . import cache, form8k_adapter, sec_adapter
from .form8k_exhibit import (_fetch_text, _resolve_cik, exhibit_to_pages,
                             DEFAULT_PAGE_CHARS)

DEFAULT_UA = sec_adapter.DEFAULT_UA

_ARCHIVES_DOC = ("https://www.sec.gov/Archives/edgar/data/"
                 "{cik}/{nod}/{name}")

_QUARTER_MONTHS = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}

PdfWriter = Callable[[str, Path, List[str]], Path]


def quarter_tag(report_date: str) -> Optional[str]:
    """Period end ``'2026-06-30'`` -> ``'Q2_2026'`` (calendar fiscal).

    ``None`` when the month is not a quarter boundary (non-calendar
    filers) — those periods are skipped rather than mis-tagged.
    """
    try:
        year, month, _day = report_date.split("-")
        q = _QUARTER_MONTHS.get(int(month))
    except (ValueError, AttributeError):
        return None
    return f"{q}_{year}" if q else None


def fetch_10q_filings(ticker_or_cik: Union[str, int], *, since=None,
                      http_get: Optional[Callable] = None,
                      user_agent: str = DEFAULT_UA, timeout: int = 30,
                      use_cache: bool = True, refresh: bool = False
                      ) -> List[Dict[str, Any]]:
    """Ticker or CIK -> 10-Q filings, oldest-first.

    Amendments supersede: when several accessions share a report
    period (``10-Q`` + ``10-Q/A``), the latest filing date wins —
    the queue should hold the corrected text, not the withdrawn one.

    Returns a list of dicts, each::

        {"date": datetime, "report_date": "YYYY-MM-DD",
         "form": "10-Q" | "10-Q/A", "accession": str,
         "file": primary document name, "url": str}

    Built on the same submissions API read as
    :func:`revenue_model.form8k_adapter.fetch_8k_events` (cached per
    CIK; injected getters bypass).
    """
    cik = _resolve_cik(ticker_or_cik, http_get=http_get,
                       user_agent=user_agent, timeout=timeout,
                       use_cache=use_cache, refresh=refresh)
    cache_enabled = use_cache and http_get is None
    key = cache.cache_key("sec_submissions_10q", cik)
    if cache_enabled:
        hit, cached = cache.cache_get(key, refresh)
        if hit:
            events = [_from_cached(e) for e in cached]
        else:
            events = _parse_submissions(form8k_adapter._fetch(
                cik, http_get=http_get, user_agent=user_agent,
                timeout=timeout))
            cache.cache_set(key, [_to_cached(e) for e in events])
    else:
        events = _parse_submissions(form8k_adapter._fetch(
            cik, http_get=http_get, user_agent=user_agent, timeout=timeout))
    for e in events:  # the archives URL needs the cik; parse is cik-free
        e["url"] = _ARCHIVES_DOC.format(
            cik=cik, nod=e["accession"].replace("-", ""), name=e["file"])
    if since is not None:
        if isinstance(since, str):
            since = datetime.strptime(since, "%Y-%m-%d")
        elif not isinstance(since, datetime):
            since = datetime(since.year, since.month, since.day)
        events = [e for e in events if e["date"] >= since]
    return events


def _parse_submissions(sub: dict) -> List[Dict[str, Any]]:
    """Parallel filings arrays -> superseded 10-Q event list."""
    recent = sub.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    fdates = recent.get("filingDate", [])
    rdates = recent.get("reportDate", [])
    accs = recent.get("accessionNumber", [])
    pdocs = recent.get("primaryDocument", [])
    best: Dict[str, dict] = {}
    for form, fd, rd, acc, pdoc in zip(forms, fdates, rdates, accs, pdocs):
        if form not in ("10-Q", "10-Q/A"):
            continue
        if not fd or not rd or not pdoc:
            continue
        if not str(pdoc).lower().endswith((".htm", ".html")):
            continue  # e.g. inline-XBRL viewer artifacts
        tag = quarter_tag(str(rd))
        if tag is None:
            continue
        cur = best.get(tag)
        if cur is not None and str(fd) <= cur["filing_date"]:
            continue  # superseded by a later filing for the period
        best[tag] = {"filing_date": str(fd), "report_date": str(rd),
                     "form": str(form), "accession": str(acc or ""),
                     "file": str(pdoc)}
    out: List[Dict[str, Any]] = []
    for tag in sorted(best, key=lambda t: best[t]["filing_date"]):
        e = best[tag]
        out.append({"date": datetime.strptime(e["filing_date"], "%Y-%m-%d"),
                    "report_date": e["report_date"], "form": e["form"],
                    "accession": e["accession"], "file": e["file"],
                    "url": ""})
    return out


def _default_pdf_writer(text: str, pdf: Path, header: List[str]) -> Path:
    """Extracted filing text -> text-layer PDF (needs ``[pdf]``)."""
    import tempfile

    from .webcast import transcript_pdf

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8") as f:
        f.write(text)
        tmp = Path(f.name)
    try:
        return transcript_pdf(tmp, Path(pdf), header=header)
    finally:
        tmp.unlink(missing_ok=True)


def queue_10q(ticker: str, queue_dir: Path, *, since=None,
              pdf_writer: Optional[PdfWriter] = None,
              http_get: Optional[Callable] = None,
              http_get_text: Optional[Callable] = None,
              user_agent: str = DEFAULT_UA, timeout: int = 30,
              max_chars: int = DEFAULT_PAGE_CHARS,
              use_cache: bool = True, refresh: bool = False
              ) -> List[Dict[str, Any]]:
    """Land every fetched 10-Q as a text-layer PDF in ``queue_dir``.

    A ticker symbol is required (the queue file name is ticker-based:
    ``{TICKER}_{Q#}_{YYYY}_10Q.pdf``, matching the PLTR queue
    convention). Existing PDFs are kept (idempotent) unless
    ``refresh=True``. Returns one dict per filing::

        {"pdf": Path, "quarter": "Q2_2026", "report_date": str,
         "form": str, "accession": str, "url": str, "landed": bool}
    """
    if not isinstance(ticker, str) or ticker.isdigit():
        raise ValueError("queue_10q needs a ticker symbol for file "
                         f"naming, got {ticker!r}")
    queue_dir = Path(queue_dir)
    queue_dir.mkdir(parents=True, exist_ok=True)
    writer = pdf_writer or _default_pdf_writer
    filings = fetch_10q_filings(ticker, since=since, http_get=http_get,
                                user_agent=user_agent, timeout=timeout,
                                use_cache=use_cache, refresh=refresh)
    out: List[Dict[str, Any]] = []
    for e in filings:
        tag = quarter_tag(e["report_date"])
        pdf = queue_dir / f"{ticker.upper()}_{tag}_10Q.pdf"
        rec = {"pdf": pdf, "quarter": tag, "report_date": e["report_date"],
               "form": e["form"], "accession": e["accession"],
               "url": e["url"], "landed": False}
        if pdf.exists() and not refresh:
            out.append(rec)
            continue
        html = _fetch_text(e["url"], http_get_text=http_get_text,
                           user_agent=user_agent, timeout=timeout)
        pages = exhibit_to_pages(html, max_chars=max_chars)
        header = [f"{ticker.upper()} {tag} Form {e['form']} "
                  f"(filed {e['date']:%Y-%m-%d}, "
                  f"period {e['report_date']})",
                  f"source: {e['url']}", ""]
        writer("\n\n".join(pages), pdf, header)
        rec["landed"] = True
        out.append(rec)
    return out


def digest_10q(filings: List[dict], backend: Callable, *,
               queue_dir: Path, cache_dir: Optional[Path] = None,
               workers: int = 1) -> Dict[str, Any]:
    """Digest the landed queue PDFs through the standard channel.

    Thin orchestration over
    :func:`revenue_model.llm_digest.digest_document` — the per-page
    cache makes it resumable; pass only the filings you want billed
    (e.g. ``filings[-1:]`` for the latest quarter).
    """
    from .llm_digest import digest_document

    if cache_dir is None:
        cache_dir = Path(queue_dir) / "digest_cache"
    out: Dict[str, Any] = {"cards": [], "voided": [], "documents": {}}
    for e in filings:
        r = digest_document(Path(e["pdf"]), backend, cache_dir=cache_dir,
                            workers=workers)
        out["cards"].extend(r["cards"])
        out["voided"].extend(r["voided"])
        out["documents"][Path(e["pdf"]).name] = {
            "pages": r["pages"], "cached": r["cached_pages"],
            "cards": len(r["cards"]), "voided": len(r["voided"])}
    return out


def _to_cached(e: Dict[str, Any]) -> dict:
    return {**e, "date": e["date"].strftime("%Y-%m-%d %H:%M:%S")}


def _from_cached(d: dict) -> Dict[str, Any]:
    return {**d, "date": datetime.strptime(d["date"], "%Y-%m-%d %H:%M:%S")}
