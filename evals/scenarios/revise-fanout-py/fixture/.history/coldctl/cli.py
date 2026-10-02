"""coldctl command line."""

import argparse
import sys

from . import __version__
from .gateway import GatewayError, gateway_url, list_units, unit_reading


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
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.base = gateway_url(args.gateway)
    try:
        return args.func(args)
    except GatewayError as exc:
        print(f"coldctl: {exc}", file=sys.stderr)
        return 1
