"""coldctl command line."""

import argparse
import sys

from . import __version__
from .gateway import GatewayError, gateway_url, list_units
from .reader import read_units

LIST_TIMEOUT = 10.0


def describe(reading):
    """A unit's reading as one line, the way `coldctl temp` prints it."""
    line = f"{reading['id']}: {reading['temp_c']:.1f} C (setpoint {reading['setpoint_c']:.1f} C)"
    if reading.get("defrost"):
        line += ", defrosting"
    return line


def render(result):
    """One line for a read result, whatever its outcome."""
    if result.outcome == "read":
        return describe(result.reading)
    if result.outcome == "no answer":
        return f"{result.unit_id}: no answer"
    reason = f"HTTP {result.status}" if result.status is not None else "gateway unreachable"
    return f"{result.unit_id}: failed ({reason})"


def report(results):
    """Print every result; the outcome counts."""
    counts = {"read": 0, "no answer": 0, "failed": 0}
    for result in results:
        counts[result.outcome] += 1
        print(render(result))
    return counts


def cmd_units(args):
    for unit_id, zone in sorted(list_units(args.base, timeout=LIST_TIMEOUT)):
        print(f"{unit_id}  {zone}")
    return 0


def cmd_temp(args):
    # temp and check share one reader now: the units are read in parallel and reported the same way.
    counts = report(read_units(args.base, args.unit))
    return 0 if counts["no answer"] == counts["failed"] == 0 else 1


def cmd_check(args):
    try:
        ids = [unit_id for unit_id, _ in list_units(args.base, timeout=LIST_TIMEOUT)]
    except GatewayError as exc:
        print(f"coldctl: cannot get the unit list: {exc}", file=sys.stderr)
        return 2
    counts = report(read_units(args.base, ids))
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
