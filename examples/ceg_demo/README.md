# CEG demo — the second-company generalization run (2026-09)

Constellation Energy proves the pipeline knows no company: everything
here is the `--preset ceg` configuration plus public EDGAR/IR data,
rebuilt end-to-end by four commands. The workspace itself (queue
PDFs, digest caches, webcast audio) stays local, like PLTR's —
rebuilt, not committed.

## Rebuild the workspace from scratch

```
python -m revenue_model tenq CEG --queue-dir workspace/下载队列 \
    --since 2025-01-01                          # 10-Qs + 10-Ks (matrix feeders)
python -m revenue_model matrix workspace/下载队列 --preset ceg
                                                # six regional segments,
                                                # loops S/C, Q4'25 backcast
python -m revenue_model news --preset ceg --company \
    --queue-dir workspace                       # news layer
python -c "from pathlib import Path; \
from revenue_model.llm_digest import make_glm_backend; \
from revenue_model.form8k_exhibit import digest_8k_exhibits; \
digest_8k_exhibits('CEG', make_glm_backend(), \
cache_dir=Path('workspace/digest_cache'), since='2025-01-01')"
                                                # 8-K EX-99 cards
python -m revenue_model webcast <ir-events-url> CEG Q2_2026 \
    --queue-dir workspace                       # earnings-call cards
```

Digest runs bill per page — use `tenq --no-digest` when landing, then
`--digest-latest N` to control spend.

## What the run produced (2026-09-21)

- 509 browseable verified cards: news 40 + 8-K EX-99 129 +
  earnings-call 20 + 10-Q digest 320 (Q2'26)
- Matrix: Mid-Atlantic / Midwest / New York / ERCOT / Other Power
  Regions (+ Calpine from the 2026-01-07 merger), loops S and C
  closed every quarter, Q4'25 backcast from the FY2025 10-K

Education/research use only.
