# Contributing to revenue-model-builder

Thanks for your interest in improving this project. This is a small,
opinionated library, so a few conventions matter a lot.

## The one rule that matters most

**The core engine stays zero-dependency (pure Python stdlib).**

`Driver`, `Segment`, `RevenueModel`, Monte Carlo, tornado, scenarios, and the
planned stochastic layer are all stdlib-only. This is a deliberate selling
point (see the README badge: `dependencies: 0`) — it makes the engine
auditable, fast to install, and trivially portable. Do **not** add `numpy`,
`pandas`, `scipy`, or any other third-party import to `revenue_model/` core.

Optional capabilities live behind extras:
- `[excel]` → `openpyxl` (only `excel_builder.py` and the `excel` CLI command)
- `[dev]` → `pytest`

If your feature genuinely needs a dependency, put it behind a new extra and
import it lazily (see how `excel_builder.py` is imported inside `cmd_excel`).

## Development setup

```bash
git clone https://github.com/ljftwq-dev/revenue-model-builder
cd revenue-model-builder
pip install -e ".[dev,excel]"     # core + pytest + openpyxl
pytest -q                          # 35 tests, <1s
python -m revenue_model build      # smoke-test the CLI
```

## Before you open a PR

1. **Tests pass:** `pytest -q` (all green)
2. **Core stays zero-dep:** if you touched `revenue_model/*.py`, confirm no new
   third-party import leaked in (`grep -rn "^import\|^from" revenue_model |
   grep -v "from \."` should show only stdlib + relative imports)
3. **Docs build clean (if you touched `docs/`):** `mkdocs build --strict` —
   strict mode fails on broken links or warnings, so a green build means the
   site is healthy
4. **Math renders as LaTeX:** inline math uses `$...$`, display math `$$...$$`.
   Identifier expressions (like `base × penetration × share × price`) stay in
   code blocks — they read better monospaced and don't need rendering.

## Commit message style

This project uses [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: <what you added>
docs: <what you documented>
fix: <what you fixed>
test: <what you tested>
refactor: <what you restructured>
```

The first line is lowercase, imperative, ≤72 chars. Add a body for anything
non-obvious. Look at `git log --oneline` for the established tone.

## What's especially welcome

- **Real-data demos** behind a separate sub-repo or release attachment (never
  commit real company financials to this repo — see
  [DISCLAIMER.md](DISCLAIMER.md) and `docs/proposal-segment-extraction.md` §8.1
  for the compliance boundary)
- **Driver templates** for the segment-extraction pipeline (see
  `docs/proposal-segment-extraction.md` §5)
- **Stochastic processes** that stay pure-stdlib (Box-Muller / Euler-Maruyama /
  hand-rolled Cholesky) — see
  `docs/plans/2026-07-28-stochastic-revenue-design.md`
- **Tests** that validate numerics against analytic solutions (the existing
  Monte Carlo and planned stochastic tests do exactly this)

## What probably belongs elsewhere

- Trading/backtesting signals (this is fundamental analysis, not quant trading)
- A web UI (consider a separate companion app rather than bloating the core)
- Buy/sell recommendations, price targets, or ratings — out of scope and a
  compliance red line

## Questions?

Open a [Discussion](https://github.com/ljftwq-dev/revenue-model-builder/discussions)
or an issue tagged `question`. Be kind — see our
[Code of Conduct](CODE_OF_CONDUCT.md).
