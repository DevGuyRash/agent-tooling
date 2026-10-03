"""The listings command line."""
import argparse
import sys

from .build import build
from .events import EventsError, load
from .slug import slugify


def main(argv=None):
    parser = argparse.ArgumentParser(prog="listings", description="Harbour Fringe listings site.")
    commands = parser.add_subparsers(dest="command", required=True)
    slug = commands.add_parser("slug", help="print the slug for each title")
    slug.add_argument("titles", nargs="+")
    site = commands.add_parser("build", help="write the site for an events file")
    site.add_argument("events")
    site.add_argument("outdir")
    args = parser.parse_args(argv)

    if args.command == "slug":
        for title in args.titles:
            print(slugify(title))
        return 0
    try:
        count = build(load(args.events), args.outdir)
    except EventsError as err:
        print(f"listings: {err}", file=sys.stderr)
        return 1
    except OSError as err:
        print(f"listings: {err.filename}: {err.strerror}", file=sys.stderr)
        return 1
    print(f"{count} pages written to {args.outdir}")
    return 0
