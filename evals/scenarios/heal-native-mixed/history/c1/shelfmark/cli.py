"""Command-line interface for shelfmark."""
import argparse
import csv
import json
import sys

from . import __version__
from .catalog import DEFAULT_PATH, Catalog
from .isbn import is_valid, normalize


def build_parser():
    p = argparse.ArgumentParser(prog="shelfmark", description="Catalogue a home library.")
    p.add_argument("--catalog", default=str(DEFAULT_PATH), help="catalogue file (default: ~/.shelfmark.json)")
    p.add_argument("--version", action="version", version=f"shelfmark {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="add a book")
    add.add_argument("isbn")
    add.add_argument("--title", required=True)
    add.add_argument("--author", required=True)

    sub.add_parser("list", help="list books")

    exp = sub.add_parser("export", help="write the catalogue to stdout")
    exp.add_argument("--format", choices=["csv", "json"], default="csv")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    cat = Catalog(args.catalog)
    if args.command == "add":
        isbn = normalize(args.isbn)
        if not is_valid(isbn):
            print(f"shelfmark: invalid ISBN: {args.isbn}", file=sys.stderr)
            return 2
        cat.add(isbn, args.title, args.author)
        cat.save()
    elif args.command == "list":
        for b in cat.books:
            print(f"{b['isbn']}  {b['title']} - {b['author']}")
    elif args.command == "export":
        if args.format == "json":
            json.dump(cat.books, sys.stdout, indent=2, sort_keys=True)
            print()
        else:
            w = csv.writer(sys.stdout)
            w.writerow(["isbn", "title", "author"])
            for b in cat.books:
                w.writerow([b["isbn"], b["title"], b["author"]])
    return 0
