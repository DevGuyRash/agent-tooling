"""circdesk: desk receipts from the library system's nightly exports."""
import argparse
import sys

from .loans import ExportError, read_loans
from .receipt import receipt


def _parser():
    p = argparse.ArgumentParser(prog="circdesk", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("receipt", help="the desk receipt for a returned item")
    r.add_argument("loans", help="loans export (loans.csv)")
    r.add_argument("loan_id")
    return p


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        text = receipt(read_loans(args.loans), args.loan_id)
    except ExportError as exc:
        print(f"circdesk: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(text)
    return 0
