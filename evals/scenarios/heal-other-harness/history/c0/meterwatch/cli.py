"""The meterwatch command line."""
import argparse

from .events import load_events
from .invoice import build_invoice
from .rollup import daily_totals


def cmd_daily(args):
    totals = daily_totals(load_events(args.events))
    for day, keys in totals.items():
        for key, units in keys.items():
            print(f"{day}  {key}  {units}")


def cmd_invoice(args):
    totals = daily_totals(load_events(args.events))
    lines, total = build_invoice(totals, args.rate, args.start, args.end)
    for day, key, units, amount in lines:
        print(f"{day}  {key}  {units}  {amount}")
    print(f"total  {total}")


def build_parser():
    parser = argparse.ArgumentParser(prog="meterwatch")
    sub = parser.add_subparsers(dest="command", required=True)

    daily = sub.add_parser("daily", help="units per UTC day and key")
    daily.add_argument("events")
    daily.set_defaults(run=cmd_daily)

    invoice = sub.add_parser("invoice", help="price the units")
    invoice.add_argument("events")
    invoice.add_argument("--rate", required=True, help="price per unit")
    invoice.add_argument("--from", dest="start", help="first UTC day (YYYY-MM-DD)")
    invoice.add_argument("--to", dest="end", help="last UTC day (YYYY-MM-DD)")
    invoice.set_defaults(run=cmd_invoice)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.run(args)
    return 0
