#!/usr/bin/env python3
"""Punctuality figures per route, for `ferry punctuality`.

ferry runs this with the sailings it has checked as JSON on standard input, in the logs' order:

    {"sailings": [{"route": "Inchmara–Dunvoan", "delay": 4}, {"route": "Inchmara–Dunvoan", "delay": null}, ...]}

(delay in minutes after the scheduled time, negative for an early departure, null for a cancelled sailing) and
lays out the figures this writes on standard output:

    {"routes": [{"route": "Inchmara–Dunvoan", "sailings": 42, "cancelled": 1, "on_time": 37, "median": 2.5,
                 "worst": 19, "bands": [[-5, 1], [0, 33], [5, 4], [15, 3]]}, ...]}

What each figure means, and the order of the routes, is in docs/punctuality.md.
"""
import json
import statistics
import sys

ON_TIME = 5  # a sailing at most this many minutes late is on time; early ones are too
BAND = 5     # minutes per band of the delay histogram


def figures(sailings):
    delays = {}  # route -> delays in the logs' order, None for a cancelled sailing; routes as first seen
    for s in sailings:
        delays.setdefault(s["route"], []).append(s["delay"])
    routes = []
    for route, ds in delays.items():
        ran = [d for d in ds if d is not None]
        bands = {}
        for d in ran:
            start = d // BAND * BAND
            bands[start] = bands.get(start, 0) + 1
        routes.append({
            "route": route,
            "sailings": len(ds),
            "cancelled": len(ds) - len(ran),
            "on_time": sum(1 for d in ran if d <= ON_TIME),
            "median": statistics.median(ran) if ran else None,
            "worst": max(ran) if ran else None,
            "bands": sorted(bands.items()),
        })
    routes.sort(key=share_on_time)
    return routes


def share_on_time(route):
    """The least punctual route first: by the share of the sailings that ran which were on time, a route where
    nothing ran before every other."""
    ran = route["sailings"] - route["cancelled"]
    return route["on_time"] / ran if ran else -1


def main():
    request = json.load(sys.stdin)
    json.dump({"routes": figures(request["sailings"])}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
