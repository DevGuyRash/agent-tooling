"""invoicing's command line."""
import argparse
import sys

from .load import InvoiceError, load
from .render import render


def main(argv=None):
    parser = argparse.ArgumentParser(prog="invoicing", description="Invoices for Harbour Print Co-op.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("show", help="print an invoice").add_argument("invoice")
    args = parser.parse_args(argv)
    try:
        print(render(load(args.invoice)))
    except InvoiceError as err:
        print(f"invoicing: {err}", file=sys.stderr)
        return 1
    except OSError as err:
        print(f"invoicing: {err.filename}: {err.strerror}", file=sys.stderr)
        return 1
    return 0
