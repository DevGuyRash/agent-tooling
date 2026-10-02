"""Command line: python3 -m shopcrm COMMAND EXPORT.csv [...]"""

import argparse
import sys

from .contacts import COLUMNS, ExportError, find_matches, read_export, to_row, write_rows
from .stats import export_stats, format_stats
from .validate import validate_file


def _parser():
    parser = argparse.ArgumentParser(prog="shopcrm", description="Tools for the storefront's customer export.")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    p = sub.add_parser("validate", help="report rows the newsletter sync would reject")
    p.add_argument("export", help="the storefront's customer export (CSV)")
    p = sub.add_parser("lookup", help="print the rows with an email address or phone number")
    p.add_argument("export", help="the storefront's customer export (CSV)")
    p.add_argument("query", help="an email address or a phone number")
    p = sub.add_parser("stats", help="print counts for an export")
    p.add_argument("export", help="the storefront's customer export (CSV)")
    return parser


def _validate(args):
    messages = validate_file(args.export)
    for message in messages:
        print(message, file=sys.stderr)
    if messages:
        return 1
    print(f"{args.export}: ok")
    return 0


def _lookup(args):
    matches = find_matches(read_export(args.export), args.query)
    if not matches:
        print(f"shopcrm: no rows match {args.query}", file=sys.stderr)
        return 1
    write_rows([COLUMNS, *(to_row(c) for c in matches)], sys.stdout)
    return 0


def _stats(args):
    sys.stdout.write(format_stats(export_stats(read_export(args.export))))
    return 0


COMMANDS = {"validate": _validate, "lookup": _lookup, "stats": _stats}


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except ExportError as exc:
        print(f"shopcrm: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"shopcrm: {exc.filename}: {exc.strerror}", file=sys.stderr)
        return 1
