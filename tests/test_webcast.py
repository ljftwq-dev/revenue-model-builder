"""Tests for revenue_model.webcast (pure parts; the Playwright dance and
ASR are injectable seams exercised live, not in CI)."""

from pathlib import Path

import pytest

from revenue_model.webcast import (
    WebcastDoorError,
    WebcastProfile,
    build_prompt,
    download_audio,
    pick_stream,
    transcript_pdf,
)


class TestPickStream:
    def test_first_m3u8_wins(self):
        urls = ["https://x/1.js", "https://m/a.m3u8", "https://m/b.m3u8"]
        assert pick_stream(urls) == "https://m/a.m3u8"

    def test_none_when_absent(self):
        assert pick_stream(["https://x/1.ts", "https://x/2.key"]) is None
        assert pick_stream([]) is None


class TestProfile:
    def test_from_env_roundtrip(self, monkeypatch):
        for k, v in (("WEBCAST_FIRST_NAME", "Jiafeng"),
                     ("WEBCAST_LAST_NAME", "Li"),
                     ("WEBCAST_EMAIL", "jiafeng4@illinois.edu"),
                     ("WEBCAST_COMPANY", "University of Illinois")):
            monkeypatch.setenv(k, v)
        p = WebcastProfile.from_env()
        assert p.first == "Jiafeng" and p.email.endswith("illinois.edu")

    def test_none_when_env_empty(self, monkeypatch):
        for k in ("WEBCAST_FIRST_NAME", "WEBCAST_LAST_NAME",
                  "WEBCAST_EMAIL", "WEBCAST_COMPANY"):
            monkeypatch.delenv(k, raising=False)
        assert WebcastProfile.from_env() is None

    def test_partial_env_raises(self, monkeypatch):
        monkeypatch.setenv("WEBCAST_EMAIL", "x@y.z")
        monkeypatch.delenv("WEBCAST_FIRST_NAME", raising=False)
        monkeypatch.delenv("WEBCAST_LAST_NAME", raising=False)
        monkeypatch.delenv("WEBCAST_COMPANY", raising=False)
        with pytest.raises(WebcastDoorError, match="partial"):
            WebcastProfile.from_env()


class TestBuildPrompt:
    def test_minimum_and_full(self):
        p = build_prompt("CEG", "Q2_2026")
        assert p == "CEG Q2_2026 earnings call."
        p2 = build_prompt("CEG", "Q2_2026", speakers="A (CEO), B (CFO)",
                          terms="Calpine, PJM")
        assert "Speakers: A (CEO), B (CFO)." in p2
        assert "Terms: Calpine, PJM." in p2


class TestDownloadAudio:
    def test_opts_and_success(self, tmp_path):
        seen = {}

        class FakeYDL:
            def __init__(self, opts):
                seen["opts"] = opts

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def download(self, urls):
                assert urls == ["https://m/a.m3u8"]
                Path(seen["opts"]["outtmpl"]).write_bytes(b"audio")

        dest = tmp_path / "call.mp4"
        out = download_audio("https://m/a.m3u8", dest,
                             ydl_factory=lambda o: FakeYDL(o))
        assert out == dest and dest.exists()
        # format ladder covers both Notified single-format (id 0) and YouTube
        assert seen["opts"]["format"] == "0/bestaudio/best"
        assert seen["opts"]["noplaylist"] is True

    def test_missing_output_raises(self, tmp_path):
        class FakeYDL:
            def __init__(self, opts):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def download(self, urls):
                return                      # claims success, writes nothing

        with pytest.raises(FileNotFoundError):
            download_audio("https://m/a.m3u8", tmp_path / "x.mp4",
                           ydl_factory=lambda o: FakeYDL(o))


class TestTranscriptPdf:
    def test_roundtrip_text_layer(self, tmp_path):
        fitz = pytest.importorskip("fitz")     # [pdf] extra in CI
        txt = tmp_path / "t.txt"
        txt.write_text("[00:00:01.00] Hello from the earnings call.\n"
                       "[00:00:05.00] Second line of prepared remarks.\n"
                       "filler " * 400, encoding="utf-8")
        pdf = transcript_pdf(txt, tmp_path / "t.pdf",
                             header=["CEG Q2_2026 Earnings Call - Full "
                                     "Transcript"])
        doc = fitz.open(pdf)
        assert doc.page_count >= 1
        whole = "\n".join(p.get_text() for p in doc)
        assert "Hello from the earnings call." in whole     # text layer!
        assert "CEG Q2_2026 Earnings Call" in whole         # header kept
        doc.close()
