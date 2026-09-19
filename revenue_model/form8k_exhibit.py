"""form8k_exhibit — 8-K EX-99 exhibits into the digest/verify channel.

v0.22.1 news-layer extension. The press releases and shareholder letters
attached to 8-K filings (EX-99 exhibits on EDGAR) are *primary* sources —
the issuer's own regulatory disclosure, not second-hand reporting. This
adapter lists those exhibits for a ticker and runs each through the same
per-page digest + verbatim-verify machinery as queue PDFs
(:func:`revenue_model.llm_digest.digest_pages`), emitting cards with
``confidence="primary"`` so :func:`revenue_model.news_layer.grade_sources`
treats them as underlying documents.

Design (mirrors ``form8k_adapter``):
- **Pure stdlib** (``urllib`` + ``html.parser``). No SDK, no key.
- **Injectable getters** — ``http_get`` (JSON: submissions + filing
  index) and ``http_get_text`` (HTML: the exhibit itself) — for offline
  tests / CI.
- Filing-index listings cached per accession; the page-level digest
  cache lives in the caller's ``cache_dir`` exactly like PDF digests.
- HTML exhibits have no physical pages, so :func:`exhibit_to_pages`
  chunks the extracted text at line boundaries (~3.5k chars/page) —
  every quote is still verified verbatim inside its chunk.
"""
import json
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from . import cache, form8k_adapter, sec_adapter
from .llm_digest import digest_pages

DEFAULT_UA = sec_adapter.DEFAULT_UA
_ARCHIVES_INDEX = ("https://www.sec.gov/Archives/edgar/data/{cik}/{nod}/"
                   "index.json")

#: lowercase filename fragments identifying an EX-99 exhibit (observed
#: patterns: ``a2023q2ex991pressrelease.htm``, ``d259921dex991.htm``,
#: ``a2022q3exhibit992ceoletter.htm``). Procedural files (index pages,
#: R*.htm financial renders) never match.
_EXHIBIT_HINTS = ("ex99", "ex-99", "ex_99",
                  "exhibit99", "exhibit-99", "exhibit_99")

_SKIP_NAMES = ("index", "header")

#: exhibit text chunk size fed to the digest channel, in characters
DEFAULT_PAGE_CHARS = 3500


def _is_exhibit(name: str) -> bool:
    low = name.lower()
    if not low.endswith((".htm", ".html")):
        return False
    if any(s in low for s in _SKIP_NAMES):
        return False
    return any(h in low for h in _EXHIBIT_HINTS)


def _resolve_cik(ticker_or_cik: Union[str, int], *, http_get: Optional[Callable],
                 user_agent: str, timeout: int, use_cache: bool,
                 refresh: bool) -> int:
    if isinstance(ticker_or_cik, int):
        return ticker_or_cik
    cik, _title = sec_adapter.fetch_cik(ticker_or_cik, http_get=http_get,
                                        user_agent=user_agent,
                                        timeout=timeout, use_cache=use_cache,
                                        refresh=refresh)
    return cik


def _fetch_json(url: str, *, http_get: Optional[Callable], user_agent: str,
                timeout: int) -> dict:
    if http_get is not None:
        return http_get(url, timeout)
    req = urllib.request.Request(url, headers={"User-Agent": user_agent,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _fetch_text(url: str, *, http_get_text: Optional[Callable],
                user_agent: str, timeout: int) -> str:
    if http_get_text is not None:
        return http_get_text(url, timeout)
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


class _TextExtractor(HTMLParser):
    """HTML -> visible text, newline per block element (script/style
    dropped). Sufficient for EDGAR exhibit plain-prose press releases."""

    _BLOCKS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5",
               "h6", "table", "blockquote"}
    _DROP = {"script", "style"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._lines: List[str] = []
        self._buf: List[str] = []
        self._drop_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._DROP:
            self._drop_depth += 1
        elif tag in self._BLOCKS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in self._DROP and self._drop_depth:
            self._drop_depth -= 1
        elif tag in self._BLOCKS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._drop_depth:
            return
        self._buf.append(data)

    def _flush(self) -> None:
        line = "".join(self._buf)
        self._buf = []
        if line.strip():
            self._lines.append(" ".join(line.split()))

    def text_lines(self) -> List[str]:
        self._flush()
        return self._lines


def exhibit_to_pages(html: str, *, max_chars: int = DEFAULT_PAGE_CHARS
                     ) -> List[str]:
    """Exhibit HTML -> page texts (~``max_chars`` chunks at line
    boundaries). The backend quotes verbatim from the page it sees, so
    chunking never breaks verification."""
    extractor = _TextExtractor()
    extractor.feed(html)
    extractor.close()
    pages: List[str] = []
    cur: List[str] = []
    size = 0
    for line in extractor.text_lines():
        if cur and size + len(line) + 1 > max_chars:
            pages.append("\n".join(cur))
            cur, size = [], 0
        cur.append(line)
        size += len(line) + 1
    if cur:
        pages.append("\n".join(cur))
    return pages


def fetch_8k_exhibits(ticker_or_cik: Union[str, int], *, since=None,
                      categories: Optional[List[str]] = None,
                      http_get: Optional[Callable] = None,
                      http_get_text: Optional[Callable] = None,
                      user_agent: str = DEFAULT_UA, timeout: int = 30,
                      use_cache: bool = True, refresh: bool = False
                      ) -> List[Dict[str, Any]]:
    """Ticker or CIK -> 8-K EX-99 exhibit documents, oldest-first.

    Returns a list of dicts, each::

        {"date": datetime, "category": str, "items": str, "form": "8-K",
         "accession": str, "file": str, "url": str}

    built on :func:`form8k_adapter.fetch_8k_events` (optionally filtered
    by ``categories``) plus the EDGAR filing index per accession. Filing
    index listings are cached per accession; injected getters bypass.
    """
    cik = _resolve_cik(ticker_or_cik, http_get=http_get, user_agent=user_agent,
                       timeout=timeout, use_cache=use_cache, refresh=refresh)
    events = form8k_adapter.fetch_8k_events(
        cik, since=since, http_get=http_get, user_agent=user_agent,
        timeout=timeout, use_cache=use_cache, refresh=refresh)
    if categories:
        wanted = set(categories)
        events = [e for e in events if e["category"] in wanted]

    cache_enabled = use_cache and http_get is None
    out: List[Dict[str, Any]] = []
    for ev in events:
        nod = ev["accession"].replace("-", "")
        key = cache.cache_key("form8k_exhibit_idx", cik, nod)
        listing = None
        if cache_enabled:
            hit, cached = cache.cache_get(key, refresh)
            if hit:
                listing = cached
        if listing is None:
            idx = _fetch_json(_ARCHIVES_INDEX.format(cik=cik, nod=nod),
                              http_get=http_get, user_agent=user_agent,
                              timeout=timeout)
            listing = [i["name"] for i in
                       idx.get("directory", {}).get("item", [])
                       if _is_exhibit(i.get("name", ""))]
            if cache_enabled:
                cache.cache_set(key, listing)
        for name in listing:
            out.append({**ev, "file": name,
                        "url": (f"https://www.sec.gov/Archives/edgar/data/"
                                f"{cik}/{nod}/{name}")})
    return out


def digest_8k_exhibits(ticker_or_cik: Union[str, int],
                       backend: Callable,
                       *, cache_dir: Optional[Path] = None,
                       since=None, categories: Optional[List[str]] = None,
                       max_chars: int = DEFAULT_PAGE_CHARS, workers: int = 1,
                       http_get: Optional[Callable] = None,
                       http_get_text: Optional[Callable] = None,
                       user_agent: str = DEFAULT_UA, timeout: int = 30,
                       use_cache: bool = True, refresh: bool = False
                       ) -> Dict[str, Any]:
    """Digest every 8-K EX-99 exhibit through the standard channel.

    Returns the :func:`digest_pages` aggregate — ``cards`` (all
    ``confidence="primary"``), ``voided``, ``documents`` per exhibit
    (pages / cached / cards / voided), plus ``exhibits`` count.
    """
    from dataclasses import replace

    exhibits = fetch_8k_exhibits(
        ticker_or_cik, since=since, categories=categories,
        http_get=http_get, http_get_text=http_get_text,
        user_agent=user_agent, timeout=timeout, use_cache=use_cache,
        refresh=refresh)
    out: Dict[str, Any] = {"cards": [], "voided": [], "documents": {},
                           "exhibits": 0}
    for ex in exhibits:
        nod = ex["accession"].replace("-", "")
        stem = f"8K_{nod}_{Path(ex['file']).stem}"
        file_name = f"{stem}.htm"
        try:
            html = _fetch_text(ex["url"], http_get_text=http_get_text,
                               user_agent=user_agent, timeout=timeout)
            pages = exhibit_to_pages(html, max_chars=max_chars)
        except Exception as exc:
            out["voided"].append({"exhibit": file_name,
                                  "error": f"{type(exc).__name__}: {exc}"})
            continue
        r = digest_pages(pages, file_name, backend, cache_dir=cache_dir,
                         cache_stem=stem, workers=workers)
        out["cards"].extend(replace(c, confidence="primary")
                            for c in r["cards"])
        out["voided"].extend(r["voided"])
        out["documents"][file_name] = {
            "pages": r["pages"], "cached": r["cached_pages"],
            "cards": len(r["cards"]), "voided": len(r["voided"]),
            "category": ex["category"], "date": ex["date"]}
        out["exhibits"] += 1
    return out
