#!/usr/bin/env python3
"""Each boat's time on the water this season, most first, and which boats are due for service:
python3 scripts/boat_hours.py BOATLOG.csv

The log is read off the event loop and each boat is summarized as its own task."""
import asyncio
import csv
import sys

SERVICE_AFTER = 100 * 60


def minutes(hhmm):
    hours, mins = hhmm.split(":")
    return int(hours) * 60 + int(mins)


def _read(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


async def read_log(path):
    return await asyncio.to_thread(_read, path)


async def summarize(boat, rows):
    total = since = 0
    for row in rows:
        if row["crew"].strip() == "SERVICE":
            since = 0
        elif row["in"].strip():
            spent = minutes(row["in"]) - minutes(row["out"])
            total += spent
            since += spent
    return boat, total, since


async def run(path):
    rows = await read_log(path)
    by_boat = {}
    for row in rows:
        by_boat.setdefault(row["boat"].strip(), []).append(row)
    results = await asyncio.gather(*(summarize(boat, rs) for boat, rs in by_boat.items()))
    for boat, total, since in sorted(results, key=lambda r: (-r[1], r[0])):
        line = f"{boat} {total // 60}:{total % 60:02d}"
        if since >= SERVICE_AFTER:
            line += " service due"
        print(line)


def main(argv):
    if len(argv) != 2:
        print("usage: boat_hours.py BOATLOG.csv", file=sys.stderr)
        return 2
    asyncio.run(run(argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
