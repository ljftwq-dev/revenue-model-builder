"""Gate H portal (v1) — the local control desk for the human gate.

Local-first by design (clone-and-run; an open-source project should not
carry a server): FastAPI + a SQLite ledger + one inline single page,
bound to 127.0.0.1. What it does:

- browse the document queue (which PDFs are in, which are digested)
  and the verified evidence cards (filings + news, one filter box);
- hand documents to the machine: a file upload lands in
  ``user_submitted/`` with sha1 dedup against everything already in the
  workspace; a URL rides the SAME fetch -> digest -> verbatim-verify
  news path (``news_layer.digest_one_url`` — no shortcut around the
  hard gate; needs ZHIPU_API_KEY at serve time);
- keep an append-only submission ledger (报账核对: every hand-off is
  accounted for, duplicates included).

Needs the [portal] extra (fastapi + uvicorn); everything else is
stdlib. The queue directory defaults to the workspace convention
``下载队列`` (override with --queue-name for English workspaces).
"""
import hashlib
import re
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from fastapi import FastAPI, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

MAX_UPLOAD_BYTES = 60_000_000


def _sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _safe_name(name: str) -> str:
    """Keep the basename, strip path tricks and control characters."""
    base = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", Path(name).name).strip()
    return base or "unnamed"


class _Ledger:
    """Append-only submission log + dedup registry in workspace SQLite."""

    def __init__(self, db_path: Path):
        self.path = Path(db_path)
        with sqlite3.connect(self.path) as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS submissions ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "ts TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL, "
                "sha1 TEXT, status TEXT NOT NULL, detail TEXT)")

    def add(self, kind: str, name: str, sha1: str, status: str,
            detail: str = "") -> None:
        with sqlite3.connect(self.path) as con:
            con.execute("INSERT INTO submissions (ts, kind, name, sha1, "
                        "status, detail) VALUES (?, ?, ?, ?, ?, ?)",
                        (datetime.now().isoformat(timespec="seconds"), kind,
                         name, sha1, status, detail[:300]))

    def seen_sha1(self, sha1: str) -> bool:
        with sqlite3.connect(self.path) as con:
            row = con.execute("SELECT 1 FROM submissions WHERE sha1 = ? "
                              "AND status = 'ok' LIMIT 1", (sha1,)).fetchone()
        return row is not None

    def recent(self, limit: int = 50) -> List[dict]:
        with sqlite3.connect(self.path) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute("SELECT ts, kind, name, sha1, status, detail "
                               "FROM submissions ORDER BY id DESC LIMIT ?",
                               (limit,)).fetchall()
        return [dict(r) for r in rows]


class _KnownHashes:
    """Lazily hashed snapshot of on-disk documents (queue + user files)
    for upload dedup. Built once per app run; a local tool, not a
    service, so no invalidation protocol in v1."""

    def __init__(self, dirs: List[Path]):
        self.dirs = dirs
        self._map: Optional[Dict[str, str]] = None

    def _build(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for d in self.dirs:
            if not d.exists():
                continue
            for f in sorted(d.iterdir()):
                if f.is_file() and not f.name.startswith("."):
                    try:
                        out[_sha1_bytes(f.read_bytes())] = f.name
                    except OSError:
                        continue
        return out

    def find(self, sha1: str) -> Optional[str]:
        if self._map is None:
            self._map = self._build()
        return self._map.get(sha1)

    def add(self, sha1: str, name: str) -> None:
        """Register a file saved through the portal so the NEXT submit
        sees it (the lazy snapshot otherwise has a self-blindspot for
        files that landed after its one build)."""
        if self._map is None:
            self._map = self._build()
        self._map[sha1] = name


def create_app(workspace: Path, *, zhipu_key: Optional[str] = None,
               queue_name: str = "下载队列",
               fetch_fn: Optional[Callable] = None,
               digest_fn: Optional[Callable] = None) -> FastAPI:
    """Build the portal app. ``fetch_fn`` / ``digest_fn`` are injectable
    for tests; production defaults are the real article fetch and the
    cloud GLM news backend (which needs the zhipu key)."""
    workspace = Path(workspace)
    queue_dir = workspace / queue_name
    news_cache = workspace / "news_cache"
    user_dir = workspace / "user_submitted"
    for d in (queue_dir, news_cache, user_dir):
        d.mkdir(parents=True, exist_ok=True)
    ledger = _Ledger(workspace / "portal.db")
    known = _KnownHashes([queue_dir, user_dir])
    app = FastAPI(title="Gate H portal", version="1")
    app.state.zhipu_key = zhipu_key

    class UrlIn(BaseModel):
        url: str
        segment: str = ""

    def _queue_rows() -> List[dict]:
        rows = []
        for where, d in (("queue", queue_dir), ("user", user_dir)):
            for f in sorted(d.iterdir()) if d.exists() else []:
                if not f.is_file() or f.name.startswith(".") or f.suffix.lower() != ".pdf":
                    continue
                digested = (queue_dir / "digest_cache"
                            / f"{f.stem}_p1.json").exists()
                rows.append({"name": f.name, "where": where,
                             "size": f.stat().st_size,
                             "mtime": datetime.fromtimestamp(
                                 f.stat().st_mtime).isoformat(timespec="minutes"),
                             "digested": digested})
        return rows

    def _cards(ring: Optional[str], segment: Optional[str],
               grep: Optional[str], limit: int) -> List[dict]:
        from .chains_cli import filter_cards, load_queue_cards
        try:
            cards = load_queue_cards(queue_dir)
        except Exception:                                  # noqa: BLE001
            cards = []
        cards = filter_cards(cards, ring=ring, segment=segment, grep=grep)
        out = [asdict(c) for c in cards[:limit]]
        for c in out:
            c["anchor"] = f"{c.pop('anchor_file')}·p{c.pop('anchor_page')}"
        return out

    @app.get("/api/stats")
    def stats() -> dict:
        rows = _queue_rows()
        filings = news = 0
        try:
            from .chains_cli import load_queue_cards
            for c in load_queue_cards(queue_dir):
                if c.url:
                    news += 1
                else:
                    filings += 1
        except Exception:                                  # noqa: BLE001
            pass
        return {"queue_pdfs": sum(1 for r in rows if r["where"] == "queue"),
                "queue_digested": sum(1 for r in rows
                                      if r["where"] == "queue" and r["digested"]),
                "user_files": sum(1 for r in rows if r["where"] == "user"),
                "filing_cards": filings, "news_cards": news,
                "url_submit_enabled": bool(zhipu_key or digest_fn)}

    @app.get("/api/queue")
    def queue() -> List[dict]:
        return _queue_rows()

    @app.get("/api/cards")
    def cards(ring: str = None, segment: str = None, grep: str = None,
              limit: int = 500) -> List[dict]:
        return _cards(ring, segment, grep, limit)

    @app.post("/api/submit/url")
    def submit_url(body: UrlIn) -> dict:
        from .news_layer import digest_one_url
        if digest_fn is None and not zhipu_key:
            return {"status": "error", "cards": 0, "url": body.url,
                    "reason": "URL submit needs ZHIPU_API_KEY at serve "
                              "time (restart the portal with it set)"}
        fn = digest_fn
        if fn is None:
            from .news_layer import make_glm_news_backend
            fn = make_glm_news_backend(zhipu_key)
        r = digest_one_url(body.url.strip(), fetch_fn=fetch_fn,
                           digest_fn=fn, cache_dir=news_cache,
                           segment=body.segment)
        ledger.add("url", r["url"], "", r["status"], r["reason"])
        return r

    @app.post("/api/submit/file")
    async def submit_file(upload: UploadFile) -> dict:
        data = await upload.read()
        if len(data) > MAX_UPLOAD_BYTES:
            return {"status": "rejected", "reason": "file exceeds 60 MB"}
        sha1 = _sha1_bytes(data)
        name = _safe_name(upload.filename or "unnamed")
        dup = known.find(sha1)
        if dup is not None:
            ledger.add("upload", name, sha1, "duplicate",
                       f"same bytes as {dup}")
            return {"status": "duplicate", "reason":
                    f"same bytes already in workspace as {dup}", "sha1": sha1}
        if ledger.seen_sha1(sha1):
            ledger.add("upload", name, sha1, "duplicate",
                       "ledger says a prior ok upload had these bytes")
            return {"status": "duplicate", "reason":
                    "previously submitted (ledger)", "sha1": sha1}
        dest = user_dir / name
        i = 1
        while dest.exists():
            dest = user_dir / f"{Path(name).stem}_{i}{Path(name).suffix}"
            i += 1
        dest.write_bytes(data)
        known.add(sha1, dest.name)
        ledger.add("upload", dest.name, sha1, "ok", f"{len(data)} bytes")
        return {"status": "ok", "reason": "", "saved_as": dest.name,
                "sha1": sha1}

    @app.get("/api/ledger")
    def ledger_view(limit: int = 50) -> List[dict]:
        return ledger.recent(limit)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _PAGE

    return app


_PAGE = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>Gate H 门户</title><style>
 body{font-family:system-ui,'Microsoft YaHei',sans-serif;margin:0;background:#f6f7f9;color:#1c2430}
 header{background:#152238;color:#fff;padding:14px 22px}
 header h1{font-size:18px;margin:0} header span{opacity:.65;font-size:12px;margin-left:10px}
 nav{display:flex;gap:2px;background:#dde3ec;padding:0 22px}
 nav button{border:0;background:none;padding:10px 16px;font-size:14px;cursor:pointer;color:#445}
 nav button.on{background:#fff;font-weight:600;border-radius:6px 6px 0 0}
 main{padding:20px 24px;max-width:1100px}
 .stats{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:18px}
 .stat{background:#fff;border:1px solid #e3e7ee;border-radius:8px;padding:10px 12px}
 .stat b{display:block;font-size:22px} .stat i{font-style:normal;font-size:12px;color:#7a8699}
 table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e3e7ee;border-radius:8px}
 th,td{text-align:left;padding:7px 10px;border-bottom:1px solid #eef1f5;font-size:13px}
 th{background:#f0f3f8;font-size:12px;color:#556}
 .pill{display:inline-block;padding:1px 8px;border-radius:9px;font-size:11px}
 .ok{background:#e3f5e8;color:#19712f}.dup{background:#fdf3dc;color:#8a6100}
 .rej{background:#fde8e8;color:#9c2626}.unc{background:#e8eefb;color:#2a4d8f}
 .card{background:#fff;border:1px solid #e3e7ee;border-radius:8px;padding:12px 14px;margin-bottom:10px}
 .card .meta{font-size:11px;color:#7a8699;margin-bottom:4px}
 .card q{color:#333;font-size:12px}
 input,select{padding:7px 10px;border:1px solid #ccd4de;border-radius:6px;font-size:13px}
 button.act{padding:8px 16px;border:0;border-radius:6px;background:#2456c4;color:#fff;cursor:pointer}
 .hint{font-size:12px;color:#7a8699;margin-top:8px}
 .row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:10px 0}
</style></head><body>
<header><h1>Gate H 门户<span>本地控制台 · 提交落队列 · 报账核对</span></h1></header>
<nav>
 <button data-t="stats" class="on">概览</button><button data-t="queue">队列</button>
 <button data-t="cards">证据卡</button><button data-t="submit">提交</button>
 <button data-t="ledger">台账</button></nav>
<main id="main"><p>加载中…</p></main>
<script>
const main=document.getElementById('main');
const pill=s=>({ok:'<span class="pill ok">ok</span>',duplicate:'<span class="pill dup">重复件</span>',
 rejected:'<span class="pill rej">拒收</span>',uncovered:'<span class="pill unc">未覆盖</span>',
 error:'<span class="pill rej">error</span>'}[s]||s);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function jget(u){const r=await fetch(u);return r.json()}
function tabs(){document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>go(b.dataset.t))}
async function go(t){
 document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('on',b.dataset.t===t));
 if(t==='stats'){const s=await jget('/api/stats');
  main.innerHTML=`<div class="stats">${[['queue_pdfs','队列 PDF'],['queue_digested','已消化'],
   ['user_files','手工提交'],['filing_cards','文档卡'],['news_cards','新闻卡'],
   ['url_submit_enabled','URL 提交']].map(([k,l])=>
   `<div class="stat"><b>${esc(s[k])}</b><i>${l}</i></div>`).join('')}</div>
   <p class="hint">URL 提交需要服务端带 ZHIPU_API_KEY 启动；文件提交不需要。</p>`;}
 if(t==='queue'){const q=await jget('/api/queue');
  main.innerHTML=`<table><tr><th>文件</th><th>位置</th><th>大小</th><th>修改时间</th><th>消化</th></tr>
  ${q.map(r=>`<tr><td>${esc(r.name)}</td><td>${r.where==='queue'?'下载队列':'手工'}</td>
  <td>${(r.size/1048576).toFixed(1)} MB</td><td>${esc(r.mtime)}</td>
  <td>${r.digested?'✓':'—'}</td></tr>`).join('')}</table>`;}
 if(t==='cards'){main.innerHTML=`<div class="row">ring <select id="ring">
  <option value="">全部</option><option>core</option><option>self</option>
  <option>updown</option><option>macro</option></select>
  segment <input id="seg" size="10"> 关键词 <input id="grep" size="14">
  <button class="act" onclick="loadCards()">过滤</button></div><div id="clist"></div>`;
  window.loadCards=async()=>{const p=new URLSearchParams();
   const r=document.getElementById('ring').value,g=document.getElementById('grep').value,
   s=document.getElementById('seg').value;
   if(r)p.set('ring',r);if(g)p.set('grep',g);if(s)p.set('segment',s);
   const cs=await jget('/api/cards?'+p);
   document.getElementById('clist').innerHTML=cs.length?cs.map(c=>
   `<div class="card"><div class="meta">${esc(c.anchor)} · ${esc(c.ring)} · ${esc(c.segment||'公司级')}
   · ${esc(c.confidence)} ${c.url?`· <a href="${esc(c.url)}" target="_blank">源</a>`:''}
   ${c.published?'· '+esc(c.published):''}</div>${esc(c.clue)}<br><q>“${esc(c.quote.slice(0,140))}”</q></div>`).join('')
   :'<p class="hint">没有匹配的卡。</p>';};
  loadCards();}
 if(t==='submit'){main.innerHTML=`<h3>URL → 新闻管线</h3>
  <div class="row"><input id="url" size="52" placeholder="https://…（文章 URL）">
  segment <input id="useg" size="10"><button class="act" onclick="subUrl()">提交</button></div>
  <div id="ures"></div><h3 style="margin-top:26px">文件 → user_submitted/</h3>
  <div class="row"><input type="file" id="file"><button class="act" onclick="subFile()">上传</button></div>
  <div id="fres"></div><p class="hint">文件按 sha1 与整个工作区去重；重复件只记账不落盘。
  PDF 落盘后由既有 digest 批处理消化。</p>`;
  window.subUrl=async()=>{const u=document.getElementById('url').value.trim();
   if(!u)return;document.getElementById('ures').textContent='提交中…';
   const r=await fetch('/api/submit/url',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({url:u,segment:document.getElementById('useg').value})}).then(x=>x.json());
   document.getElementById('ures').innerHTML=pill(r.status)+
   (r.cards!==undefined?` ${r.cards} 张卡 `:'')+(r.reason?esc(r.reason):'');};
  window.subFile=async()=>{const f=document.getElementById('file').files[0];if(!f)return;
   const fd=new FormData();fd.append('upload',f);
   document.getElementById('fres').textContent='上传中…';
   const r=await fetch('/api/submit/file',{method:'POST',body:fd}).then(x=>x.json());
   document.getElementById('fres').innerHTML=pill(r.status)+' '+
   esc(r.saved_as||r.reason||'');};}
 if(t==='ledger'){const l=await jget('/api/ledger');
  main.innerHTML=`<table><tr><th>时间</th><th>类型</th><th>名称</th><th>sha1</th><th>状态</th><th>说明</th></tr>
  ${l.map(r=>`<tr><td>${esc(r.ts)}</td><td>${esc(r.kind)}</td><td>${esc(r.name)}</td>
  <td>${esc((r.sha1||'').slice(0,8))}</td><td>${pill(r.status)}</td><td>${esc(r.detail)}</td></tr>`).join('')
  ||'<tr><td colspan="6" class="hint">还没有提交记录。</td></tr>'}</table>`;}
}
tabs();go('stats');
</script></body></html>"""


def serve(workspace: Path, *, host: str = "127.0.0.1", port: int = 8790,
          queue_name: str = "下载队列") -> None:
    """Run the portal locally. Reads ZHIPU_API_KEY from the environment
    (load via your secrets manager; never hardcode)."""
    import os

    import uvicorn

    key = os.environ.get("ZHIPU_API_KEY") or None
    app = create_app(workspace, zhipu_key=key, queue_name=queue_name)
    print(f"Gate H portal -> http://{host}:{port}  "
          f"(workspace: {workspace}; URL submit "
          f"{'ON' if key else 'OFF (no ZHIPU_API_KEY)'})")
    uvicorn.run(app, host=host, port=port, log_level="warning")
