"""dockops rebalance (docs/rebalance.md): every trip read into Python, packed by SQLite into one string per 50,000
ids, and every rule applied here; few rows cross the cursor and memory stays low."""
from datetime import date, timedelta

from .errors import UsageError
from .table import render

CHUNK = 50_000


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
    blob = conn.execute("SELECT group_concat(id || char(9) || code || char(9) || name || char(9) || area, char(10))"
                        " FROM stations").fetchone()[0] or ""
    stations = {}
    for line in blob.split("\n"):
        if line:
            sid, code, name, area = line.split("\t")
            stations[int(sid)] = (code, name, area)
    if args.area is not None and args.area not in {s[2] for s in stations.values()}:
        raise UsageError(f"no stations in area '{args.area}'")
    lo, hi = f"{first} 00:00:00", f"{last + timedelta(days=1)} 00:00:00"
    departures, arrivals = {}, {}
    top = conn.execute("SELECT COALESCE(MAX(id), 0) FROM trips").fetchone()[0]
    for start_id in range(0, top + 1, CHUNK):
        chunk = conn.execute(
            "SELECT group_concat(kind || char(9) || start_station || char(9) || COALESCE(end_station, '') || char(9)"
            " || started_at || char(9) || COALESCE(ended_at, ''), char(10)) FROM trips WHERE id >= ? AND id < ?",
            (start_id, start_id + CHUNK)).fetchone()[0]
        if not chunk:
            continue
        for line in chunk.split("\n"):
            kind, start, end, started_at, ended_at = line.split("\t")
            if kind != "ride":
                continue
            start = int(start)
            end = int(end) if end else None
            if end == start and ended_at and _seconds(ended_at) - _seconds(started_at) < 60:
                continue
            if lo <= started_at < hi:
                departures[start] = departures.get(start, 0) + 1
            if end is not None and ended_at and lo <= ended_at < hi:
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
