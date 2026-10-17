"""Command-line interface for chorelog."""
import argparse
from datetime import date

from .log import Entry, append_entry, read_entries
from .report import count_by_person


def build_parser():
    p = argparse.ArgumentParser(prog="chorelog", description="Keep a household chore log.")
    p.add_argument("--file", default="chores.log", help="the log file (default: chores.log)")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("add", help="record a chore")
    a.add_argument("person")
    a.add_argument("chore")
    a.add_argument("--date", type=date.fromisoformat, help="YYYY-MM-DD (default: today)")
    sub.add_parser("report", help="count entries per person")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "add":
        append_entry(args.file, Entry(args.date or date.today(), args.person, args.chore))
        return 0
    entries = read_entries(args.file)
    if not entries:
        print("no entries")
        return 0
    for person, count in count_by_person(entries):
        print(f"{person}: {count}")
    return 0
