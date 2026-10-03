"""invoicing's command line."""
import argparse
import sys
from pathlib import Path

from .load import InvoiceError, load
from .month import month_report
from .render import render


def main(argv=None):
    parser = argparse.ArgumentParser(prog="invoicing", description="Invoices for Harbour Print Co-op.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("show", help="print an invoice").add_argument("invoice")
    commands.add_parser("month", help="month-end report for a directory of invoices").add_argument("directory")
    args = parser.parse_args(argv)
    try:
        if args.command == "show":
            print(render(load(args.invoice)))
        else:
            paths = sorted(Path(args.directory).glob("*.json"))
            if not paths:
                print(f"invoicing: no invoices in {args.directory}", file=sys.stderr)
                return 1
            print(month_report([load(p) for p in paths]))
    except InvoiceError as err:
        print(f"invoicing: {err}", file=sys.stderr)
        return 1
    except OSError as err:
        print(f"invoicing: {err.filename}: {err.strerror}", file=sys.stderr)
        return 1
    return 0
