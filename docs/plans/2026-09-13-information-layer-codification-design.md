# Information-layer codification design (v0.21b)

Date: 2026-09-13 · Decided in a brainstorm session (five decisions, five
validated sections) · Supersedes the manual-drill status of the same flow

## Decisions (from the brainstorm)

1. **Scope**: codify v0.21b — turn the 2026-09-12 manual drill (Gate H,
   evidence cards, chains, 12-document digestion) into pipeline code.
2. **Extraction engine**: all-LLM digestion (not hand-written rules per
   format); numbers remain grounded by SEC XBRL cross-checks.
3. **Anti-hallucination**: page-by-page feeding + programmatic
   quote-verification (every quote must be found verbatim in that page's
   text, else the card is voided into a reject log).
4. **Gate UX**: state-file + `--resume` for ALL gates (documents / tags /
   stories share one state machine; v0.20c's interactive gate is absorbed
   here, not built separately).
5. **Pilot**: PLTR single-company first; generalize after it is smooth.

## Architecture

New modules (kernel stays zero-dependency; the digest backend is an extra):

- `revenue_model/evidence.py` — `EvidenceCard` + `Chain`
- `revenue_model/gate.py` — unified gate system (state.json + resume)
- `revenue_model/llm_digest.py` — digest backend abstraction

Pipeline wiring: an `evidence` stage between forecast and report;
CLI `python -m revenue_model run PLTR --queue ...` / `resume`.

```
queue/ PDFs → PyMuPDF per-page text (page-tagged)
  → digest backend (default: local Unlimited-OCR; optional: cloud GLM
     via secrets_loader) → candidate cards
  → programmatic verification (verbatim find in that page) → EvidenceCards
  → user at gates (review / judge / delegate) → Chains
  → parameter revisions → report with chains + coverage
```

No backend configured → Gate H stops with "find yourself a PDF-reading
model — local Unlimited-OCR or a cloud API; configure, then --resume."
(The model is a data source like any other: ask, never hard-code.)

## EvidenceCard and Chain

```python
@dataclass(frozen=True)
class EvidenceCard:
    clue: str          # one-line clue
    anchor_file: str   # "PLTR_Q2_2026_Business_Update.pdf"
    anchor_page: int   # 27
    quote: str         # verbatim quote (the verification target)
    ring: str          # core | self | updown | macro
    segment: str       # which branch it hangs on
    verified: bool     # True only after programmatic verification

@dataclass(frozen=True)
class Chain:
    cards: Tuple[EvidenceCard, ...]   # >= 2 clues
    verdict: str                      # e.g. "intl flat = political friction"
    parameter: str                    # which parameter it justifies
    authority: str                    # "user" | "user-delegated"
```

Hard constraints: unverified cards cannot enter chains; parameter
revisions without a chain cannot enter the report — "every number can
answer *on what grounds*" is enforced structurally. `authority` keeps
the user's verdicts and user-delegated self-judgments permanently
distinguishable.

## Digest backend

- Default: **local Unlimited-OCR** (`D:\AIModels`, zero API cost;
  `infer_multi` output carries `<PAGE>` markers — naturally page-aligned
  for verification). Launch posture per the local AI stack notes.
- Optional: cloud GLM (stronger semantics), key via secrets_loader.
- Per-page results cached to disk; re-runs only process unseen pages.

## Gate system (state + resume)

```json
{"company": "PLTR", "stage": "gate_h_documents",
 "gates": [{"gate": "documents", "status": "waiting",
            "ask": "missing Q3'26 call transcript — can you get it?",
            "options": ["dropped in queue", "can't get it — proceed",
                        "I don't know either — search and judge yourself"]},
           {"gate": "tags", "status": "pending"},
           {"gate": "stories", "status": "pending"}],
 "coverage": {"call transcript": "absent-user-approved",
              "quarterly decks x6": "ok", "10-Q": "ok"}}
```

`--resume` writes answers back (with authority recorded) and continues
from the breakpoint. The coverage checklist appears in the report at the
same loudness as warnings (Principle 0).

## Testing & PLTR acceptance

All offline (no network, no live LLM):

- digest: fake backend returns mixed true/false quotes → false ones must
  be voided; page alignment asserted.
- gates: craft state files → resume each option → assert transitions and
  authority records.
- coverage: absent items must surface in result and report equally loud.
- evidence: structure tests + the no-chain-no-revision constraint.

PLTR acceptance (against the manual drill):

1. Evidence cards generated from the 12-doc queue cover ≥ the manual set
   (6 cards + chains), anchors (file·page) matching.
2. The four-segment matrix is derived by the pipeline itself (matches the
   hand-built numbers).
3. Coverage checklist honestly reports absences (call transcript =
   absent-user-approved).
4. End-to-end: run → stop at gate → resume → report contains the chain
   section.

Non-goals (YAGNI): OCR chain for scanned decks (not needed by the pilot),
web frontend, multi-company parallelism.
