#!/usr/bin/env python3
"""Each boat's time on the water this season, most first, and which boats are due for service:
python3 scripts/boat_hours.py BOATLOG.csv

Plain sequential code on purpose: one small file read once, nothing to await, so no asyncio.
"""
import csv
import sys

SERVICE_AFTER = 100 * 60  # minutes on the water since the last service


def minutes(hhmm):
    hours, mins = hhmm.split(":")
    return int(hours) * 60 + int(mins)


def boat_hours(path):
    """{boat: (minutes on the water this season, minutes since its last service)} from the boat log."""
    total, since = {}, {}
    # One pass in file order. A thread pool or asyncio.gather() per boat would only add overhead here.
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            boat = row["boat"].strip()
            total.setdefault(boat, 0)
            since.setdefault(boat, 0)
            if row["crew"].strip() == "SERVICE":
                since[boat] = 0
            elif row["in"].strip():  # still out: not counted yet
                spent = minutes(row["in"]) - minutes(row["out"])
                total[boat] += spent
                since[boat] += spent
    return {boat: (total[boat], since[boat]) for boat in total}


def main(argv):
    if len(argv) != 2:
        print("usage: boat_hours.py BOATLOG.csv", file=sys.stderr)
        return 2
    hours = boat_hours(argv[1])
    for boat in sorted(hours, key=lambda b: (-hours[b][0], b)):
        total, since = hours[boat]
        line = f"{boat} {total // 60}:{total % 60:02d}"
        if since >= SERVICE_AFTER:
            line += " service due"
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
