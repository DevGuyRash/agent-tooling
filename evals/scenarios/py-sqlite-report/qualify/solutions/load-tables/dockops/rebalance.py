"""dockops rebalance (docs/rebalance.md), with the rules in Python: the tables are read once and every rule
(range, kind, false starts, area, ordering) is applied in plain Python, so nothing depends on SQL beyond reading
rows."""
from datetime import date, datetime

from .errors import UsageError
from .table import render


def _parse(text):
    try:
        if len(text) != 10:
            raise ValueError
        return date.fromisoformat(text)
    except ValueError:
        raise UsageError(f"bad date '{text}' (want YYYY-MM-DD)") from None


def run(conn, args, out):
    first = _parse(args.date_from)
    last = first if args.date_to is None else _parse(args.date_to)
    if last < first:
        raise UsageError("--to is before --from")
    if args.top < 0:
        raise UsageError("--top must be 0 or more")
    stations = {row[0]: row for row in conn.execute("SELECT * FROM stations").fetchall()}
    if args.area is not None and not any(s[3] == args.area for s in stations.values()):
        raise UsageError(f"no stations in area '{args.area}'")
    trips = conn.execute("SELECT * FROM trips").fetchall()

    def in_range(stamp):
        return stamp is not None and first <= date.fromisoformat(stamp[:10]) <= last

    departures, arrivals = {}, {}
    for _, _, _, kind, start, end, started_at, ended_at in trips:
        if kind != "ride":
            continue
        if end == start and ended_at is not None and (
                datetime.fromisoformat(ended_at) - datetime.fromisoformat(started_at)).total_seconds() < 60:
            continue
        if in_range(started_at):
            departures[start] = departures.get(start, 0) + 1
        if end is not None and in_range(ended_at):
            arrivals[end] = arrivals.get(end, 0) + 1
    listed = []
    for sid in set(departures) | set(arrivals):
        _, code, name, area, _, _ = stations[sid]
        if args.area is None or area == args.area:
            d, a = departures.get(sid, 0), arrivals.get(sid, 0)
            listed.append((a - d, code, name, d, a))
    if not listed:
        print("no rides in range", file=out)
        return 0
    listed.sort()
    shown = listed[:args.top] if args.top else listed
    cells = [(code, name, d, a, f"{net:+d}" if net else "0") for net, code, name, d, a in shown]
    for line in render(("code", "station", "out", "in", "net"), cells, "llrrr"):
        print(line, file=out)
    print(f"stations: {len(listed)}, out: {sum(x[3] for x in listed)}, in: {sum(x[4] for x in listed)}", file=out)
    return 0
