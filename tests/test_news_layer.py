"""Tests for revenue_model.news_layer (transports injected — no network)
plus the news-related EvidenceCard/chain rendering extensions."""

import json

import pytest

from revenue_model.chains_cli import build_chainbook, render_cards_md, render_chains_md
from revenue_model.evidence import EvidenceCard
from revenue_model.news_layer import (
    KeywordGroup,
    NewsSpec,
    _clusters,
    _news_prompt,
    _same_fact,
    _wire_copy,
    fetch_news,
    grade_sources,
    render_suggestions,
    spec_from_json,
)


def test_news_prompt_company_injection():
    """The digest prompt names the drill subject via parameter — the layer
    must stay company-agnostic (no hard-coded Palantir in the mechanism)."""
    p_pltr = _news_prompt("BODY TEXT", "US_Gov", "Palantir")
    p_other = _news_prompt("BODY TEXT", "", "Contemporary Amperex")
    assert "Palantir" in p_pltr
    assert "Contemporary Amperex" in p_other
    assert "BODY TEXT" in p_other and "US_Gov" in p_pltr
    # the JSON contract survives the templating
    assert '"clue"' in p_other and '"ring"' in p_other


# ---------------------------------------------------------------------------
# fixtures: fake transports
# ---------------------------------------------------------------------------

ARTICLES = {
    "https://defensescoop.com/maven": {
        "title": "DoD expands Maven",
        "text": ("The Pentagon plans to expand the Maven Smart System "
                 "program with Palantir. The FY27 budget request includes "
                 "$1.5 billion for the effort according to budget documents "
                 "published in May 2026. Officials said the expansion "
                 "covers several combatant commands." + " filler " * 60),
    },
    "https://spacenews.com/maven-budget": {
        "title": "Pentagon budget Maven",
        "text": ("The Pentagon's FY27 budget request seeks $1.5 billion to "
                 "expand the Maven Smart System built by Palantir, budget "
                 "documents show. The expansion follows growing demand "
                 "from combatant commands." + " filler " * 60),
    },
    "https://eu-sovereignty.eu/palantir-paradox": {
        "title": "The Palantir paradox",
        "text": ("Europe's sovereignty push keeps running into Palantir "
                 "software. Critics in several capitals want tighter "
                 "scrutiny of American software vendors, and thousands "
                 "signed a petition to end a UK public-sector contract."
                 + " filler " * 60),
    },
    "https://paywalled-daily.com/story": None,          # fetch fails
}

SEEN_WINDOWS = []          # (query, recency) the fake search received


def fake_search(query, count, recency=None):
    SEEN_WINDOWS.append((query, recency))
    if "Maven" in query or "DoD" in query:
        return [{"link": "https://defensescoop.com/maven",
                 "title": "DoD expands Maven", "publish_date": "2026-05-14"},
                {"link": "https://spacenews.com/maven-budget",
                 "title": "Pentagon budget Maven", "publish_date": "2026-05-15"},
                {"link": "https://paywalled-daily.com/story",
                 "title": "Premium", "publish_date": "2026-05-16"}]
    if "sovereignty" in query:
        return [{"link": "https://eu-sovereignty.eu/palantir-paradox",
                 "title": "The Palantir paradox", "publish_date": "2026-05-02"}]
    return []


def fake_fetch(url):
    art = ARTICLES.get(url)
    if art is None:
        raise ValueError("403 paywall")
    return art


def fake_digest(text, url, seg):
    if "spacenews" in url:
        return [{"clue": "FY27 预算申请 15 亿美元扩大 Maven",
                 "quote": "budget request seeks $1.5 billion",
                 "ring": "updown", "segment": "US_Gov"}]
    if "maven" in url or "budget" in url:
        return [
            {"clue": "FY27 预算文件点名扩大 Maven，预算 15 亿美元",
             "quote": "budget request includes $1.5 billion",
             "ring": "updown", "segment": "US_Gov"},
            {"clue": "编造的引文",
             "quote": "THIS SENTENCE IS NOT IN THE ARTICLE AT ALL",
             "ring": "core", "segment": "US_Gov"},
        ]
    if "eu-sovereignty" in url:
        return [{"clue": "欧洲主权悖论：审查呼声与依赖并存",
                 "quote": "sovereignty push keeps running into Palantir",
                 "ring": "updown", "segment": "Int_Comm"}]
    return []


SPEC = NewsSpec(groups=(
    KeywordGroup("US_Gov", ("Palantir DoD Maven budget",)),
    KeywordGroup("Int_Comm", ("Palantir Europe sovereignty",)),
))


# ---------------------------------------------------------------------------
# fetch_news end-to-end (fake transports)
# ---------------------------------------------------------------------------

def test_fetch_news_verify_grade_and_uncovered(tmp_path):
    r = fetch_news(SPEC, search_fn=fake_search, fetch_fn=fake_fetch,
                   digest_fn=fake_digest, cache_dir=tmp_path / "cache")
    cards = r["cards"]
    assert len(cards) == 3                        # 2 maven + 1 sovereignty
    # the fabricated quote was rejected
    assert any("quote_not_found" in v for v in r["rejects"])
    # the paywalled article landed on the uncovered list, not the cards
    assert any("paywalled-daily" in u["url"] for u in r["uncovered"])
    # every card is verified and carries url + published
    assert all(c.verified and c.url for c in cards)
    pub = {c.url: c.published for c in cards}
    assert pub["https://defensescoop.com/maven"] == "2026-05-14"
    # the two Maven reports are independent origins -> dual
    conf = {c.url: c.confidence for c in cards}
    assert conf["https://defensescoop.com/maven"] == "dual"
    assert conf["https://spacenews.com/maven-budget"] == "dual"
    # the sovereignty story stands alone -> single (kept!)
    assert conf["https://eu-sovereignty.eu/palantir-paradox"] == "single"


def test_fetch_news_cache_resume_zero_calls(tmp_path):
    class CountingFetch:
        calls = 0

        def __call__(self, url):
            CountingFetch.calls += 1
            return fake_fetch(url)

    fetch_news(SPEC, search_fn=fake_search, fetch_fn=CountingFetch(),
               digest_fn=fake_digest, cache_dir=tmp_path / "c1")
    first = CountingFetch.calls
    assert first == 4                    # 3 fetched + 1 paywalled attempt
    r2 = fetch_news(SPEC, search_fn=fake_search, fetch_fn=CountingFetch(),
                    digest_fn=fake_digest, cache_dir=tmp_path / "c1")
    assert CountingFetch.calls == first  # all hits (incl. negative cache)
    assert len(r2["cards"]) == 3
    assert len(r2["uncovered"]) == 1     # paywall remembered, not re-hit


def test_failed_search_group_recorded_not_fatal(tmp_path):
    def boom(query, count, recency=None):
        if "Maven" in query:
            raise RuntimeError("search down")
        return fake_search(query, count, recency)

    r = fetch_news(SPEC, search_fn=boom, fetch_fn=fake_fetch,
                   digest_fn=fake_digest, cache_dir=tmp_path / "c")
    assert r["failed_groups"] and "Maven" in r["failed_groups"][0]["query"]
    assert len(r["cards"]) == 1                    # the other group ran


def test_queries_limit_smoke():
    r = fetch_news(SPEC, search_fn=fake_search, fetch_fn=fake_fetch,
                   digest_fn=fake_digest, queries_limit=1)
    assert all(c.segment == "US_Gov" for c in r["cards"])


# ---------------------------------------------------------------------------
# clustering / grading rules in isolation
# ---------------------------------------------------------------------------

def card(url, published, quote, clue="", segment="US_Gov"):
    return EvidenceCard(clue=clue or f"线索 {quote[:20]}",
                        anchor_file=url.split("//")[1].split(".")[0],
                        anchor_page=1, quote=quote, ring="updown",
                        segment=segment, verified=True, url=url,
                        published=published)


def test_same_fact_number_match():
    a = card("https://a.com/x", "2026-05-01", "the deal was worth $1.5 billion")
    b = card("https://b.com/y", "2026-06-01", "a 1.5 billion dollar contract",
             segment="US_Gov")
    assert _same_fact(a, b)


def test_same_fact_word_overlap_fallback():
    a = card("https://a.com/x", "2026-05-01",
             "European lawmakers scrutiny Palantir sovereignty petition",
             segment="Int_Comm")
    b = card("https://b.com/y", "2026-06-01",
             "Palantir sovereignty petition scrutiny grows Europe",
             segment="Int_Comm")
    assert _same_fact(a, b)


def test_wire_copy_same_day_shared_phrase():
    q = "Palantir announced Maven expansion combatant commands today"
    a = card("https://a.com/x", "2026-05-14", q)
    b = card("https://b.com/y", "2026-05-14", q)
    assert _wire_copy(a, b)
    c = card("https://c.com/z", "2026-05-20", q)
    assert not _wire_copy(a, c)                    # different day


def test_grade_wire_copy_is_one_origin():
    q = "Palantir announced Maven expansion combatant commands today"
    a = card("https://a.com/x", "2026-05-14", q)
    b = card("https://b.com/y", "2026-05-14", q)   # wire copy of a
    graded = grade_sources([a, b])
    assert all(c.confidence == "single" for c in graded)


def test_grade_primary_document_backs_cluster():
    q = "budget request includes $1.5 billion for Maven"
    doc = EvidenceCard(clue="FY27 预算文件", anchor_file="dodbudget",
                       anchor_page=3, quote=q, ring="updown",
                       segment="US_Gov", verified=True,
                       url="https://comptroller.gov/fy27.pdf",
                       published="2026-05-14", confidence="primary")
    news = card("https://defensescoop.com/m", "2026-05-14", q)
    graded = grade_sources([doc, news])
    by_url = {c.url: c.confidence for c in graded}
    assert by_url["https://comptroller.gov/fy27.pdf"] == "primary"
    assert by_url["https://defensescoop.com/m"] == "dual"


def test_clusters_keeps_unrelated_apart():
    a = card("https://a.com/x", "2026-05-01",
             "budget request includes $1.5 billion", segment="US_Gov")
    b = card("https://b.com/y", "2026-05-01",
             "petitions grow against UK contract", segment="Int_Comm")
    assert len(_clusters([a, b])) == 2


# ---------------------------------------------------------------------------
# rendering + chain integration
# ---------------------------------------------------------------------------

def test_render_suggestions_flags_and_counts():
    cards = fetch_news(SPEC, search_fn=fake_search, fetch_fn=fake_fetch,
                       digest_fn=fake_digest, cache_dir=None)["cards"]
    md = render_suggestions(cards)
    assert "US_Gov" in md and "Int_Comm" in md
    assert md.count("来源: https://") == 3
    assert "[dual]" in md and "[single]" in md
    assert "单源 1 张" in md


def test_single_source_chain_marker():
    news = card("https://eu-sovereignty.eu/palantir-paradox", "2026-05-02",
                "sovereignty push keeps running into Palantir",
                clue="欧洲主权悖论", segment="Int_Comm")
    filing = EvidenceCard(clue="Int_Comm 六季仅 +28%", anchor_file="10q.pdf",
                          anchor_page=19, quote="Commercial revenue",
                          ring="core", segment="Int_Comm", verified=True)
    spec = [{"cards": ["eu-sovereignty·p1", "10q.pdf·p19"],
             "verdict": "欧洲商业横盘是政治摩擦", "parameter": "Int_Comm 2027 1.10-1.35",
             "authority": "user"}]
    md = render_chains_md(build_chainbook([news, filing], spec), "T")
    assert "[含单源]" in md
    assert "eu-sovereignty.eu" in md           # news card shows its url


def test_cards_md_shows_source_line_for_news():
    news = card("https://spacenews.com/m", "2026-05-15", "budget documents show")
    md = render_cards_md([news], "浏览")
    assert "spacenews.com" in md and "`single`" in md


def test_load_news_cards_from_cache_only(tmp_path):
    from revenue_model.news_layer import load_news_cards

    r = fetch_news(SPEC, search_fn=fake_search, fetch_fn=fake_fetch,
                   digest_fn=fake_digest, cache_dir=tmp_path / "c")
    loaded = load_news_cards(tmp_path / "c")
    assert {c.url for c in loaded} == {c.url for c in r["cards"]}
    assert all(c.verified for c in loaded)
    conf = {c.url: c.confidence for c in loaded}
    assert conf["https://defensescoop.com/maven"] == "dual"
    assert conf["https://eu-sovereignty.eu/palantir-paradox"] == "single"
    # search-metadata dates survive the cache round-trip (the regex
    # fallback on article text alone would lose them: "May 2026" != ISO)
    dates = {c.url: c.published for c in loaded}
    assert dates["https://defensescoop.com/maven"] == "2026-05-14"
    assert dates["https://spacenews.com/maven-budget"] == "2026-05-15"


def test_spec_roundtrip(tmp_path):
    p = tmp_path / "spec.json"
    p.write_text('{"groups": [{"segment": "US_Comm", '
                 '"queries": ["a", "b"], "days_back": 30}], '
                 '"exclude_domains": ["prnewswire.com"]}', encoding="utf-8")
    spec = spec_from_json(p)
    assert spec.groups[0].segment == "US_Comm"
    assert spec.groups[0].days_back == 30
    assert spec.exclude_domains == ("prnewswire.com",)


# ---------------------------------------------------------------------------
# search time window: days_back wired through to the engine (v0.22.2)
# ---------------------------------------------------------------------------

from revenue_model.news_layer import (  # noqa: E402
    _av_date,
    _recency_for,
    av_news_search,
    ceg_news_spec,
    merge_results,
    news_spec_for,
)


# ---------------------------------------------------------------------------
# presets: the mechanism stays company-agnostic (PLTR was just first)
# ---------------------------------------------------------------------------

def test_ceg_preset_branches_follow_revenue_geography():
    """The CEG preset (second-company run, 2026-09) must carry the
    company-agnostic contract: non-empty queries, real branch names
    aligned to CEG's reportable segments, and no Palantir strings."""
    spec = ceg_news_spec()
    assert spec.groups and all(g.queries for g in spec.groups)
    segs = {g.segment for g in spec.groups}
    assert {"Mid_Atlantic", "Midwest"} <= segs
    for g in spec.groups:
        for q in g.queries:
            assert "Palantir" not in q


def test_news_spec_for_registry():
    assert news_spec_for("pltr").groups[0].segment == "US_Comm"
    assert news_spec_for("ceg").groups[0].segment == ""
    import pytest

    with pytest.raises(ValueError, match="unknown news preset"):
        news_spec_for("nvda")


def test_recency_for_boundaries():
    assert _recency_for(0) is None                    # explicit unlimited
    assert _recency_for(-5) is None
    assert _recency_for(1) == "oneDay"
    assert _recency_for(7) == "oneWeek"
    assert _recency_for(8) == "oneMonth"
    assert _recency_for(31) == "oneMonth"
    assert _recency_for(120) == "oneYear"
    assert _recency_for(366) == "oneYear"
    assert _recency_for(400) is None                  # > a year: all history


def test_fetch_news_passes_days_back_window(tmp_path):
    SEEN_WINDOWS.clear()
    spec = NewsSpec(groups=(KeywordGroup("US_Gov", ("Palantir DoD Maven budget",),
                                         days_back=30),))
    fetch_news(spec, search_fn=fake_search, fetch_fn=fake_fetch,
               digest_fn=fake_digest, cache_dir=None)
    assert SEEN_WINDOWS[0] == ("Palantir DoD Maven budget", "oneMonth")


def test_fetch_news_recency_override_beats_days_back(tmp_path):
    SEEN_WINDOWS.clear()
    spec = NewsSpec(groups=(KeywordGroup("US_Gov", ("Palantir DoD Maven budget",),
                                         days_back=30),))
    fetch_news(spec, search_fn=fake_search, fetch_fn=fake_fetch,
               digest_fn=fake_digest, cache_dir=None,
               recency_override="noLimit")
    assert SEEN_WINDOWS[0][1] is None                 # widened to all history


# ---------------------------------------------------------------------------
# AV NEWS_SENTIMENT add-on source (v0.22.2)
# ---------------------------------------------------------------------------

AV_FEED = {
    "feed": [
        {"title": "Palantir wins Army contract extension",
         "url": "https://www.defensenews.com/ground/2026/09/17/pltr-army/",
         "time_published": "20260917T201512",
         "source": "Defensenews",
         "summary": "The Army extended its Maven-related contract.",
         "overall_sentiment_label": "Bullish"},
        {"title": "Dup of the same story",
         "url": "https://defensescoop.com/maven",
         "time_published": "20260917T210000",
         "source": "Defensescoop",
         "summary": "Wire copy.",
         "overall_sentiment_label": "Neutral"},
        {"title": "No URL item gets dropped",
         "url": "",
         "time_published": "20260918T010000",
         "source": "X", "summary": "", "overall_sentiment_label": "Neutral"},
    ]
}


class _FakeAVResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_av_news_search_maps_feed(monkeypatch):
    import urllib.request

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeAVResponse(AV_FEED)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    import revenue_model.news_layer as nl
    monkeypatch.setattr(nl, "_av_last_call", [])      # fresh throttle memory
    hits = av_news_search("whatever query", 8, api_key="K",
                          tickers="PLTR", _now=lambda: 1000.0,
                          _sleep=lambda s: None)
    assert "function=NEWS_SENTIMENT" in captured["url"]
    assert "tickers=PLTR" in captured["url"]
    assert "apikey=K" in captured["url"]
    assert len(hits) == 2                             # empty-URL item dropped
    first = hits[0]
    assert first["link"] == AV_FEED["feed"][0]["url"]
    assert first["publish_date"] == "2026-09-17"      # T-stamp -> date
    assert first["sentiment"] == "Bullish"


def test_av_news_search_quota_error_raises(monkeypatch):
    import urllib.request

    def fake_urlopen(req, timeout=None):
        return _FakeAVResponse({"Information": "25 requests per day limit"})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    import revenue_model.news_layer as nl
    monkeypatch.setattr(nl, "_av_last_call", [])

    with pytest.raises(RuntimeError, match="25 requests"):
        av_news_search("q", 5, api_key="K", tickers="PLTR",
                       _now=lambda: 2000.0, _sleep=lambda s: None)


def test_av_date_tolerance():
    assert _av_date("20260918T130000") == "2026-09-18"
    assert _av_date("20260918T1300") == "2026-09-18"
    assert _av_date("") == ""
    assert _av_date("garbage") == "garbage"[:10]


def test_merge_results_dedups_by_link():
    a = [{"link": "https://x.com/1", "title": "one"},
         {"link": "https://x.com/2", "title": "two"}]
    b = [{"link": "https://x.com/2", "title": "two-dup"},
         {"link": "https://y.com/3", "title": "three"},
         {"link": "", "title": "linkless dropped"}]
    merged = merge_results(a, b)
    assert [i["link"] for i in merged] == ["https://x.com/1",
                                           "https://x.com/2",
                                           "https://y.com/3"]
    assert merged[1]["title"] == "two"                # first occurrence wins


def test_av_items_ride_the_same_pipeline(tmp_path):
    """An AV-discovered article flows through fetch -> digest -> verbatim
    verify exactly like a search hit — the add-on adds discovery, never
    a shortcut around the hard gate."""
    av_hit = [{"link": "https://spacenews.com/maven-budget",
               "title": "Pentagon budget Maven",
               "publish_date": "2026-05-15",
               "source": "AV", "sentiment": "Bullish"}]
    r = fetch_news(SPEC, search_fn=lambda q, n, recency=None: av_hit,
                   fetch_fn=fake_fetch, digest_fn=fake_digest,
                   cache_dir=tmp_path / "c")
    assert any(c.url == "https://spacenews.com/maven-budget" for c in r["cards"])
    assert all(c.verified for c in r["cards"])
