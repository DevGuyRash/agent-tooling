import argparse
import sys

from . import config, render, sales


def build_parser():
    parser = argparse.ArgumentParser(prog="stallbook")
    parser.add_argument("--data", default="data", help="directory with sales.csv and stallbook.ini")
    commands = parser.add_subparsers(dest="command", required=True)
    report = commands.add_parser("report", help="print one week's sales")
    report.add_argument("--week", required=True, help="week label, such as 2026-W14")
    report.add_argument("--format", choices=["text"], default="text", help="output format")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    settings = config.load(args.data)
    report = sales.load_week(args.data, args.week)
    if args.format == "text":
        sys.stdout.write(render.render_text(report, settings))
    return 0
