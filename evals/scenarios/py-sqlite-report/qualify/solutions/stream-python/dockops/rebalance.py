"""dockops rebalance (docs/rebalance.md): one pass over the trips table, a row at a time, the rules applied in
Python; only the counts are kept."""
from datetime import date, timedelta

from .errors import UsageError
from .table import render


def _parse(text):
    try:
        if len(text) != 10:
            raise ValueError
        return date.fromisoformat(text)
    except ValueError:
        raise UsageError(f"bad date '{text}' (want YYYY-MM-DD)") from None


def _seconds(stamp):
    d = date.fromisoformat(stamp[:10]).toordinal()
    return d * 86400 + int(stamp[11:13]) * 3600 + int(stamp[14:16]) * 60 + int(stamp[17:19])


def run(conn, args, out):
    first = _parse(args.date_from)
    last = first if args.date_to is None else _parse(args.date_to)
    if last < first:
        raise UsageError("--to is before --from")
    if args.top < 0:
        raise UsageError("--top must be 0 or more")
    stations = {sid: (code, name, area) for sid, code, name, area in
                conn.execute("SELECT id, code, name, area FROM stations")}
    if args.area is not None and args.area not in {s[2] for s in stations.values()}:
        raise UsageError(f"no stations in area '{args.area}'")
    lo, hi = f"{first} 00:00:00", f"{last + timedelta(days=1)} 00:00:00"
    departures, arrivals = {}, {}
    for kind, start, end, started_at, ended_at in conn.execute(
            "SELECT kind, start_station, end_station, started_at, ended_at FROM trips"):
        if kind != "ride":
            continue
        if end == start and ended_at is not None and _seconds(ended_at) - _seconds(started_at) < 60:
            continue
        if lo <= started_at < hi:
            departures[start] = departures.get(start, 0) + 1
        if end is not None and lo <= ended_at < hi:
            arrivals[end] = arrivals.get(end, 0) + 1
    listed = sorted((arrivals.get(i, 0) - departures.get(i, 0), stations[i][0], stations[i][1],
                     departures.get(i, 0), arrivals.get(i, 0))
                    for i in set(departures) | set(arrivals) if args.area in (None, stations[i][2]))
    if not listed:
        print("no rides in range", file=out)
        return 0
    shown = listed[:args.top] if args.top else listed
    cells = [(code, name, d, a, f"{net:+d}" if net else "0") for net, code, name, d, a in shown]
    for line in render(("code", "station", "out", "in", "net"), cells, "llrrr"):
        print(line, file=out)
    print(f"stations: {len(listed)}, out: {sum(x[3] for x in listed)}, in: {sum(x[4] for x in listed)}", file=out)
    return 0
