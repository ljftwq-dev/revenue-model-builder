"""cache.py tests — uses a tmp RMB_CACHE_DIR so the home cache is never touched."""
import pytest

from revenue_model import cache


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("RMB_CACHE_DIR", str(tmp_path))
    return tmp_path


def test_get_cache_dir_override(tmp_cache):
    assert cache.get_cache_dir() == tmp_cache


def test_cache_roundtrip(tmp_cache):
    cache.cache_set("sec_NVDA", {"2025": 130497.0, "2026": 215938.0})
    hit, data = cache.cache_get("sec_NVDA")
    assert hit is True
    assert data["2026"] == 215938.0


def test_cache_miss(tmp_cache):
    hit, data = cache.cache_get("nonexistent")
    assert hit is False
    assert data is None


def test_refresh_forces_miss(tmp_cache):
    cache.cache_set("k", {"v": 1})
    hit, _ = cache.cache_get("k", refresh=True)
    assert hit is False


def test_cache_key_short(tmp_cache):
    assert cache.cache_key("sec", "NVDA") == "sec_NVDA"


def test_cache_key_long_url_hashes(tmp_cache):
    url = ("https://s201.q4cdn.com/141608511/files/doc_financials/2027/Q127/"
           "Rev_by_Mkt_Qtrly_Trend_Q127-NEW-v3.pdf")
    k = cache.cache_key("q4cdn", url)
    assert k.startswith("q4cdn_")
    assert len(k) < 30  # hashed, short
    assert k == cache.cache_key("q4cdn", url)  # deterministic


def test_invalid_cache_treated_as_miss(tmp_cache):
    p = cache.get_cache_dir() / "bad.json"
    p.write_text("{not valid json", encoding="utf-8")
    hit, data = cache.cache_get("bad")
    assert hit is False
    assert data is None
