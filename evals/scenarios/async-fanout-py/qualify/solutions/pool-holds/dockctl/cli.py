"""dockctl command line."""

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

from . import __version__
from .gateway import GatewayError, NoAnswer, dock_status, gateway_url, list_docks

GATEWAY_LIMIT = 16   # requests in progress per client (docs/gateway-api.md)
OFFLINE_AFTER = 2.0  # seconds without an answer before a dock counts as offline
LIST_TIMEOUT = 10.0
READ_TIMEOUT = 30.0  # a backstop so no read can hang forever; offline is decided at OFFLINE_AFTER


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


def sweep_one(base, dock_id, started):
    """(outcome, line) for one dock; records when its read began in `started`."""
    started[dock_id] = time.monotonic()
    try:
        return "ok", describe(dock_status(base, dock_id, timeout=READ_TIMEOUT))
    except NoAnswer:
        return "offline", f"{dock_id}: offline"
    except GatewayError as exc:
        reason = f"HTTP {exc.status}" if exc.status is not None else "gateway unreachable"
        return "failed", f"{dock_id}: failed ({reason})"


def cmd_sweep(args):
    try:
        ids = sorted(dock_id for dock_id, _ in list_docks(args.base, timeout=LIST_TIMEOUT))
    except GatewayError as exc:
        print(f"dockctl: cannot get the dock list: {exc}", file=sys.stderr)
        return 2
    # Never more than GATEWAY_LIMIT reads in progress: the pool has that many workers. A dock that has not
    # answered OFFLINE_AFTER seconds after its read began is reported offline.
    started = {}
    pool = ThreadPoolExecutor(max_workers=GATEWAY_LIMIT)
    futures = [pool.submit(sweep_one, args.base, dock_id, started) for dock_id in ids]
    results = []
    for dock_id, future in zip(ids, futures):
        while dock_id not in started:
            time.sleep(0.005)
        try:
            results.append(future.result(timeout=max(0.0, started[dock_id] + OFFLINE_AFTER - time.monotonic())))
        except FutureTimeout:
            results.append(("offline", f"{dock_id}: offline"))
    counts = {"ok": 0, "offline": 0, "failed": 0}
    for outcome, line in results:
        counts[outcome] += 1
        print(line)
    print(f"swept {len(ids)} docks: {counts['ok']} ok, {counts['offline']} offline, {counts['failed']} failed")
    sys.stdout.flush()
    os._exit(0 if counts["ok"] == len(ids) else 1)  # do not wait for the reads given up on


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

    p = sub.add_parser("sweep", help="read every dock; exit 1 if any was offline or failed, 2 without a dock list")
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
