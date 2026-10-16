"""The command line (SPEC R4, R5)."""
import argparse
import sys

from .data import DataError, load_loans, load_members, load_tools, parse_date


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
    return 0
