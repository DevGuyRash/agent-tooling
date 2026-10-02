"""dockops rebalance (docs/rebalance.md): two GROUP BY queries on date(), which SQLite answers by scanning trips."""
from datetime import date

from . import db
from .errors import UsageError
from .table import render

NOT_FALSE_START = """
NOT (end_station IS NOT NULL AND end_station = start_station
     AND (julianday(ended_at) - julianday(started_at)) * 86400.0 < 60)
"""


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
    if args.area is not None and not db.area_exists(conn, args.area):
        raise UsageError(f"no stations in area '{args.area}'")
    span = (first.isoformat(), last.isoformat())
    departures = dict(conn.execute(
        f"SELECT start_station, COUNT(*) FROM trips WHERE kind = 'ride' AND date(started_at) BETWEEN ? AND ? "
        f"AND {NOT_FALSE_START} GROUP BY start_station", span))
    arrivals = dict(conn.execute(
        f"SELECT end_station, COUNT(*) FROM trips WHERE kind = 'ride' AND end_station IS NOT NULL "
        f"AND date(ended_at) BETWEEN ? AND ? AND {NOT_FALSE_START} GROUP BY end_station", span))
    where = "WHERE area = ?" if args.area is not None else ""
    params = (args.area,) if args.area is not None else ()
    listed = []
    for sid, code, name in conn.execute(f"SELECT id, code, name FROM stations {where}", params):
        d, a = departures.get(sid, 0), arrivals.get(sid, 0)
        if d or a:
            listed.append((a - d, code, name, d, a))
    if not listed:
        print("no rides in range", file=out)
        return 0
    listed.sort(key=lambda x: (x[0], x[1]))
    shown = listed[:args.top] if args.top else listed
    cells = [(code, name, d, a, f"{net:+d}" if net else "0") for net, code, name, d, a in shown]
    for line in render(("code", "station", "out", "in", "net"), cells, "llrrr"):
        print(line, file=out)
    print(f"stations: {len(listed)}, out: {sum(x[3] for x in listed)}, in: {sum(x[4] for x in listed)}", file=out)
    return 0
