"""Tests for revenue_model.news_layer (transports injected — no network)
plus the news-related EvidenceCard/chain rendering extensions."""

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


def fake_search(query, count):
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
    def boom(query, count):
        if "Maven" in query:
            raise RuntimeError("search down")
        return fake_search(query, count)

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


def test_spec_roundtrip(tmp_path):
    p = tmp_path / "spec.json"
    p.write_text('{"groups": [{"segment": "US_Comm", '
                 '"queries": ["a", "b"], "days_back": 30}], '
                 '"exclude_domains": ["prnewswire.com"]}', encoding="utf-8")
    spec = spec_from_json(p)
    assert spec.groups[0].segment == "US_Comm"
    assert spec.groups[0].days_back == 30
    assert spec.exclude_domains == ("prnewswire.com",)
