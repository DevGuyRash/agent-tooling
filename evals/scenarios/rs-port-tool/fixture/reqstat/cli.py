"""Command-line entry point: reqstat [options] [FILE ...]."""

import argparse
import re
import sys

from . import __version__
from .logfmt import ParseError, parse_line, valid_timestamp
from .report import GROUPINGS, SORTS, Summary, render_csv, render_table, select

DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def timestamp_arg(text):
    """--since/--until: a full timestamp, or a date meaning midnight UTC."""
    if DATE_RE.fullmatch(text):
        text += "T00:00:00Z"
    if not valid_timestamp(text):
        raise argparse.ArgumentTypeError(f"invalid timestamp {text!r} (use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)")
    return text


def count_arg(minimum):
    def parse(text):
        try:
            value = int(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"invalid number {text!r}") from None
        if value < minimum:
            raise argparse.ArgumentTypeError(f"must be at least {minimum}")
        return value
    return parse


def build_parser():
    p = argparse.ArgumentParser(prog="reqstat", allow_abbrev=False,
                                description="Summarize logfmt access logs by route, path, status class, or method.")
    p.add_argument("files", nargs="*", metavar="FILE", help="log files to read (standard input when none, or -)")
    p.add_argument("--by", choices=GROUPINGS, default="route", help="what to group requests by (default: route)")
    p.add_argument("--since", type=timestamp_arg, help="only requests at or after this time")
    p.add_argument("--until", type=timestamp_arg, help="only requests before this time")
    p.add_argument("--min-count", type=count_arg(1), default=1, metavar="N",
                   help="hide groups with fewer than N requests (default: 1)")
    p.add_argument("--sort", choices=SORTS, default="count", help="row order (default: count)")
    p.add_argument("--top", type=count_arg(0), default=0, metavar="N", help="show only the first N rows (0: all)")
    p.add_argument("--format", choices=("table", "csv"), default="table", help="output format (default: table)")
    p.add_argument("--strict", action="store_true", help="stop at the first malformed line instead of skipping it")
    p.add_argument("--version", action="version", version=f"reqstat {__version__}")
    return p


class Abort(Exception):
    pass


def read_lines(name):
    if name == "-":
        yield from enumerate(sys.stdin, 1)
        return
    try:
        with open(name, encoding="utf-8", errors="replace") as f:
            yield from enumerate(f, 1)
    except OSError as e:
        raise Abort(f"cannot read {name}: {e.strerror}") from None


def summarize(files, args):
    summary = Summary()
    for name in files:
        label = "<stdin>" if name == "-" else name
        for lineno, raw in read_lines(name):
            line = raw.rstrip("\r\n")
            stripped = line.strip(" \t")
            if not stripped or stripped.startswith("#"):
                continue
            try:
                req = parse_line(line)
            except ParseError as e:
                if args.strict:
                    raise Abort(f"{label}:{lineno}: {e}") from None
                summary.malformed += 1
                continue
            if args.since and req.ts < args.since:
                continue
            if args.until and req.ts >= args.until:
                continue
            summary.add(req, args.by)
    return summary


def main(argv=None):
    args = build_parser().parse_args(argv)
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    try:
        summary = summarize(args.files or ["-"], args)
    except Abort as e:
        print(f"reqstat: {e}", file=sys.stderr)
        return 1
    rows = select(summary, min_count=args.min_count, order=args.sort, top=args.top)
    if args.format == "csv":
        sys.stdout.write(render_csv(rows, args.by))
    else:
        sys.stdout.write(render_table(summary, rows, args.by))
    return 0
