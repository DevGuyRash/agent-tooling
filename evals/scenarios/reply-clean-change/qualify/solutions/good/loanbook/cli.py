"""loanbook's command line: python3 -m loanbook [--data DIR] COMMAND ..."""
import argparse
import datetime
import sys

from .records import RecordsError, load
from .report import due_lines, overdue_lines


def _date(text):
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f'bad date "{text}" (use YYYY-MM-DD)') from None


def _within(text):
    if not text.isdigit() or not 1 <= int(text) <= 14:
        raise argparse.ArgumentTypeError(f'--within must be 1 to 14, not "{text}"')
    return int(text)


def cmd_overdue(args, library):
    return overdue_lines(library, args.on)


def cmd_due(args, library):
    return due_lines(library, args.on, args.within)


def build_parser():
    parser = argparse.ArgumentParser(prog="loanbook", description="Ashby Street Library of Things loans.")
    parser.add_argument("--data", default="data", help="directory holding items.csv, members.csv, loans.csv")
    sub = parser.add_subparsers(dest="command", required=True)

    o = sub.add_parser("overdue", help="loans past their due date, by member")
    o.add_argument("--on", type=_date, default=datetime.date.today(), help="the day to check (default today)")
    o.set_defaults(func=cmd_overdue)

    d = sub.add_parser("due", help="loans coming due soon, by member")
    d.add_argument("--on", type=_date, default=datetime.date.today(), help="the first day (default today)")
    d.add_argument("--within", type=_within, default=2, help="days after --on to include, 1 to 14 (default 2)")
    d.set_defaults(func=cmd_due)
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
