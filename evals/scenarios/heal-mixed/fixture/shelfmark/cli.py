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

    ls = sub.add_parser("list", help="list books")
    ls.add_argument("--tag", help="only books with this tag")

    exp = sub.add_parser("export", help="write the catalogue to stdout")
    exp.add_argument("--format", choices=["csv", "json"], default="csv")

    tag = sub.add_parser("tag", help="add tags to a book")
    tag.add_argument("isbn")
    tag.add_argument("tags", nargs="+")
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
        books = cat.with_tag(args.tag) if args.tag else cat.books
        for b in books:
            print(f"{b['isbn']}  {b['title']} - {b['author']}")
    elif args.command == "export":
        if args.format == "json":
            json.dump(cat.books, sys.stdout, indent=2, sort_keys=True)
            print()
        else:
            w = csv.writer(sys.stdout)
            w.writerow(["isbn", "title", "author", "tags"])
            for b in cat.books:
                w.writerow([b["isbn"], b["title"], b["author"], ";".join(b.get("tags", []))])
    elif args.command == "tag":
        try:
            cat.tag(normalize(args.isbn), args.tags)
        except KeyError:
            print(f"shelfmark: not in catalogue: {args.isbn}", file=sys.stderr)
            return 1
        cat.save()
    return 0
