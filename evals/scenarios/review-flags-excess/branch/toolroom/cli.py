"""The command line (SPEC R4, R5, R9, R10)."""
import argparse
import sys
from datetime import date

from .data import DataError, load_loans, load_members, load_tools, parse_date
from .fines import ROUNDING_MODES
from .notices import write_notices
from .overdue import overdue_loans
from .render import render_csv, render_text


def _date_argument(text):
    try:
        return parse_date(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="toolroom", description="The books of a neighbourhood tool library.")
    parser.add_argument("--data", default=".", metavar="DIR", help="the directory with the three data files")
    parser.add_argument("--today", type=_date_argument, metavar="DATE", help="today's date, YYYY-MM-DD (default: the system date)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("out", help="list the loans that are still out")
    overdue = commands.add_parser("overdue", help="list the overdue loans and their fines")
    overdue.add_argument("--format", choices=("text", "csv"), default="text", help="how to print the list")
    overdue.add_argument("--notices", metavar="DIR", help="also write a notice for each member with an overdue loan")
    overdue.add_argument("--rounding", choices=ROUNDING_MODES, default="nearest", help="how a supporter's fine is rounded to the cent")
    args = parser.parse_args(argv)
    try:
        members = load_members(args.data)
        tools = load_tools(args.data)
        loans = load_loans(args.data, members, tools)
    except DataError as exc:
        print("toolroom: %s" % exc, file=sys.stderr)
        return 2
    if args.command == "out":
        for loan in sorted((loan for loan in loans if loan.returned is None), key=lambda loan: (loan.due, loan.id)):
            print("%s  %s  %s  %s" % (loan.id, members[loan.member].name, tools[loan.tool].name, loan.due.isoformat()))
    elif args.command == "overdue":
        today = args.today or date.today()
        rows = overdue_loans(loans, members, lambda: load_tools(args.data), today, args.rounding)
        sys.stdout.write((render_csv if args.format == "csv" else render_text)(rows))
        if args.notices:
            write_notices(args.notices, rows, members)
    return 0
