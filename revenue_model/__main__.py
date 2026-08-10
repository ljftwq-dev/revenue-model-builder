"""Unified CLI: python -m revenue_model {build, simulate, excel, docx, tushare, extract}.

Aggregates the demo alignment check, Monte Carlo + sensitivity, Excel/Word
rendering, tushare A-share adapter, and annual-report segment extraction
behind a single entry point.

The pure-stdlib core stays importable without the [excel] extra: the ``excel``
command imports openpyxl lazily and prints a helpful install hint if it is
missing.
"""
import argparse
import json
import os

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


def cmd_tushare(args):
    from .tushare_adapter import build_model_from_tushare
    token = args.token or os.environ.get("TUSHARE_TOKEN")
    if not token:
        raise SystemExit(
            "tushare token required: pass --token or set TUSHARE_TOKEN "
            "(load via your secrets manager; never hardcode)")
    model = build_model_from_tushare(
        args.ts_code, token=token, years=args.years)
    print(f"OK -> {model.company} ({args.ts_code}) | years: {model.years()}")
    for y in model.years():
        yr = model.validate(y)
        print(f"  {y}: total {yr.total_revenue:,.0f}M | residual {yr.residual_ratio:.0%}")
    print("segments (driver values are [adapter] placeholders, fill to forecast):")
    for s in model.segments:
        print(f"  - {s.name}")
    if args.output:
        try:
            from .excel_builder import build_excel
        except ImportError as exc:
            raise SystemExit(
                "output needs the [excel] extra: "
                "pip install revenue-model-builder[excel]") from exc
        out = build_excel(model, args.output)
        print(f"Excel -> {out}")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="revenue_model",
        description="Bottom-up revenue forecasting (driver-based, zero-dep core).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser(
        "build",
        help="validate the NovaTech demo model aligns to reported totals")
    p_build.set_defaults(func=cmd_build)

    p_sim = sub.add_parser(
        "simulate",
        help="Monte Carlo + Bear/Base/Bull + tornado on the demo")
    p_sim.set_defaults(func=cmd_simulate)

    p_excel = sub.add_parser(
        "excel",
        help="render the NovaTech demo model to a formatted .xlsx")
    p_excel.add_argument(
        "output", nargs="?", default="NovaTech_revenue_model_demo.xlsx",
        help="output .xlsx path (default: ./NovaTech_revenue_model_demo.xlsx)")
    p_excel.set_defaults(func=cmd_excel)

    p_docx = sub.add_parser(
        "docx",
        help="render the NovaTech demo model to a Word memo (.docx)")
    p_docx.add_argument(
        "output", nargs="?", default="NovaTech_revenue_model_demo.docx",
        help="output .docx path (default: ./NovaTech_revenue_model_demo.docx)")
    p_docx.add_argument(
        "--lang", default="en", choices=["zh", "en"],
        help="memo language: 'en' (default, global) or 'zh' (中文版)")
    p_docx.add_argument(
        "--no-charts", action="store_true",
        help="render tables only, no embedded charts (skip matplotlib)")
    p_docx.set_defaults(func=cmd_docx)

    p_extract = sub.add_parser(
        "extract",
        help="extract a segment skeleton from annual-report text")
    p_extract.add_argument(
        "file", help="text file with the 'main business analysis' section")
    p_extract.add_argument(
        "--api-key", default=None,
        help="LLM API key (load via your secrets manager; never hardcode)")
    p_extract.set_defaults(func=cmd_extract)

    p_tushare = sub.add_parser(
        "tushare",
        help="build a RevenueModel from tushare (A-share NEV / intelligent-driving)")
    p_tushare.add_argument(
        "ts_code", help="A-share ts_code, e.g. 002405.SZ (德赛西威)")
    p_tushare.add_argument(
        "--token", default=None,
        help="tushare token (or env TUSHARE_TOKEN; load via your secrets manager)")
    p_tushare.add_argument(
        "--years", type=int, nargs="*", default=None,
        help="optional year filter (default: all annual reports on record)")
    p_tushare.add_argument(
        "-o", "--output", default=None,
        help="optional: also render to .xlsx via excel_builder")
    p_tushare.set_defaults(func=cmd_tushare)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
