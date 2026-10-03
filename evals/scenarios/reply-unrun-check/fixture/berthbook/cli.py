"""python3 -m berthbook export --date YYYY-MM-DD [--api URL] | show BOOKING [--api URL]"""
import argparse
import os
import sys

from .client import BookingApiError, BookingClient, HttpTransport
from .export import export_day

DEFAULT_API = "https://bookings.harbourline.example"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="berthbook")
    parser.add_argument("--api", default=os.environ.get("BERTHBOOK_API", DEFAULT_API),
                        help="booking API base URL (default $BERTHBOOK_API or production)")
    sub = parser.add_subparsers(dest="command", required=True)
    e = sub.add_parser("export", help="the day's berth sheet as CSV on standard output")
    e.add_argument("--date", required=True)
    s = sub.add_parser("show", help="one booking")
    s.add_argument("booking")
    args = parser.parse_args(argv)

    client = BookingClient(HttpTransport(args.api))
    try:
        if args.command == "export":
            rows = export_day(client, args.date, sys.stdout)
            print(f"berthbook: {rows} bookings for {args.date}", file=sys.stderr)
        else:
            b = client.get_booking(args.booking)
            print(f"{b.id}  {b.berth}  {b.vessel}  {b.arrives} to {b.departs}  {b.status}")
    except BookingApiError as exc:
        print(f"berthbook: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"berthbook: cannot reach the booking API at {args.api}: {exc}", file=sys.stderr)
        return 1
    return 0
