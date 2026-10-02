"""dockctl command line."""

import argparse
import sys

from . import __version__
from .gateway import GatewayError, dock_status, gateway_url, list_docks
from .sweeper import read_all


def describe(status):
    """A dock's status as one line, the way `dockctl show` prints it."""
    bikes = status["bikes"]
    noun = "bike" if bikes == 1 else "bikes"
    return f"{status['id']}: {bikes} {noun}, {status['free']} free"


def cmd_list(args):
    for dock_id, name in sorted(list_docks(args.base)):
        print(f"{dock_id}  {name}")
    return 0


def cmd_show(args):
    for dock_id in args.dock:
        print(describe(dock_status(args.base, dock_id)))
    return 0


def cmd_sweep(args):
    try:
        dock_ids = sorted(dock_id for dock_id, _ in list_docks(args.base))
    except GatewayError as exc:
        print(f"dockctl: no dock list: {exc}", file=sys.stderr)
        return 2
    tally = {"ok": 0, "offline": 0, "failed": 0}
    for dock_id, (outcome, payload) in zip(dock_ids, read_all(args.base, dock_ids)):
        tally[outcome] += 1
        if outcome == "ok":
            print(describe(payload))
        elif outcome == "offline":
            print(f"{dock_id}: offline")
        else:
            print(f"{dock_id}: failed ({payload})")
    print(f"swept {len(dock_ids)} docks: {tally['ok']} ok, {tally['offline']} offline, {tally['failed']} failed")
    return 0 if tally["offline"] + tally["failed"] == 0 else 1


def build_parser():
    parser = argparse.ArgumentParser(prog="dockctl", description="Ops tools for the Riverbend Bikes dock network.")
    parser.add_argument("--gateway", metavar="URL",
                        help="dock gateway base URL (default: $DOCKCTL_GATEWAY, else http://127.0.0.1:8470)")
    parser.add_argument("--version", action="version", version=f"dockctl {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="list every dock the gateway knows")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="show docks' bikes and free slots right now")
    p.add_argument("dock", nargs="+", help="dock ID, for example D-0042")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("sweep", help="read every dock (for the uptime monitor)")
    p.set_defaults(func=cmd_sweep)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.base = gateway_url(args.gateway)
    try:
        return args.func(args)
    except GatewayError as exc:
        print(f"dockctl: {exc}", file=sys.stderr)
        return 1
