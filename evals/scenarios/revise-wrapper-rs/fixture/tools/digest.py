#!/usr/bin/env python3
"""Daily digest of the cold-chain loggers: one line per unit and day.

    python3 tools/digest.py --units units.tsv [--day YYYY-MM-DD] LOG...

The exports and the units file are described in docs/format.md and the digest's columns in
docs/digest.md. The script trusts its input: froid digest checks the files before running it.
"""
import argparse
import statistics
import sys

HEADER = ("unit", "day", "n", "min", "max", "mean", "median", "out", "worst")
LEFT = 2  # unit and day line up on the left, the numbers on the right; worst comes last, unpadded


def tenths(text):
    """'-18.5' -> -185"""
    sign = -1 if text.startswith("-") else 1
    whole, _, frac = text.lstrip("-").partition(".")
    return sign * (int(whole) * 10 + int(frac))


def degrees(t):
    """-185 -> '-18.5'"""
    return f"{t / 10:.1f}"


def read_units(path):
    ranges = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            unit, low, high = line.split("\t")
            ranges[unit] = (tenths(low), tenths(high))
    return ranges


def read_logs(paths, day=None):
    """{unit: {date: [(clock, tenths), ...]}}, units in the order they first appear."""
    units = {}
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line.strip() or line.startswith("#"):
                    continue
                stamp, unit, temp = line.split("\t")
                date, clock = stamp[:10], stamp[11:16]
                if day and date != day:
                    continue
                units.setdefault(unit, {}).setdefault(date, []).append((clock, tenths(temp)))
    return units


def outside(t, low, high):
    """How far a reading is outside the range, in tenths; 0 inside it."""
    return max(low - t, t - high, 0)


def rows(units, ranges):
    for unit, dates in units.items():
        for date in sorted(dates):
            readings = dates[date]
            temps = [t for _, t in readings]
            row = [unit, date, str(len(temps)), degrees(min(temps)), degrees(max(temps)),
                   degrees(round(sum(temps) / len(temps))), degrees(round(statistics.median(temps)))]
            if unit in ranges:
                low, high = ranges[unit]
                bad = [(outside(t, low, high), clock, t) for clock, t in readings if outside(t, low, high)]
                worst = max(bad, key=lambda b: b[0], default=None)  # the first of equally bad readings
                row += [str(len(bad)), f"{degrees(worst[2])} at {worst[1]}" if worst else "-"]
            else:
                row += ["-", "-"]
            yield row


def layout(body):
    table = [HEADER, *body]
    widths = [max(len(row[i]) for row in table) for i in range(len(HEADER) - 1)]
    lines = []
    for row in table:
        cells = [cell.ljust(width) if i < LEFT else cell.rjust(width)
                 for i, (cell, width) in enumerate(zip(row, widths))]
        lines.append("  ".join([*cells, row[-1]]))
    return lines


def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Daily digest of the cold-chain loggers.")
    parser.add_argument("--units", required=True, help="the units file (docs/format.md)")
    parser.add_argument("--day", help="only this day, YYYY-MM-DD")
    parser.add_argument("logs", nargs="+", help="logger exports")
    args = parser.parse_args(argv)
    body = list(rows(read_logs(args.logs, args.day), read_units(args.units)))
    if not body:
        print(f"no readings on {args.day}" if args.day else "no readings")
        return 0
    print("\n".join(layout(body)))
    out = sum(int(row[7]) for row in body if row[7] != "-")
    print(f"\n{plural(len(body), 'unit-day')}, {plural(out, 'reading')} out of range")
    return 0


if __name__ == "__main__":
    sys.exit(main())
