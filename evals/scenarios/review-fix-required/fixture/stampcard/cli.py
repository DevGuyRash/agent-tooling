"""The command line (SPEC R11)."""
import argparse
import json
import sys

from .batch import run
from .directory import Directory, file_lookup
from .report import render


def main(argv=None):
    parser = argparse.ArgumentParser(prog="stampcard", description="Credit stamps from the till's events file.")
    parser.add_argument("events", help="the till's events file (JSON lines)")
    parser.add_argument("cards", help="the cards file (CSV: id,name,stamps)")
    parser.add_argument("--outbox", default="outbox.jsonl", help="where notification messages are written")
    args = parser.parse_args(argv)
    try:
        with open(args.events, encoding="utf-8") as f:
            lines = f.read().splitlines()
        open(args.cards, encoding="utf-8").close()
    except OSError as exc:
        print("stampcard: cannot read %s: %s" % (exc.filename, exc.strerror), file=sys.stderr)
        return 2

    def transport(message):
        with open(args.outbox, "a", encoding="utf-8") as f:
            f.write(json.dumps(message, sort_keys=True) + "\n")

    summary = run(lines, Directory(file_lookup(args.cards)), transport)
    sys.stdout.write(render(summary))
    return 0
