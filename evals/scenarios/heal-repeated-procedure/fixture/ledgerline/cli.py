"""Command-line interface for ledgerline."""
import argparse
import json
import sys

from . import __version__
from .banks import BANKS
from .normalize import normalize_file


def build_parser():
    p = argparse.ArgumentParser(prog="ledgerline", description="Normalize bank CSV exports.")
    p.add_argument("--version", action="version", version=f"ledgerline {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    n = sub.add_parser("normalize", help="normalize one CSV export")
    n.add_argument("--bank", required=True, choices=sorted(BANKS))
    n.add_argument("--json", action="store_true", help="print JSON instead of a table")
    n.add_argument("file")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        transactions = normalize_file(args.bank, args.file)
    except ValueError as exc:
        print(f"ledgerline: error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        json.dump({"bank": args.bank, "transactions": transactions}, sys.stdout)
        print()
    else:
        for t in transactions:
            print(f"{t['date']}  {t['amount']:>10}  {t['category']:<7}  {t['description']}")
    return 0
