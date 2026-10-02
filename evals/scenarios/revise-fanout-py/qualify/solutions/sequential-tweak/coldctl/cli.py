"""coldctl command line."""

import argparse
import sys

from . import __version__
from .gateway import GatewayError, NoAnswer, Session, gateway_url, list_units, unit_reading

NO_ANSWER_AFTER = 1.5  # seconds; trimmed from 2: even the slow bus segments answer within about a second
LIST_TIMEOUT = 10.0


def describe(reading):
    """A unit's reading as one line, the way `coldctl temp` prints it."""
    line = f"{reading['id']}: {reading['temp_c']:.1f} C (setpoint {reading['setpoint_c']:.1f} C)"
    if reading.get("defrost"):
        line += ", defrosting"
    return line


def cmd_units(args):
    for unit_id, zone in sorted(list_units(args.base)):
        print(f"{unit_id}  {zone}")
    return 0


def cmd_temp(args):
    for unit_id in args.unit:
        print(describe(unit_reading(args.base, unit_id)))
    return 0


def check_one(session, unit_id):
    """(outcome, line) for one unit: read, no answer, or failed."""
    try:
        return "read", describe(session.unit_reading(unit_id, timeout=NO_ANSWER_AFTER))
    except NoAnswer:
        return "no answer", f"{unit_id}: no answer"
    except GatewayError as exc:
        reason = f"HTTP {exc.status}" if exc.status is not None else "gateway unreachable"
        return "failed", f"{unit_id}: failed ({reason})"


def cmd_check(args):
    try:
        ids = sorted(unit_id for unit_id, _ in list_units(args.base, timeout=LIST_TIMEOUT))
    except GatewayError as exc:
        print(f"coldctl: cannot get the unit list: {exc}", file=sys.stderr)
        return 2
    counts = {"read": 0, "no answer": 0, "failed": 0}
    session = Session(args.base)
    try:
        for unit_id in ids:
            outcome, line = check_one(session, unit_id)
            counts[outcome] += 1
            print(line)
    finally:
        session.close()
    print(f"checked {len(ids)} units: {counts['read']} read, {counts['no answer']} no answer, "
          f"{counts['failed']} failed")
    return 0 if counts["read"] == len(ids) else 1


def build_parser():
    parser = argparse.ArgumentParser(prog="coldctl",
                                     description="Refrigeration checks for the Larchmont Grocers distribution center.")
    parser.add_argument("--gateway", metavar="URL",
                        help="BMS gateway base URL (default: $COLDCTL_GATEWAY, else http://127.0.0.1:8640)")
    parser.add_argument("--version", action="version", version=f"coldctl {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("units", help="list every refrigeration unit the gateway knows")
    p.set_defaults(func=cmd_units)

    p = sub.add_parser("temp", help="show units' temperature and setpoint right now")
    p.add_argument("unit", nargs="+", help="unit ID, for example U-0412")
    p.set_defaults(func=cmd_temp)

    p = sub.add_parser("check", help="read every unit for the food-safety monitor; exit 1 if any unit gave no "
                                     "reading, 2 without a unit list")
    p.set_defaults(func=cmd_check)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.base = gateway_url(args.gateway)
    try:
        return args.func(args)
    except GatewayError as exc:
        print(f"coldctl: {exc}", file=sys.stderr)
        return 1
