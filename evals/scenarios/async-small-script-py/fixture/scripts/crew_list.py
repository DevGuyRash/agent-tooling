#!/usr/bin/env python3
"""Active members by squad, for the noticeboard: python3 scripts/crew_list.py MEMBERS.csv"""
import csv
import sys


def crew_lists(path):
    squads = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["active"].strip().lower() == "yes":
                squads.setdefault(row["squad"].strip(), []).append(row["name"].strip())
    return {squad: sorted(names) for squad, names in sorted(squads.items())}


def main(argv):
    if len(argv) != 2:
        print("usage: crew_list.py MEMBERS.csv", file=sys.stderr)
        return 2
    for squad, names in crew_lists(argv[1]).items():
        print(f"{squad}: {', '.join(names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
