"""Command-line interface for pantry."""
import argparse
import sys

from . import __version__
from .scale import scale_text
from .units import convert


def build_parser():
    p = argparse.ArgumentParser(prog="pantry", description="Scale recipes and convert kitchen units.")
    p.add_argument("--version", action="version", version=f"pantry {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("scale", help="scale a recipe file")
    s.add_argument("file")
    s.add_argument("--factor", type=float, required=True)
    s.add_argument("--metric", action="store_true", help="print grams and millilitres")
    c = sub.add_parser("convert", help="convert an amount between units")
    c.add_argument("amount", type=float)
    c.add_argument("src")
    c.add_argument("dst")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "scale":
        with open(args.file) as f:
            print(scale_text(f.read(), args.factor, args.metric))
    else:
        try:
            print(f"{convert(args.amount, args.src, args.dst):.2f} {args.dst}")
        except ValueError as exc:
            print(f"pantry: {exc}", file=sys.stderr)
            return 2
    return 0
