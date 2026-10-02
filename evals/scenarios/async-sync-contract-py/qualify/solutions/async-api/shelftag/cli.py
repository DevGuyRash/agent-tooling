"""python3 -m shelftag print ITEMS.csv [--width N] | preview NAME PRICE"""
import argparse
import asyncio
import csv
import sys

from .label import DEFAULT_WIDTH, Item, label_text
from .money import parse_price


def read_items(path):
    """Items from a CSV with the columns name,price,net_grams,origin (the last two may be empty)."""
    items = []
    with open(path, newline="", encoding="utf-8") as fh:
        for n, row in enumerate(csv.DictReader(fh), start=2):
            try:
                grams = (row.get("net_grams") or "").strip()
                items.append(Item(name=row["name"].strip(), price_rappen=parse_price(row["price"]),
                                  net_grams=int(grams) if grams else None,
                                  origin=(row.get("origin") or "").strip() or None))
            except (KeyError, ValueError) as exc:
                raise ValueError(f"{path}, line {n}: {exc}") from None
    return items


async def _render(items, width):
    return await asyncio.gather(*(label_text(item, width=width) for item in items))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="shelftag")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("print", help="every item's label")
    p.add_argument("items")
    p.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    p = sub.add_parser("preview", help="one label")
    p.add_argument("name")
    p.add_argument("price")
    args = parser.parse_args(argv)
    try:
        if args.command == "print":
            labels = asyncio.run(_render(read_items(args.items), args.width))
            if labels:
                print("\n\n".join(labels))
        else:
            print(asyncio.run(label_text(Item(args.name, parse_price(args.price)))))
    except (OSError, ValueError) as exc:  # LabelError is a ValueError
        print(f"shelftag: {exc}", file=sys.stderr)
        return 1
    return 0
