"""webcast — earnings-call webcasts into the digest channel, automated.

Codifies the 2026-09-19 manual drill (CEG on Notified) next to the
original YouTube path (PLTR). Four resumable stages — whatever is
already on disk is skipped:

    acquire    player URL -> audio file
               - YouTube/others: yt-dlp directly
               - Notified (edge.media-server.com): headless Playwright
                 walks the registration door + cookie banner and sniffs
                 the AES-128 HLS playlist out of the network log; yt-dlp
                 then downloads and decrypts
    transcribe faster-whisper (GPU first, CPU int8 fallback)
    pdf        transcript -> text-layer PDF into the workspace queue
    digest     the standard per-page digest + verbatim-verify channel

Identity policy: registration forms are only ever filled from an
explicit profile (CLI flags or WEBCAST_FIRST_NAME / WEBCAST_LAST_NAME /
WEBCAST_EMAIL / WEBCAST_COMPANY env vars). No profile + a form in the
way -> the run stops with a clear message; the program never invents an
identity. Platforms the dance cannot pass (CAPTCHA, SSO, DRM) raise
WebcastDoorError — the honest hand-off boundary stays for those.

Extras: [webcast] (playwright, yt-dlp), [asr] (faster-whisper), [pdf].
"""
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

COOKIE_BUTTON_TEXTS = (
    "接受所有 Cookie", "接受所有", "Accept All Cookies", "Accept All",
    "Allow All", "接受", "同意", "Agree",
)
FORM_FIELD_LABELS = (
    ("first", re.compile(r"first\s*name", re.I)),
    ("last", re.compile(r"last\s*name", re.I)),
    ("email", re.compile(r"e-?mail", re.I)),
    ("company", re.compile(r"company|organization|organisation", re.I)),
)


class WebcastDoorError(RuntimeError):
    """The player could not be passed automatically (no profile given,
    a form/CAPTCHA in the way, or no stream appeared)."""


@dataclass(frozen=True)
class WebcastProfile:
    """Registration identity — explicitly provided, never invented."""
    first: str
    last: str
    email: str
    company: str

    @classmethod
    def from_env(cls) -> Optional["WebcastProfile"]:
        vals = [os.environ.get(f"WEBCAST_{k}") for k in
                ("FIRST_NAME", "LAST_NAME", "EMAIL", "COMPANY")]
        if all(vals):
            return cls(*vals)
        if any(vals):
            missing = [k for k, v in zip(
                ("FIRST_NAME", "LAST_NAME", "EMAIL", "COMPANY"), vals)
                if not v]
            raise WebcastDoorError(
                f"partial WEBCAST_* identity in env; missing {missing}")
        return None


def pick_stream(urls: List[str]) -> Optional[str]:
    """First HLS playlist URL in a network log (pure, testable)."""
    for u in urls:
        if ".m3u8" in u:
            return u
    return None


def build_prompt(company: str, quarter: str, speakers: str = "",
                 terms: str = "") -> str:
    """The ASR initial prompt; company/quarter always present, the rest
    optional glossary from the caller."""
    parts = [f"{company} {quarter} earnings call."]
    if speakers:
        parts.append(f"Speakers: {speakers}.")
    if terms:
        parts.append(f"Terms: {terms}.")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# acquire
# ---------------------------------------------------------------------------

def notified_stream_url(player_url: str, *, profile: Optional[WebcastProfile],
                        headless: bool = True, timeout_s: int = 90,
                        launch: Optional[Callable] = None) -> str:
    """Headless Playwright through the Notified door -> the .m3u8 URL.

    ``launch`` is injectable for tests (default: sync_playwright chromium).
    Raises WebcastDoorError on a form without a profile, on a CAPTCHA-
    looking page, or when no playlist shows up within ``timeout_s``.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit("acquire needs the [webcast] extra: "
                         "pip install revenue-model-builder[webcast]") from exc
    captured: List[str] = []

    def _record(urls: List[str]) -> None:          # test seam
        captured.extend(urls)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        try:
            page = browser.new_page()
            page.on("response", lambda r: captured.append(r.url))
            page.goto(player_url, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)          # OneTrust banner loads late
            _dismiss_cookies(page)
            _fill_door(page, profile)
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                got = pick_stream(captured)
                if got:
                    return got
                _try_play(page)          # headless players need a nudge
                page.wait_for_timeout(1000)
            tail = "\n".join(f"  {u[:110]}" for u in captured[-8:])
            raise WebcastDoorError(
                f"no .m3u8 within {timeout_s}s at {player_url} "
                f"({len(captured)} requests seen); last:\n{tail}")
        finally:
            browser.close()


def _try_play(page) -> None:
    """Best-effort play-button nudge: headed players auto-start, headless
    ones often wait for a gesture. Anchored names so cookie-center
    buttons ('Cookie 设置' etc.) can never match; errors swallowed."""
    try:
        loc = page.get_by_role(
            "button", name=re.compile(r"^(play|replay|listen|播放)", re.I))
        if loc.count():
            loc.first.click(timeout=1500)
            return
    except Exception:                                   # noqa: BLE001
        pass
    try:
        loc = page.locator(".theo-playbutton, .vjs-big-play-button, "
                           "button.play")
        if loc.count():
            loc.first.click(timeout=1500)
    except Exception:                                   # noqa: BLE001
        pass


def _dismiss_cookies(page, *, tries: int = 5) -> None:
    """Close the OneTrust-style banner, retrying: the banner mounts
    asynchronously, so a single early pass reliably misses it — and a
    banner left open swallows every later click."""
    for _ in range(tries):
        gone = True
        for text in COOKIE_BUTTON_TEXTS:
            try:
                btn = page.get_by_role("button", name=text)
                if btn.count():
                    gone = False
                    btn.first.click(timeout=2000)
                    page.wait_for_timeout(1500)
                    break
            except Exception:                           # noqa: BLE001
                continue
        if gone:
            return


def _fill_door(page, profile: Optional[WebcastProfile]) -> None:
    boxes = {}
    for key, pattern in FORM_FIELD_LABELS:
        try:
            loc = page.get_by_label(pattern)
            if loc.count():
                boxes[key] = loc.first
        except Exception:                               # noqa: BLE001
            continue
    if not boxes:
        return                                          # no form in the way
    if profile is None:
        raise WebcastDoorError(
            "a registration form blocks the player and no WEBCAST_* "
            "identity was provided — rerun with --register-* flags "
            "or the WEBCAST_FIRST_NAME/LAST_NAME/EMAIL/COMPANY env vars")
    if "first" in boxes:
        boxes["first"].fill(profile.first)
    if "last" in boxes:
        boxes["last"].fill(profile.last)
    if "email" in boxes:
        boxes["email"].fill(profile.email)
    if "company" in boxes:
        boxes["company"].fill(profile.company)
    try:
        page.get_by_role("button", name=re.compile(
            r"^(submit|register|continue|log.?in)$", re.I)).first.click(
            timeout=3000)
        page.wait_for_timeout(2000)
    except Exception as exc:                            # noqa: BLE001
        raise WebcastDoorError(f"form submit failed: {exc}") from exc


def download_audio(url: str, dest: Path, *, ydl_factory: Optional[Callable]
                   = None) -> Path:
    """yt-dlp (library API) to ``dest``. Format ladder covers both the
    YouTube case (bestaudio) and generic single-format HLS (id ``0``,
    seen on Notified)."""
    if ydl_factory is None:
        def ydl_factory(opts):                          # noqa: F811
            from yt_dlp import YoutubeDL
            return YoutubeDL(opts)
    opts = {
        "format": "0/bestaudio/best",
        "outtmpl": str(dest),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    with ydl_factory(opts) as ydl:
        ydl.download([url])
    if not dest.exists():
        raise FileNotFoundError(f"yt-dlp reported success but {dest} missing")
    return dest


def acquire(player_url: str, dest: Path, *,
            profile: Optional[WebcastProfile] = None) -> Path:
    """Player URL (YouTube or Notified) -> audio file on disk."""
    if "media-server.com" in player_url:
        stream = notified_stream_url(player_url, profile=profile)
        print(f"[acquire] stream: {stream}", flush=True)
        return download_audio(stream, dest)
    return download_audio(player_url, dest)


# ---------------------------------------------------------------------------
# transcribe / pdf
# ---------------------------------------------------------------------------

def transcribe(audio: Path, out_txt: Path, *, initial_prompt: str,
               model_factory: Optional[Callable] = None) -> Path:
    """faster-whisper medium -> timestamped transcript txt + json."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SystemExit("transcribe needs faster-whisper: "
                         "pip install faster-whisper") from exc

    def _default_factory():
        try:
            return WhisperModel("medium", device="cuda",
                                compute_type="float16")
        except Exception:                               # noqa: BLE001
            return WhisperModel("medium", device="cpu",
                                compute_type="int8")

    factory = model_factory or _default_factory
    model = factory()
    t0 = time.time()
    segments, info = model.transcribe(str(audio), language="en",
                                      beam_size=5, vad_filter=True,
                                      initial_prompt=initial_prompt)
    segs, lines = [], [f"# {out_txt.stem} 转写", ""]
    for s in segments:
        segs.append({"start": s.start, "end": s.end, "text": s.text.strip()})
        lines.append(f"[{_fmt(s.start)}] {s.text.strip()}")
    out_txt.write_text("\n".join(lines), encoding="utf-8")
    out_txt.with_suffix(".json").write_text(
        __import__("json").dumps({"segments": segs,
                                  "duration": info.duration},
                                 ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"[asr] {time.time() - t0:.0f}s | {len(segs)} segments -> "
          f"{out_txt.name}", flush=True)
    return out_txt


def _fmt(s: float) -> str:
    m, s = divmod(float(s), 60)
    h, m = divmod(m, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:05.2f}"


def transcript_pdf(txt: Path, pdf: Path, *, header: List[str]) -> Path:
    """Timestamped transcript -> text-layer PDF (Helvetica wrap)."""
    import fitz  # lazy: PyMuPDF, [pdf] extra

    PAGE_W, PAGE_H, MARGIN = 595, 842, 50
    SIZE, LEAD, MAX_LINES = 9.5, 13, 54
    MAX_W = PAGE_W - 2 * MARGIN

    def wrap(text: str) -> List[str]:
        out, cur = [], ""
        for word in text.split(" "):
            trial = word if not cur else cur + " " + word
            if fitz.get_text_length(trial, fontname="helv",
                                    fontsize=SIZE) <= MAX_W:
                cur = trial
            else:
                out.append(cur)
                cur = word
        if cur:
            out.append(cur)
        return out

    lines: List[str] = []
    for h in header:
        lines += wrap(h) + [""]
    for raw in txt.read_text(encoding="utf-8").splitlines():
        lines += wrap(raw) or [""]
    doc = fitz.open()
    for i in range(0, len(lines), MAX_LINES):
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        for j, ln in enumerate(lines[i:i + MAX_LINES]):
            page.insert_text((MARGIN, MARGIN + 14 + j * LEAD), ln,
                             fontname="helv", fontsize=SIZE)
    doc.save(pdf)
    doc.close()
    print(f"[pdf] {pdf.name}", flush=True)
    return pdf


# ---------------------------------------------------------------------------
# digest
# ---------------------------------------------------------------------------

def digest_pdf(pdf: Path, queue_dir: Path, *, backend: Callable) -> dict:
    """The standard channel: per-page digest + verbatim verify + cache."""
    from .llm_digest import digest_document

    r = digest_document(pdf, backend, cache_dir=queue_dir / "digest_cache")
    print(f"[digest] {r['pages']} pages | cards {len(r['cards'])} | "
          f"voided {len(r['voided'])} | cached {r['cached_pages']}",
          flush=True)
    return r


def run(url: str, ticker: str, quarter: str, workspace: Path, *,
        profile: Optional[WebcastProfile] = None,
        speakers: str = "", terms: str = "",
        queue_name: str = "下载队列",
        skip_acquired: bool = False) -> dict:
    """The whole chain, resumable (each stage checks its output file)."""
    ws = Path(workspace)
    stage = ws / "webcast"
    stage.mkdir(parents=True, exist_ok=True)
    queue = ws / queue_name
    queue.mkdir(parents=True, exist_ok=True)
    audio = stage / f"{ticker}_{quarter}_call.mp4"
    txt = stage / f"{ticker}_{quarter}_call.whisper.txt"
    pdf = queue / f"{ticker}_{quarter}_Earnings_Call_Transcript.pdf"

    if not (audio.exists() and skip_acquired):
        acquire(url, audio, profile=profile)
    if not txt.exists():
        transcribe(audio, txt,
                   initial_prompt=build_prompt(ticker, quarter, speakers,
                                               terms))
    if not pdf.exists():
        transcript_pdf(txt, pdf, header=[
            f"{ticker} {quarter} Earnings Call - Full Transcript",
            f"Source: {url}",
            "Transcribed by faster-whisper medium; digest-verified "
            "verbatim per page."])
    key = os.environ.get("ZHIPU_API_KEY")
    if not key:
        raise SystemExit("digest needs ZHIPU_API_KEY in the environment")
    from .llm_digest import make_glm_backend
    return digest_pdf(pdf, queue, backend=make_glm_backend(
        model="glm-4-flash"))
