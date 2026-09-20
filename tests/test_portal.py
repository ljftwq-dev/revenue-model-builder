"""Tests for revenue_model.portal (Gate H local portal v1).

fastapi/httpx are behind the [portal] extra — skip the whole module
where they are absent (CI without extras must stay green).
"""

import json

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")            # TestClient transport

from fastapi.testclient import TestClient  # noqa: E402

from revenue_model.portal import create_app  # noqa: E402


# ---------------------------------------------------------------------------
# fixtures: a tiny workspace + injectable news transports
# ---------------------------------------------------------------------------

PAGE = ("The Pentagon plans to expand the Maven Smart System program "
        "with Palantir. The FY27 budget request includes $1.5 billion "
        "for the effort." + " filler " * 60)


def fake_fetch(url):
    if "paywalled" in url:
        raise ValueError("403 paywall")
    return {"title": "DoD expands Maven", "text": PAGE}


def fake_digest(text, url, seg):
    return [{"clue": "FY27 预算 15 亿美元扩大 Maven",
             "quote": "budget request includes $1.5 billion",
             "ring": "updown", "segment": seg or "US_Gov"}]


def make_client(tmp_path, *, zhipu_key=None):
    app = create_app(tmp_path / "ws", zhipu_key=zhipu_key,
                     fetch_fn=fake_fetch, digest_fn=fake_digest)
    return TestClient(app), tmp_path / "ws"


def test_stats_and_empty_queue(tmp_path):
    client, ws = make_client(tmp_path)
    r = client.get("/api/stats").json()
    assert r["queue_pdfs"] == 0 and r["user_files"] == 0
    assert r["filing_cards"] == 0
    assert r["url_submit_enabled"] is True       # digest_fn injected
    assert client.get("/api/queue").json() == []
    assert client.get("/").status_code == 200    # the single page ships


def test_file_upload_lands_in_user_submitted_with_ledger(tmp_path):
    client, ws = make_client(tmp_path)
    data = b"%PDF-1.4 fake earnings pdf"
    r1 = client.post("/api/submit/file",
                     files={"upload": ("PLTR_fake.pdf", data, "application/pdf")}).json()
    assert r1["status"] == "ok"
    saved = ws / "user_submitted" / r1["saved_as"]
    assert saved.exists() and saved.read_bytes() == data
    # shows up in queue browse + stats
    q = client.get("/api/queue").json()
    assert any(row["name"] == saved.name and row["where"] == "user" for row in q)
    assert client.get("/api/stats").json()["user_files"] == 1
    # the ledger recorded it
    led = client.get("/api/ledger").json()
    assert led[0]["kind"] == "upload" and led[0]["status"] == "ok"


def test_file_upload_duplicate_rejected_by_bytes(tmp_path):
    client, ws = make_client(tmp_path)
    data = b"%PDF-1.4 same bytes everywhere"
    r1 = client.post("/api/submit/file",
                     files={"upload": ("a.pdf", data, "application/pdf")}).json()
    r2 = client.post("/api/submit/file",
                     files={"upload": ("b.pdf", data, "application/pdf")}).json()
    assert r1["status"] == "ok" and r2["status"] == "duplicate"
    assert "a.pdf" in r2["reason"]
    # duplicate did NOT land a second file
    assert len(list((ws / "user_submitted").iterdir())) == 1
    led = client.get("/api/ledger").json()
    assert [row["status"] for row in led] == ["duplicate", "ok"]


def test_upload_name_sanitized(tmp_path):
    client, _ = make_client(tmp_path)
    r = client.post("/api/submit/file", files={
        "upload": ("../../evil<>:name.pdf", b"x-data", "application/pdf")}).json()
    assert r["status"] == "ok"
    assert "/" not in r["saved_as"] and "\\" not in r["saved_as"]
    assert "<" not in r["saved_as"]


def test_url_submit_rides_news_pipeline_and_is_idempotent(tmp_path):
    client, ws = make_client(tmp_path)
    url = "https://defensescoop.com/maven-portal-test"
    r1 = client.post("/api/submit/url", json={"url": url,
                                              "segment": "US_Gov"}).json()
    assert r1["status"] == "ok" and r1["cards"] == 1
    cache_hits = list((ws / "news_cache").glob("*.json"))
    assert len(cache_hits) == 1
    payload = json.loads(cache_hits[0].read_text(encoding="utf-8"))
    assert payload["url"] == url and payload["raw"]
    # second submit of the same URL: cached, zero new work
    r2 = client.post("/api/submit/url", json={"url": url}).json()
    assert r2["status"] == "duplicate" and r2["cards"] == 1
    # the card is browsable through /api/cards
    cards = client.get("/api/cards", params={"segment": "US_Gov"}).json()
    assert any(c["url"] == url and c["verified"] for c in cards)
    assert cards[0]["anchor"].endswith("·p1")


def test_url_submit_uncovered_is_negative_cached(tmp_path):
    client, ws = make_client(tmp_path)
    r = client.post("/api/submit/url",
                    json={"url": "https://paywalled-daily.com/x"}).json()
    assert r["status"] == "uncovered"
    assert "paywall" in r["reason"] or "403" in r["reason"]
    led = client.get("/api/ledger").json()
    assert led[0]["status"] == "uncovered"


def test_url_submit_without_key_returns_clear_error(tmp_path):
    app = create_app(tmp_path / "ws", zhipu_key=None,
                     fetch_fn=fake_fetch, digest_fn=None)
    client = TestClient(app)
    r = client.post("/api/submit/url", json={"url": "https://x.com/a"}).json()
    assert r["status"] == "error"
    assert "ZHIPU_API_KEY" in r["reason"]


def test_cards_endpoint_filters(tmp_path):
    client, _ = make_client(tmp_path)
    client.post("/api/submit/url",
                json={"url": "https://defensescoop.com/maven-f1"})
    only = client.get("/api/cards", params={"ring": "core"}).json()
    assert only == []                             # the card is updown
    hit = client.get("/api/cards", params={"grep": "Maven"}).json()
    assert len(hit) == 1
    miss = client.get("/api/cards", params={"grep": "Nvidia"}).json()
    assert miss == []
