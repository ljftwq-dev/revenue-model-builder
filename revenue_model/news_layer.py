"""News layer (v0.22) — targeted news into verifiable cards, feeding the
updown ring (6% of the filing corpus; the gap the manual drill showed).

Pipeline per the approved design (docs/plans/2026-09-14-news-layer-design.md):

    NewsSpec (company-agnostic keyword groups per segment)
      -> search (Zhipu web_search MCP endpoint, Bearer key)
      -> fetch article text (plain urllib, html -> text)
      -> digest (cloud GLM, news prompt, same JSON shape as llm_digest)
      -> verify: quote verbatim in the fetched text   <- the ONLY hard gate
      -> grade: confidence primary/dual/single by origin-level clustering
      -> cache per URL hash (resume = zero API cost)

Gate semantics are deliberately SOFT beyond the hard gate: single-source
cards exist, chain, and render with a marker — source cross-checking is
a label, never a deletion (nothing gets thrown away except fabrications).

The transport callables (search_fn / fetch_fn / digest_fn) are injectable
for tests; the defaults need ZHIPU_API_KEY and network.
"""
import hashlib
import html as html_lib
import json
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .evidence import EvidenceCard
from .llm_digest import _parse_json_array, _sanitize

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}

_POSITIVE = ("win", "won", "contract", "award", "expand", "record", "renew",
             "growth", "partnership", "deal", "中标", "扩大", "增长", "合作",
             "续约", "大单")
_NEGATIVE = ("terminat", "suspend", "scrutiny", "protest", "delay", "cut",
             "risk", "decline", "petition", "审查", "终止", "暂停", "风险",
             "抗议", "请愿", "下滑", "推迟")


# ---------------------------------------------------------------------------
# spec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KeywordGroup:
    """One search group feeding one segment branch."""
    segment: str
    queries: Tuple[str, ...]
    ring: str = "updown"
    days_back: int = 120
    max_results: int = 8


@dataclass(frozen=True)
class NewsSpec:
    """Company-agnostic news configuration (PLTR is just a preset)."""
    groups: Tuple[KeywordGroup, ...]
    exclude_domains: Tuple[str, ...] = ()


def spec_from_json(path: Path) -> NewsSpec:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    groups = tuple(KeywordGroup(
        segment=g["segment"], queries=tuple(g["queries"]), ring=g.get("ring", "updown"),
        days_back=int(g.get("days_back", 120)), max_results=int(g.get("max_results", 8)))
        for g in data["groups"])
    return NewsSpec(groups=groups,
                    exclude_domains=tuple(data.get("exclude_domains", [])))


def pltr_news_spec() -> NewsSpec:
    """The PLTR drill preset: one group per four-segment branch + supply."""
    return NewsSpec(groups=(
        KeywordGroup("US_Comm", ("Palantir US commercial customer contract win",
                                 "Palantir enterprise AIP deal")),
        KeywordGroup("Int_Comm", ("Palantir Europe sovereignty scrutiny",
                                  "Palantir UK contract petition")),
        KeywordGroup("US_Gov", ("Palantir DoD Maven contract budget",
                                "Palantir Army contract award")),
        KeywordGroup("Int_Gov", ("Palantir international government contract",)),
        KeywordGroup("", ("Palantir partner cloud AWS Azure reseller",)),
    ))


# ---------------------------------------------------------------------------
# transports (injectable)
# ---------------------------------------------------------------------------

def mcp_web_search(query: str, *, api_key: str, count: int = 8,
                   recency: str = None, base: str =
                   "https://open.bigmodel.cn/api/mcp/web_search_prime/mcp") -> List[dict]:
    """Zhipu web-search over the same MCP endpoint the assistant uses
    (initialize -> tools/call web_search_prime, SSE-parsed). Returns
    [{title, link, content, ...}]."""
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream",
               "Authorization": f"Bearer {api_key}", **UA}
    session = {"id": None}

    def _rpc(payload):
        h = dict(headers)
        if session["id"]:
            h["Mcp-Session-Id"] = session["id"]
        req = urllib.request.Request(base, data=json.dumps(payload).encode(),
                                     headers=h)
        with urllib.request.urlopen(req, timeout=60) as resp:
            sid = resp.headers.get("Mcp-Session-Id")
            if sid:
                session["id"] = sid
            raw = resp.read().decode("utf-8", errors="replace")
        events = []
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                chunk = line[5:].strip()
                if chunk and chunk != "[DONE]":
                    try:
                        events.append(json.loads(chunk))
                    except json.JSONDecodeError:
                        pass
        return events

    _rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
          "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                     "clientInfo": {"name": "rmb-news", "version": "0.22"}}})
    _rpc({"jsonrpc": "2.0", "method": "notifications/initialized"})
    args: Dict = {"search_query": query, "content_size": "medium"}
    if recency:
        args["search_recency_filter"] = recency
    events = _rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                   "params": {"name": "web_search_prime", "arguments": args}})
    for e in events:
        if e.get("id") == 2 and "result" in e:
            for c in e["result"].get("content", []):
                if c.get("type") == "text":
                    raw = c.get("text", "")
                    parsed = None
                    try:
                        parsed = json.loads(raw)
                        if isinstance(parsed, str):     # double-encoded
                            parsed = json.loads(parsed)
                    except (json.JSONDecodeError, TypeError):
                        parsed = None
                    if parsed is None:
                        parsed = _parse_json_array(raw)
                    items = parsed if isinstance(parsed, list) else []
                    hits = [i for i in items
                            if isinstance(i, dict) and i.get("link")]
                    return hits[:count]
    return []


def fetch_article(url: str) -> Dict:
    """Plain HTTP fetch + html->text. Returns {"url", "title", "text"} or
    raises for the caller to record on the uncovered list."""
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as resp:
        ctype = resp.headers.get("Content-Type", "")
        raw = resp.read(900_000)
    if "html" not in ctype and "text" not in ctype and ctype:
        raise ValueError(f"content-type {ctype.split(';')[0]} not fetchable")
    page = raw.decode("utf-8", errors="replace")
    m = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
    title = html_lib.unescape(m.group(1)).strip() if m else url
    page = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", page)
    text = re.sub(r"(?s)<[^>]+>", " ", page)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    if len(text) < 300:
        raise ValueError("text too short (paywall/JS page)")
    return {"url": url, "title": title, "text": text}


def _news_prompt(text: str, seg: str, company: str) -> str:
    """The article-digest prompt. ``company`` is injected so the layer stays
    company-agnostic — the mechanism never hard-codes the drill subject."""
    return (
        f"你是新闻证据抽取器。下面是一篇可能与 {company} 收入相关的新闻。"
        "只准引用本文原文。找出有助于预测该公司未来收入的线索"
        "（客户/订单/合同、竞争、监管审查、供应链与合作伙伴、预算与政策）。"
        "输出 JSON 数组，每个元素形如：\n"
        '{"clue": "线索一句话(中文)", "quote": "本文原文逐字引用", '
        '"ring": "core|self|updown|macro", "segment": "' + (seg or "") + '"}\n'
        "ring 含义: core=收入数字/指引, self=公司自身动态, "
        "updown=上下游/客户/供应商/竞争, macro=宏观与政策。\n"
        "没有值得记录的线索就输出 []。绝不编造引文——引文必须能在本文中逐字找到。\n"
        "--- 正文开始 ---\n" + text + "\n--- 正文结束 ---"
    )


def make_glm_news_backend(api_key: str, model: str = "glm-4-flash",
                          company: str = "Palantir") -> Callable:
    """Cloud GLM digest backend for ONE news article (same JSON shape as
    the filing digest backend). ``company`` names the drill subject in the
    prompt (defaults to the historical PLTR drill; pass your own ticker)."""

    def backend(text: str, url: str, seg: str) -> List[dict]:
        prompt = _news_prompt(text, seg, company)
        body = json.dumps({"model": model,
                           "messages": [{"role": "user", "content": prompt}],
                           "temperature": 0.1}).encode("utf-8")
        req = urllib.request.Request(
            "https://open.bigmodel.cn/api/paas/v4/chat/completions",
            data=body, headers={"Authorization": f"Bearer {api_key}",
                                "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as r:
            resp = json.loads(r.read())
        return _parse_json_array(resp["choices"][0]["message"]["content"])

    return backend


# ---------------------------------------------------------------------------
# fetch + digest + verify orchestration
# ---------------------------------------------------------------------------

def _domain(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url or "")
    return m.group(1).lower().removeprefix("www.") if m else ""


def _slug(domain: str) -> str:
    return domain.split(".")[0] if domain else "unknown"


def _url_key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def fetch_news(spec: NewsSpec, *, search_fn: Callable, fetch_fn: Callable,
               digest_fn: Callable, cache_dir: Optional[Path] = None,
               queries_limit: int = 0) -> Dict:
    """Run the whole layer. search_fn(query, count) -> [{link, title,
    publish?}]; fetch_fn(url) -> {"title", "text"}; digest_fn(text, url,
    segment) -> [candidate dicts]. Cache keyed by URL hash; re-runs only
    pay for unseen URLs. Local failures never kill the batch."""
    cache = Path(cache_dir) if cache_dir else None
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
    cards: List[EvidenceCard] = []
    rejects: List[dict] = []
    uncovered: List[dict] = []
    failed_groups: List[dict] = []
    ran = 0
    for group in spec.groups:
        for query in group.queries:
            if queries_limit and ran >= queries_limit:
                return _finish(cards, rejects, uncovered, failed_groups)
            ran += 1
            try:
                results = search_fn(query, group.max_results)
            except Exception as exc:                       # noqa: BLE001
                failed_groups.append({"query": query,
                                      "error": f"{type(exc).__name__}: {exc}"})
                continue
            for item in results:
                url = item.get("link") or item.get("url") or ""
                if not url:
                    continue
                if any(d in _domain(url) for d in spec.exclude_domains):
                    continue
                published = str(item.get("publish_date") or item.get("date")
                                or item.get("published") or "")[:10]
                key = cache / f"{_url_key(url)}.json" if cache else None
                payload = None
                if key is not None and key.exists():
                    try:
                        payload = json.loads(key.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        payload = None
                if payload is not None and payload.get("uncovered_reason"):
                    uncovered.append({"url": url,
                                      "reason": payload["uncovered_reason"]})
                    continue
                if payload is None:
                    try:
                        art = fetch_fn(url)
                    except Exception as exc:               # noqa: BLE001
                        reason = (f"{type(exc).__name__}: "
                                  f"{str(exc)[:80]}")
                        uncovered.append({"url": url, "reason": reason})
                        if key is not None:
                            tmp = cache / f".{_url_key(url)}.tmp"
                            tmp.write_text(json.dumps(
                                {"url": url, "uncovered_reason": reason},
                                ensure_ascii=False), encoding="utf-8")
                            tmp.replace(key)
                        continue
                    try:
                        raw = digest_fn(art["text"], url, group.segment)
                    except Exception as exc:               # noqa: BLE001
                        rejects.append({"url": url, "digest_error":
                                        f"{type(exc).__name__}: {exc}"})
                        continue
                    payload = {"url": url, "title": art.get("title", ""),
                               "text": art["text"], "raw": raw}
                    if key is not None:
                        tmp = cache / f".{_url_key(url)}.tmp"
                        tmp.write_text(json.dumps(payload, ensure_ascii=False),
                                       encoding="utf-8")
                        tmp.replace(key)
                domain = _domain(url)
                for cand in payload.get("raw", []):
                    card = _sanitize(cand, _slug(domain), 1)
                    if card is None:
                        rejects.append({"url": url, "candidate": cand})
                        continue
                    verified = card.verify(payload["text"])
                    if verified.verified:
                        cards.append(EvidenceCard(
                            clue=card.clue, anchor_file=_slug(domain),
                            anchor_page=1, quote=card.quote, ring=card.ring,
                            segment=card.segment or group.segment,
                            verified=True, url=url,
                            published=published or _date_in(payload["text"])))
                    else:
                        rejects.append({"url": url, "quote_not_found": cand})
    return _finish(cards, rejects, uncovered, failed_groups)


def _finish(cards, rejects, uncovered, failed_groups) -> Dict:
    graded = grade_sources(cards)
    return {"cards": graded, "rejects": rejects, "uncovered": uncovered,
            "failed_groups": failed_groups}


def _date_in(text: str) -> str:
    m = re.search(r"\b(20[12]\d-[01]\d-[0-3]\d)\b", text)
    return m.group(1) if m else ""


def load_news_cards(cache_dir: Path) -> List[EvidenceCard]:
    """Verified news cards purely from a news cache (no network, no
    backend) — the browsing/chain-building path, mirroring
    llm_digest.load_cached_cards."""
    cache_dir = Path(cache_dir)
    cards: List[EvidenceCard] = []
    for f in sorted(cache_dir.glob("*.json")):
        if f.name.startswith("."):
            continue
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if payload.get("uncovered_reason"):
            continue
        domain = _domain(payload.get("url", ""))
        for cand in payload.get("raw", []):
            card = _sanitize(cand, _slug(domain), 1)
            if card is None:
                continue
            verified = card.verify(payload.get("text", ""))
            if verified.verified:
                cards.append(EvidenceCard(
                    clue=card.clue, anchor_file=_slug(domain), anchor_page=1,
                    quote=card.quote, ring=card.ring, segment=card.segment,
                    verified=True, url=payload.get("url", ""),
                    published=_date_in(payload.get("text", ""))))
    return grade_sources(cards)


# ---------------------------------------------------------------------------
# origin-level clustering + confidence grading (pure, deterministic)
# ---------------------------------------------------------------------------

def _numbers(text: str) -> List[float]:
    """Quantities with scale suffixes folded in ($1.5 billion ==
    15 亿 == 1.5e9) so cross-article number matching survives unit drift.
    Bare years are skipped."""
    out = []
    for m in re.finditer(r"(\d[\d,]*(?:\.\d+)?)\s*(billion|million|万亿|亿|百万)?",
                         text, re.I):
        raw = m.group(1).replace(",", "")
        try:
            v = float(raw)
        except ValueError:
            continue
        suf = (m.group(2) or "").lower()
        if not suf and 1990 <= v <= 2099 and "." not in raw:
            continue                       # years, not quantities
        mult = {"billion": 1e9, "million": 1e6, "亿": 1e8,
                "百万": 1e6, "万亿": 1e12}.get(suf, 1)
        v *= mult
        if abs(v) >= 3:
            out.append(v)
    return out


def _words(text: str) -> set:
    stop = {"the", "and", "for", "with", "that", "from", "this", "was",
            "were", "has", "have", "will", "said", "its", "their", "about",
            "into", "than", "then", "them", "they", "which", "while",
            "after", "before", "over", "under", "between", "during"}
    toks = {w for w in re.findall(r"[a-zA-Z]{4,}", text.lower()) if w not in stop}
    toks |= set(re.findall(r"[\u4e00-\u9fff]{2,}", text))
    return toks


def _same_fact(a: EvidenceCard, b: EvidenceCard) -> bool:
    if a.segment != b.segment:
        return False
    na, nb = _numbers(a.clue + " " + a.quote), _numbers(b.clue + " " + b.quote)
    for x in na:
        for y in nb:
            if abs(x - y) <= 0.02 * max(abs(x), abs(y)):
                return True
    wa, wb = _words(a.clue + " " + a.quote), _words(b.clue + " " + b.quote)
    j = len(wa & wb) / max(len(wa | wb), 1)
    return j >= 0.5


def _tokens(text: str) -> List[str]:
    """Ordered content tokens (for shingle/phrase work)."""
    return re.findall(r"[a-zA-Z]{4,}|[\u4e00-\u9fff]{2,}", text.lower())


def _wire_copy(a: EvidenceCard, b: EvidenceCard) -> bool:
    """Same-day + shared 5-gram -> almost certainly the same press release
    reposted: conservatively ONE origin regardless of domain."""
    if not a.published or a.published != b.published:
        return False
    ta, tb = _tokens(a.quote), _tokens(b.quote)
    if len(ta) < 5 or len(tb) < 5:
        return False
    sa = {tuple(ta[i:i + 5]) for i in range(len(ta) - 4)}
    sb = {tuple(tb[i:i + 5]) for i in range(len(tb) - 4)}
    return bool(sa & sb)


def _clusters(cards: List[EvidenceCard]) -> List[List[EvidenceCard]]:
    parent = list(range(len(cards)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(cards)):
        for j in range(i + 1, len(cards)):
            if _same_fact(cards[i], cards[j]) or _wire_copy(cards[i], cards[j]):
                parent[find(i)] = find(j)
    groups: Dict[int, List[EvidenceCard]] = {}
    for i, c in enumerate(cards):
        groups.setdefault(find(i), []).append(c)
    return list(groups.values())


def grade_sources(cards: List[EvidenceCard]) -> List[EvidenceCard]:
    """Assign confidence in place-safe fashion (returns new card list):

    - a cluster containing a ``primary`` card (underlying document)
      grades its news cards ``dual`` (document + reporting);
    - otherwise >= 2 distinct ORIGINS (domain, with same-day shared-
      phrase wire copies merged into one) -> ``dual``;
    - else ``single`` (kept! a label, never a deletion).
    """
    out: List[EvidenceCard] = []
    for cluster in _clusters(cards):
        has_primary = any(c.confidence == "primary" for c in cluster)
        origins = set()
        for a in cluster:
            wired = {_domain(b.url) for b in cluster
                     if b is not a and _wire_copy(a, b)}
            origins.add(_domain(a.url))
            origins -= wired                        # conservative merge
        dual = has_primary or len(origins) >= 2
        for c in cluster:
            conf = c.confidence
            if conf == "single":
                conf = "dual" if dual else "single"
            out.append(_replace_conf(c, conf))
    return out


def _replace_conf(card: EvidenceCard, conf: str) -> EvidenceCard:
    from dataclasses import replace
    return replace(card, confidence=conf)


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def render_suggestions(cards: List[EvidenceCard], title: str =
                       "新闻证据建议清单") -> str:
    """Per-segment review list with heuristic direction flags (+/-/?).
    Text only — parameter changes are always hand-written into the
    chains spec (opinions stay human)."""
    lines = [f"# {title}", "",
             "方向标记为启发式（关键词）判断，仅供快速扫读；"
             "改不改参数请对照 chains_spec 人工拍板。", ""]
    segs: Dict[str, List[EvidenceCard]] = {}
    for c in cards:
        segs.setdefault(c.segment or "(公司级)", []).append(c)
    for seg in sorted(segs):
        lines.append(f"## {seg}")
        lines.append("")
        for c in sorted(segs[seg], key=lambda x: x.published, reverse=True):
            blob = (c.clue + " " + c.quote).lower()
            flag = ("+" if any(w in blob for w in _POSITIVE) else
                    "-" if any(w in blob for w in _NEGATIVE) else "?")
            lines.append(f"- [{flag}] [{c.confidence}] {c.clue}")
            lines.append(f"  > \"{c.quote[:120]}\"")
            lines.append(f"  来源: {c.url} ({c.published or '日期未知'})")
        lines.append("")
    singles = sum(1 for c in cards if c.confidence == "single")
    lines.append(f"共 {len(cards)} 卡；单源 {singles} 张（可用，注意标签）。")
    return "\n".join(lines)
