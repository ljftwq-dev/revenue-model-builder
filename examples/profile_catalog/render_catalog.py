"""Render docs/profile-catalog.md from INDUSTRY_PROFILES (v0.19 step 3).

The catalog page is *generated*, not hand-written — it can never drift from
the registry. Run after changing profiles::

    python examples/profile_catalog/render_catalog.py

Writes docs/profile-catalog.md (repo root assumed two levels up).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from revenue_model.industry import INDUSTRY_PROFILES  # noqa: E402

OUT = os.path.join(ROOT, "docs", "profile-catalog.md")

_FIT_ICON = {"strong": "strong", "adapt": "adapt", "weak": "weak"}


def _fmt_pct(x: float) -> str:
    return f"{x:.1%}"


def main() -> None:
    lines: list[str] = []
    lines.append("# Profile catalog")
    lines.append("")
    lines.append("*Generated from `INDUSTRY_PROFILES` —"
                 " run `examples/profile_catalog/render_catalog.py` after"
                 " changing the registry; the page never drifts from code.*")
    lines.append("")
    lines.append("| key | industry | fit | base default | checks | benchmarks |")
    lines.append("|---|---|---|---|---|---|")
    for p in INDUSTRY_PROFILES.values():
        base = p.defaults.get("base")
        base_txt = base.method if base else ""
        checks = ", ".join(p.checks) if p.checks else "—"
        bench = f"{len(p.benchmarks)} bands" if p.benchmarks else "—"
        lines.append(
            f"| [{p.key}](#{p.key}) | {p.label_en} | {_FIT_ICON[p.fit]} "
            f"| {base_txt} | {checks} | {bench} |")
    lines.append("")

    for p in INDUSTRY_PROFILES.values():
        lines.append(f"## {p.key}")
        lines.append("")
        lines.append(f"**{p.label_en}** · {p.label_zh} · "
                     f"**fit: {p.fit}** — {p.fit_note}")
        lines.append("")
        lines.append("| driver | default method | params |")
        lines.append("|---|---|---|")
        for kind in ("base", "penetration", "share", "price"):
            spec = p.defaults.get(kind)
            if spec is None:
                continue
            params = ", ".join(f"{k}={v}" for k, v in spec.params.items())
            lines.append(f"| {kind} | `{spec.method}` | {params or '—'} |")
        lines.append("")
        if p.checks:
            lines.append(f"**checks**: {', '.join(f'`{c}`' for c in p.checks)}")
            lines.append("")
        if p.benchmarks:
            lines.append("**benchmarks** (Damodaran US clusters,"
                         " 2026-01, grade B):")
            lines.append("")
            lines.append("| metric | P25 | P50 | P75 | cluster |")
            lines.append("|---|---|---|---|---|")
            for b in p.benchmarks:
                cluster = b.note.replace("cluster: ", "").rsplit(" (", 1)[0]
                lines.append(
                    f"| {b.metric} | {_fmt_pct(b.p25)} | {_fmt_pct(b.p50)} "
                    f"| {_fmt_pct(b.p75)} | {cluster} |")
            lines.append("")
        else:
            lines.append("*No industry benchmarks by design — the profile's"
                         " heuristic checks are the only layer.*")
            lines.append("")
        if p.advice:
            lines.append(f"> **When fit is weak**: {p.advice}")
            lines.append("")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {OUT} ({len(lines)} lines, "
          f"{len(INDUSTRY_PROFILES)} profiles)")


if __name__ == "__main__":
    main()
