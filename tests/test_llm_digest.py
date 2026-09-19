"""Tests for revenue_model.llm_digest — page extraction, backends,
verification, page cache. All offline (injected backend)."""
import json
from pathlib import Path

import pytest

from revenue_model.llm_digest import (
    GLM_CODING_URL, GLM_PAAS_URL, MissingBackendError, digest_document,
    digest_pages, digest_queue, extract_pages, make_glm_backend,
)

PAGE_TEXT = ("Highlights. Revenue grew +93% Y/Y to $1.94 billion. "
             "US commercial revenue grew +149% Y/Y.")


def fake_backend(page_text: str, file_name: str, page_no: int):
    """Deterministic backend: one true card, one hallucinated card."""
    if page_no != 4:
        return []
    return [
        {"clue": "record quarter", "quote": "Revenue grew +93% Y/Y",
         "ring": "core", "segment": ""},
        {"clue": "hallucinated", "quote": "CFO promised 200% growth",
         "ring": "self", "segment": ""},
        {"clue": "bad shape: no quote"},
    ]


def _make_pdf(tmp_path: Path) -> Path:
    import fitz

    doc = fitz.open()
    for i in range(1, 6):
        page = doc.new_page()
        text = PAGE_TEXT if i == 4 else f"filler page {i}"
        page.insert_text((72, 72), text)
    p = tmp_path / "demo.pdf"
    doc.save(str(p))
    doc.close()
    return p


@pytest.fixture()
def pdf(tmp_path):
    return _make_pdf(tmp_path)


class TestExtract:
    def test_pages_extracted_in_order(self, pdf):
        pages = extract_pages(pdf)
        assert len(pages) == 5
        assert "Revenue grew" in pages[3]


class TestDigestDocument:
    def test_true_card_kept_hallucination_voided(self, pdf):
        r = digest_document(pdf, fake_backend)
        assert len(r["cards"]) == 1
        assert r["cards"][0].verified
        assert r["cards"][0].anchor_page == 4
        voids = r["voided"]
        assert any("quote_not_found" in v for v in voids)   # hallucinated
        assert any("candidate" in v for v in voids)         # malformed

    def test_page_cache_second_run_all_cached(self, pdf, tmp_path):
        cache = tmp_path / "digest_cache"
        digest_document(pdf, fake_backend, cache_dir=cache)
        r2 = digest_document(pdf, fake_backend, cache_dir=cache)
        assert r2["cached_pages"] == r2["pages"]
        assert len(r2["cards"]) == 1                         # same result

    def test_backend_failure_voids_page_not_run(self, pdf):
        def boom(text, name, page):
            raise RuntimeError("model down")
        r = digest_document(pdf, boom)
        assert r["cards"] == []
        assert all("error" in v for v in r["voided"])


class TestDigestQueue:
    def test_queue_digests_all_pdfs(self, tmp_path):
        _make_pdf(tmp_path)
        # second pdf with a different name
        import shutil
        shutil.copy(tmp_path / "demo.pdf", tmp_path / "demo2.pdf")
        r = digest_queue(tmp_path, fake_backend)
        assert set(r["documents"]) == {"demo.pdf", "demo2.pdf"}
        assert len(r["cards"]) == 2

    def test_parallel_workers_same_result(self, pdf, tmp_path):
        r1 = digest_document(pdf, fake_backend, cache_dir=tmp_path / "c1")
        r2 = digest_document(pdf, fake_backend, cache_dir=tmp_path / "c2",
                            workers=3)
        assert len(r1["cards"]) == len(r2["cards"]) == 1
        assert r1["voided"] and r2["voided"]


class TestMissingBackend:
    def test_message_is_a_gate_question(self):
        err = MissingBackendError()
        assert "find yourself a PDF-reading model" in str(err)
        assert "--resume" in str(err)


class TestMakeGlmBackend:
    """base_url / endpoint selection (v0.22.1 tiered digest), offline via
    a monkeypatched urlopen that captures the request URL."""

    @staticmethod
    def _run_backend(monkeypatch, base_url):
        import urllib.request

        captured = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": "[]"}}]}).encode()

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            return FakeResp()

        monkeypatch.setenv("ZHIPU_API_KEY", "test-key")
        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        backend = make_glm_backend(base_url=base_url)
        assert backend("page text", "f.pdf", 1) == []
        return captured["url"]

    def test_default_endpoint_is_paas(self, monkeypatch):
        url = self._run_backend(monkeypatch, None)
        assert url == GLM_PAAS_URL

    def test_coding_endpoint_selected(self, monkeypatch):
        url = self._run_backend(monkeypatch, GLM_CODING_URL)
        assert url == GLM_CODING_URL
        assert "coding" in url

    def test_constants(self):
        assert GLM_PAAS_URL.endswith("/paas/v4/chat/completions")
        assert GLM_CODING_URL.endswith("/coding/paas/v4/chat/completions")


class TestDigestPages:
    """the endpoint-agnostic core: non-PDF page texts ride the same
    verify/cache machinery (used by form8k_exhibit)."""

    def test_pages_digest_without_pdf(self):
        pages = ["filler", "filler", "filler", PAGE_TEXT]
        r = digest_pages(pages, "exhibit.htm", fake_backend)
        assert len(r["cards"]) == 1
        assert r["cards"][0].anchor_file == "exhibit.htm"
        assert r["cards"][0].anchor_page == 4
        assert r["cards"][0].verified

    def test_cache_stem_namespaces_entries(self, tmp_path):
        pages = [PAGE_TEXT]
        digest_pages(pages, "exhibit.htm", fake_backend,
                     cache_dir=tmp_path, cache_stem="custom")
        assert (tmp_path / "custom_p1.json").exists()
        r2 = digest_pages(pages, "exhibit.htm", fake_backend,
                          cache_dir=tmp_path, cache_stem="custom")
        assert r2["cached_pages"] == 1

