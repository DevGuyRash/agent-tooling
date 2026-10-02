"""coldctl command line."""

import argparse
import os
import time
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

from . import __version__
from .gateway import GatewayError, NoAnswer, gateway_url, list_units, unit_reading

NO_ANSWER_AFTER = 2.0  # seconds; the food-safety monitor counts a unit silent this long as not answering
LIST_TIMEOUT = 10.0
GATEWAY_LIMIT = 16  # requests in progress per client (docs/bms-gateway.md)


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


def check_one(base, unit_id):
    """(outcome, line) for one unit: read, no answer, or failed."""
    try:
        return "read", describe(unit_reading(base, unit_id, timeout=NO_ANSWER_AFTER))
    except NoAnswer:
        return "no answer", f"{unit_id}: no answer"
    except GatewayError as exc:
        reason = f"HTTP {exc.status}" if exc.status is not None else "gateway unreachable"
        return "failed", f"{unit_id}: failed ({reason})"


def _one(base, unit_id, started):
    started[unit_id] = time.monotonic()
    try:
        return "read", describe(unit_reading(base, unit_id, timeout=30.0))
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
    # Up to GATEWAY_LIMIT units at a time; each read gives up (and closes its connection) after
    # NO_ANSWER_AFTER, so a silent unit never holds a request against the gateway's limit.
    started = {}
    pool = ThreadPoolExecutor(max_workers=GATEWAY_LIMIT)
    futures = [pool.submit(_one, args.base, u, started) for u in ids]
    results = []
    for unit_id, future in zip(ids, futures):
        while unit_id not in started:
            time.sleep(0.005)
        try:
            results.append(future.result(timeout=max(0.0, started[unit_id] + NO_ANSWER_AFTER - time.monotonic())))
        except FutureTimeout:
            results.append(("no answer", f"{unit_id}: no answer"))
    counts = {"read": 0, "no answer": 0, "failed": 0}
    for outcome, line in results:
        counts[outcome] += 1
        print(line)
    print(f"checked {len(ids)} units: {counts['read']} read, {counts['no answer']} no answer, "
          f"{counts['failed']} failed")
    sys.stdout.flush()
    os._exit(0 if counts["read"] == len(ids) else 1)


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
