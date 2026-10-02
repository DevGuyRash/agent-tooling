"""The dockops command line."""
import argparse
import os
import sys

from . import bikes, db, stations
from .errors import NotFound, UsageError


def build_parser():
    p = argparse.ArgumentParser(prog="dockops", description="Tools for Tidewater Bikes dispatch.")
    p.add_argument("--db", default=os.environ.get("DOCKOPS_DB", "dockops.db"),
                   help="the trips database (default: $DOCKOPS_DB, then ./dockops.db)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("stations", help="list stations")
    s.add_argument("--area", help="only this dispatch area")
    s.add_argument("--retired", action="store_true", help="include retired stations")
    s.set_defaults(func=stations.run)

    b = sub.add_parser("bike", help="a bike's most recent trips")
    b.add_argument("bike_id", type=int)
    b.add_argument("--last", type=int, default=10, help="how many trips (default 10)")
    b.set_defaults(func=bikes.run)
    return p


def main(argv=None, out=None, err=None):
    out = out or sys.stdout
    err = err or sys.stderr
    args = build_parser().parse_args(argv)
    try:
        conn = db.connect(args.db)
    except db.DatabaseMissing as exc:
        print(f"dockops: {exc}", file=err)
        return 1
    try:
        return args.func(conn, args, out)
    except UsageError as exc:
        print(f"dockops: {exc}", file=err)
        return 2
    except NotFound as exc:
        print(f"dockops: {exc}", file=err)
        return 1
    finally:
        conn.close()
