# News Layer Design (v0.22) — the updown ring finally gets fed

Date: 2026-09-14 · Status: approved (brainstorm session, five forks locked)

## Problem

The 12-document PLTR drill produced 2,638 verified cards, but the ring
distribution is lopsided: core 66%, self 21%, **updown 6%**, macro 6%.
The upstream/downstream signal a real analyst works with (the manual
ArcSoft forecast's differentiator) does not live in 10-Qs and decks — it
lives in news, supplier announcements, budget documents. The L0/L1/L2
experiment (2026-09-12) already quantified this: news-guided estimate =
true value, extrapolation = -60%. This version wires that layer in.

Also: worldmonitor MCP verified dead on 2026-09-14 (Unauthorized on all
calls, anonymous tier apparently removed) — the plan no longer depends
on it.

## Locked decisions (Q1–Q5)

1. **Scope**: PLTR single-case drill; all mechanisms company-agnostic
   (config-driven like `MatrixSpec`) so 1.0.0's multi-company replay is
   a config change, not a rewrite.
2. **Sources**: targeted web news first (`web-search-prime` search +
   `web-reader` article fetch, verbatim quote verification against the
   fetched text), plus SEC 8-K EX-99 alongside (existing
   `form8k_adapter` base). AV NEWS_SENTIMENT deferred (later sentiment
   add-on). worldmonitor dropped.
3. **Gate semantics — soft tiering**: the ONLY hard filter is the
   verbatim-quote check (kills fabrications, never real news). Source
   cross-checking is a *label*, not a deletion: `confidence =
   primary | dual | single`. Single-source cards chain normally; the
   chain renders with a `[含单源]` marker; an all-single chain prints a
   review prompt — never blocks. "Source" counts ORIGINS, not articles:
   same-domain = one source; near-simultaneous near-identical wording
   (wire copy) conservatively merges to one; articles citing the same
   underlying document cluster onto that document, which upgrades to
   `primary` when fetchable.
4. **Operation**: manual CLI batch (`news_batch.py` pattern — fetch →
   verify → cache, resumable). Scheduled runs only after the gate is
   proven.
5. **Parameter influence**: news cards hang on chains as evidence; the
   pipeline emits a *suggestion list* (text) vs current parameters.
   Parameter changes are always hand-written into the chains spec —
   opinions stay human (project Principle).

## Architecture (approved section 1)

```
NewsSpec (company-agnostic; PLTR = first preset)
   │  per-segment keyword groups (customers/suppliers/rivals/deals/policy)
   ▼
① search: web-search-prime per keyword group (last N days, top K each)
   ▼
② fetch: web-reader pulls article markdown per URL
   ▼
③ digest: glm-4-flash, same prompt family as llm_digest
   ▼
④ verify: quote must appear verbatim in the fetched text   ← only hard gate
   ▼
⑤ grade: program-only dual/single clustering (origin-level)
   ▼
⑥ NewsCard store (news_cache/{url-hash}.json; resume = zero API cost)
   ▼
⑦ merge with 8-K EX-99 cards → `cards` browses everything
   ▼
⑧ suggestions.md: news cards vs current chain parameters (text only)
```

8-K route: `form8k_adapter` pulls EX-99 text through the same ③④⑤
channel, graded `primary` (a filing IS the origin).

## Data structure (approved section 2)

`EvidenceCard` gains four optional fields (defaults keep every existing
call site and the `Chain` hard constraints untouched):

- `url` — the resolvable source link (traceability core)
- `published` — publication date
- `confidence` — `primary | dual | single` (default `single`)
- `anchor_file` for news = domain slug, `anchor_page` = 1; the md
  renderer shows `【domain·date】+ URL` for news cards.

Fact clustering is pure program: cluster signature = (segment, key
entities, key numbers with tolerance); origin dedup by domain; wire-copy
detection via time proximity (<6h) + shared long phrases.

## Error handling (approved section 3)

Local failures void locally (digest philosophy): a failed keyword group
is skipped and listed; unfetchable articles (403/paywall/JS) produce NO
card and land on an explicit *uncovered list* (never pretend); backend
failures void that article for resume; total network failure aborts and
reports (the workspace network rule).

## Testing

Unit (no network): every clustering/grading rule; NewsCard→Chain
compatibility; `[含单源]` rendering; suggestion generation; cache resume.
Live acceptance (PLTR): (a) re-find the manual drill's chain-2 news
clues (EU sovereignty paradox / France24 scrutiny / UK petition) as
cards; (b) updown share 6% → **≥15%**; (c) at least one news-anchored
chain end-to-end through the chains CLI into a rendered report.

## Deliverables

`revenue_model/news_layer.py` · `tests/test_news_layer.py` · CLI
`python -m revenue_model news` · `程序\PLTR管线\news_batch.py` +
PLTR NewsSpec preset · suggestions output · CHANGELOG entry (v0.22).
