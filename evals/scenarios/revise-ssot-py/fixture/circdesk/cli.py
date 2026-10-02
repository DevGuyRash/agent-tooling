"""circdesk: desk receipts, overnight notices, and the kiosk's account view, from the library system's
nightly exports."""
import argparse
import datetime as dt
import sys

from .account import account
from .loans import ExportError, read_loans, read_patrons
from .notices import notices
from .receipt import receipt


def _date(text):
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a date (YYYY-MM-DD)") from None


def _parser():
    p = argparse.ArgumentParser(prog="circdesk", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("receipt", help="the desk receipt for a returned item")
    r.add_argument("loans", help="loans export (loans.csv)")
    r.add_argument("loan_id")
    n = sub.add_parser("notices", help="overdue notices for tonight's mailing")
    n.add_argument("loans", help="loans export (loans.csv)")
    n.add_argument("patrons", help="patrons export (patrons.csv)")
    n.add_argument("--on", type=_date, help="the day to work fines out for (default: today)")
    a = sub.add_parser("account", help="what one patron owes, for the kiosk")
    a.add_argument("loans", help="loans export (loans.csv)")
    a.add_argument("patrons", help="patrons export (patrons.csv)")
    a.add_argument("patron_id")
    a.add_argument("--on", type=_date, help="the day to work fines out for (default: today)")
    return p


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.command == "receipt":
            text = receipt(read_loans(args.loans), args.loan_id)
        elif args.command == "notices":
            text = notices(read_loans(args.loans), read_patrons(args.patrons), args.on or dt.date.today())
        else:
            text = account(read_loans(args.loans), read_patrons(args.patrons), args.patron_id,
                           args.on or dt.date.today())
    except ExportError as exc:
        print(f"circdesk: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(text)
    return 0
