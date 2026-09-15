"""Unified CLI: python -m revenue_model {build, simulate, excel, docx, tushare, sec, akshare, extract}.

Aggregates the demo alignment check, Monte Carlo + sensitivity, Excel/Word
rendering, the three market adapters (A-share tushare / US SEC / HK akshare),
and annual-report segment extraction behind a single entry point.

The pure-stdlib core stays importable without any optional extra: ``excel`` /
``docx`` import their deps lazily; ``akshare`` needs the ``[data]`` extra.
"""
import argparse
import json
import os
from pathlib import Path

from .demo import build_novatech, print_validation, print_simulation
from .extractor import extract_segments


def cmd_build(args):
    print_validation(build_novatech())


def cmd_simulate(args):
    print_simulation(build_novatech())


def cmd_excel(args):
    try:
        from .excel_builder import build_excel
    except ImportError as exc:
        raise SystemExit(
            "The 'excel' command needs openpyxl. Install the [excel] extra:\n"
            "    pip install revenue-model-builder[excel]"
        ) from exc
    model = build_novatech()
    out = build_excel(model, args.output, forecast_years=[2025, 2026, 2027])
    print(f"OK -> {out}")
    print("historical columns: filled with real data + formulas")
    print("forecast columns 2025E/2026E/2027E: structure reserved (orange), values blank")


def cmd_docx(args):
    try:
        from .docx_builder import build_docx
    except ImportError as exc:
        raise SystemExit(
            "The 'docx' command needs python-docx. Install the [docx] extra:\n"
            "    pip install revenue-model-builder[docx]"
        ) from exc
    model = build_novatech()
    out = build_docx(model, args.output, lang=args.lang,
                     include_charts=not args.no_charts)
    print(f"OK -> {out}")
    print(f"language: {args.lang}  |  charts: {not args.no_charts}")


def cmd_extract(args):
    with open(args.file, encoding="utf-8") as f:
        text = f.read()
    parsed = extract_segments(text, api_key=args.api_key)
    print(json.dumps(parsed, ensure_ascii=False, indent=2))


def _print_market_model(model, unit_note, with_excel_output):
    print(f"OK -> {model.company} | years: {model.years()}")
    for y in model.years():
        yr = model.validate(y)
        print(f"  {y}: total {yr.total_revenue:,.0f}M {unit_note} | residual {yr.residual_ratio:.0%}")
    print("segments (driver values are [adapter] placeholders, fill to forecast):")
    for s in model.segments:
        print(f"  - {s.name}")


def cmd_tushare(args):
    from .tushare_adapter import build_model_from_tushare
    token = args.token or os.environ.get("TUSHARE_TOKEN")
    if not token:
        raise SystemExit(
            "tushare token required: pass --token or set TUSHARE_TOKEN "
            "(load via your secrets manager; never hardcode)")
    model = build_model_from_tushare(args.ts_code, token=token, years=args.years)
    _print_market_model(model, "CNY", None)
    if args.output:
        _render_excel(model, args.output)


def cmd_sec(args):
    from .sec_adapter import build_model_from_sec
    model = build_model_from_sec(args.ticker, years=args.years)
    _print_market_model(model, "USD", None)
    if args.output:
        _render_excel(model, args.output)


def cmd_akshare(args):
    try:
        from .akshare_adapter import build_model_from_akshare
    except ImportError as exc:
        raise SystemExit(
            "The 'akshare' command needs akshare. Install the [data] extra:\n"
            "    pip install revenue-model-builder[data]"
        ) from exc
    model = build_model_from_akshare(args.code, years=args.years)
    _print_market_model(model, "(orig. ccy)", None)
    if args.output:
        _render_excel(model, args.output)


def cmd_matrix(args):
    try:
        from .segment_matrix import build_matrix, pltr_spec, yoy_summary
    except ImportError as exc:
        raise SystemExit(
            "The 'matrix' command needs PyMuPDF. Install the [pdf] extra:\n"
            "    pip install revenue-model-builder[pdf]"
        ) from exc
    spec = pltr_spec() if args.preset == "pltr" else None
    if spec is None:
        raise SystemExit(f"unknown preset: {args.preset}")
    rows = build_matrix(args.queue_dir, spec)
    body = "\n".join(
        f"{t}: US_Comm {v['usc']:6.0f}  Int_Comm {v['icomm']:6.1f}  "
        f"US_Gov {v['usg']:6.0f}  Int_Gov {v['igov']:6.1f}  "
        f"sum={v['total']:7.1f}" for t, v in rows.items())
    print(body)
    print("\nY/Y by segment:")
    print(yoy_summary(rows))
    print("closed loops: A (US branches == geographic US) and "
          "B (sum4 == total) verified per quarter")
    if args.output:
        out = Path(args.output)
        out.write_text(body + "\n\nY/Y by segment:\n" + yoy_summary(rows)
                       + "\n", encoding="utf-8")
        print(f"saved {out}")


def cmd_cards(args):
    from .chains_cli import filter_cards, load_queue_cards, render_cards_md

    cards = load_queue_cards(args.queue_dir)
    cards = filter_cards(cards, ring=args.ring, segment=args.segment,
                         grep=args.grep)
    if args.limit:
        cards = cards[:args.limit]
    print(render_cards_md(cards, f"证据卡浏览 · {args.queue_dir}"))
    print(f"({len(cards)} cards shown)")


def cmd_chain(args):
    from .chains_cli import build_chainbook, load_queue_cards, \
        load_spec, render_chains_md

    specs = load_spec(args.spec)
    cards = load_queue_cards(args.queue_dir)
    book = build_chainbook(cards, specs)
    md = render_chains_md(book, args.title)
    out = Path(args.output)
    out.write_text(md, encoding="utf-8")
    cov = book.coverage_summary()
    print(f"OK -> {out}")
    print(f"chains: {cov['chains']} | cards cited: {cov['verified']} | "
          f"files: {len(cov['files'])}")


def _render_excel(model, output):
    try:
        from .excel_builder import build_excel
    except ImportError as exc:
        raise SystemExit(
            "output needs the [excel] extra: "
            "pip install revenue-model-builder[excel]") from exc
    print(f"Excel -> {build_excel(model, output)}")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="revenue_model",
        description="Bottom-up revenue forecasting (driver-based, zero-dep core).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="validate the NovaTech demo model aligns to reported totals")
    p_build.set_defaults(func=cmd_build)

    p_sim = sub.add_parser("simulate", help="Monte Carlo + Bear/Base/Bull + tornado on the demo")
    p_sim.set_defaults(func=cmd_simulate)

    p_excel = sub.add_parser("excel", help="render the NovaTech demo model to a formatted .xlsx")
    p_excel.add_argument("output", nargs="?", default="NovaTech_revenue_model_demo.xlsx",
                         help="output .xlsx path (default: ./NovaTech_revenue_model_demo.xlsx)")
    p_excel.set_defaults(func=cmd_excel)

    p_docx = sub.add_parser("docx", help="render the NovaTech demo model to a Word memo (.docx)")
    p_docx.add_argument("output", nargs="?", default="NovaTech_revenue_model_demo.docx",
                        help="output .docx path (default: ./NovaTech_revenue_model_demo.docx)")
    p_docx.add_argument("--lang", default="en", choices=["zh", "en"],
                        help="memo language: 'en' (default, global) or 'zh' (中文版)")
    p_docx.add_argument("--no-charts", action="store_true",
                        help="render tables only, no embedded charts (skip matplotlib)")
    p_docx.set_defaults(func=cmd_docx)

    p_extract = sub.add_parser("extract", help="extract a segment skeleton from annual-report text")
    p_extract.add_argument("file", help="text file with the 'main business analysis' section")
    p_extract.add_argument("--api-key", default=None,
                           help="LLM API key (load via your secrets manager; never hardcode)")
    p_extract.set_defaults(func=cmd_extract)

    # ---- three market adapters --------------------------------------------
    p_tushare = sub.add_parser("tushare", help="A-share adapter (tushare, NEV / intelligent-driving)")
    p_tushare.add_argument("ts_code", help="A-share ts_code, e.g. 002405.SZ (德赛西威)")
    p_tushare.add_argument("--token", default=None, help="tushare token (or env TUSHARE_TOKEN)")
    p_tushare.add_argument("--years", type=int, nargs="*", default=None, help="optional year filter")
    p_tushare.add_argument("-o", "--output", default=None, help="optional: also render to .xlsx")
    p_tushare.set_defaults(func=cmd_tushare)

    p_sec = sub.add_parser("sec", help="US-equity adapter (SEC EDGAR, intelligent-driving)")
    p_sec.add_argument("ticker", help="US ticker, e.g. NVDA / MBLY")
    p_sec.add_argument("--years", type=int, nargs="*", default=None, help="optional year filter")
    p_sec.add_argument("-o", "--output", default=None, help="optional: also render to .xlsx")
    p_sec.set_defaults(func=cmd_sec)

    p_akshare = sub.add_parser("akshare", help="HK-equity adapter (AKShare, needs [data] extra)")
    p_akshare.add_argument("code", help="HK code, e.g. 01211 (比亚迪股份)")
    p_akshare.add_argument("--years", type=int, nargs="*", default=None, help="optional year filter")
    p_akshare.add_argument("-o", "--output", default=None, help="optional: also render to .xlsx")
    p_akshare.set_defaults(func=cmd_akshare)

    # ---- v0.21b information layer: matrix + cards + chains ---------------
    p_matrix = sub.add_parser(
        "matrix", help="four-segment quarterly matrix, double closed-loop "
                       "checked (needs [pdf] extra)")
    p_matrix.add_argument("queue_dir", help="directory holding the queue PDFs")
    p_matrix.add_argument("--preset", default="pltr", choices=["pltr"],
                          help="company configuration (default: pltr)")
    p_matrix.add_argument("-o", "--output", default=None,
                          help="optional output .txt path")
    p_matrix.set_defaults(func=cmd_matrix)

    p_cards = sub.add_parser(
        "cards", help="browse verified evidence cards from a digest cache")
    p_cards.add_argument("queue_dir", help="queue directory (with digest_cache/)")
    p_cards.add_argument("--ring", default=None,
                         choices=["core", "self", "updown", "macro"],
                         help="filter by ring")
    p_cards.add_argument("--segment", default=None,
                         help="substring filter on segment")
    p_cards.add_argument("--grep", default=None,
                         help="substring filter on clue/quote")
    p_cards.add_argument("--limit", type=int, default=None,
                         help="show at most N cards")
    p_cards.set_defaults(func=cmd_cards)

    p_chain = sub.add_parser(
        "chain", help="build evidence chains from a spec JSON (拉链、定参数)")
    p_chain.add_argument("queue_dir", help="queue directory (with digest_cache/)")
    p_chain.add_argument("--spec", required=True,
                         help="chains spec JSON: [{cards, verdict, parameter, authority}, ...]")
    p_chain.add_argument("-o", "--output", default="evidence-chains.md",
                         help="output markdown (default: ./evidence-chains.md)")
    p_chain.add_argument("--title", default="证据串联卡 —— 线索→链条→参数",
                          help="markdown title")
    p_chain.set_defaults(func=cmd_chain)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
