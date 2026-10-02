#!/usr/bin/env python3
"""Each boat's time on the water this season, most first, and which boats are due for service:
python3 scripts/boat_hours.py BOATLOG.csv"""
import csv
import os
import sys
from concurrent.futures import ThreadPoolExecutor

SERVICE_AFTER = 100 * 60


def minutes(hhmm):
    hours, mins = hhmm.split(":")
    return int(hours) * 60 + int(mins)


def summarize(item):
    boat, rows = item
    total = since = 0
    for row in rows:
        if row["crew"].strip() == "SERVICE":
            since = 0
        elif row["in"].strip():
            spent = minutes(row["in"]) - minutes(row["out"])
            total += spent
            since += spent
    return boat, total, since


def main(argv):
    if len(argv) != 2:
        print("usage: boat_hours.py BOATLOG.csv", file=sys.stderr)
        return 2
    by_boat = {}
    with open(argv[1], newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            by_boat.setdefault(row["boat"].strip(), []).append(row)
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        results = list(pool.map(summarize, by_boat.items()))
    for boat, total, since in sorted(results, key=lambda r: (-r[1], r[0])):
        line = f"{boat} {total // 60}:{total % 60:02d}"
        if since >= SERVICE_AFTER:
            line += " service due"
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
