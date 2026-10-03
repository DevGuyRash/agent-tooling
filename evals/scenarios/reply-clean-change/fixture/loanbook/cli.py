"""loanbook's command line: python3 -m loanbook [--data DIR] COMMAND ..."""
import argparse
import datetime
import sys

from .records import RecordsError, load
from .report import overdue_lines


def _date(text):
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f'bad date "{text}" (use YYYY-MM-DD)') from None


def cmd_overdue(args, library):
    return overdue_lines(library, args.on)


def build_parser():
    parser = argparse.ArgumentParser(prog="loanbook", description="Ashby Street Library of Things loans.")
    parser.add_argument("--data", default="data", help="directory holding items.csv, members.csv, loans.csv")
    sub = parser.add_subparsers(dest="command", required=True)

    o = sub.add_parser("overdue", help="loans past their due date, by member")
    o.add_argument("--on", type=_date, default=datetime.date.today(), help="the day to check (default today)")
    o.set_defaults(func=cmd_overdue)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        library = load(args.data)
        lines = args.func(args, library)
    except RecordsError as exc:
        print(f"loanbook: {exc}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return 0
