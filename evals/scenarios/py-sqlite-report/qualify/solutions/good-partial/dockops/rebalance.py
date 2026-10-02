"""dockops rebalance (docs/rebalance.md): SQL picks the range's rides through the time indexes; Python counts."""
from datetime import date, datetime, timedelta

from . import db
from .errors import UsageError
from .table import render


def _parse(text):
    try:
        if len(text) != 10:
            raise ValueError
        return date.fromisoformat(text)
    except ValueError:
        raise UsageError(f"bad date '{text}' (want YYYY-MM-DD)") from None


def _false_start(start, end, started_at, ended_at):
    if end is None or end != start:
        return False
    return (datetime.fromisoformat(ended_at) - datetime.fromisoformat(started_at)).total_seconds() < 60


def run(conn, args, out):
    first = _parse(args.date_from)
    last = first if args.date_to is None else _parse(args.date_to)
    if last < first:
        raise UsageError("--to is before --from")
    if args.top < 0:
        raise UsageError("--top must be 0 or more")
    if args.area is not None and not db.area_exists(conn, args.area):
        raise UsageError(f"no stations in area '{args.area}'")
    lo, hi = f"{first} 00:00:00", f"{last + timedelta(days=1)} 00:00:00"
    out_count, in_count = {}, {}
    for start, end, started_at, ended_at in conn.execute(
            "SELECT start_station, end_station, started_at, ended_at FROM trips "
            "WHERE kind = 'ride' AND started_at >= ? AND started_at < ?", (lo, hi)):
        if not _false_start(start, end, started_at, ended_at):
            out_count[start] = out_count.get(start, 0) + 1
    for start, end, started_at, ended_at in conn.execute(
            "SELECT start_station, end_station, started_at, ended_at FROM trips "
            "WHERE kind = 'ride' AND end_station IS NOT NULL AND ended_at >= ? AND ended_at < ?", (lo, hi)):
        if not _false_start(start, end, started_at, ended_at):
            in_count[end] = in_count.get(end, 0) + 1
    stations = {sid: (code, name, area) for sid, code, name, area in
                conn.execute("SELECT id, code, name, area FROM stations")}
    listed = []
    for sid in set(out_count) | set(in_count):
        code, name, area = stations[sid]
        if args.area is None or area == args.area:
            listed.append((in_count.get(sid, 0) - out_count.get(sid, 0), code, name, out_count.get(sid, 0),
                           in_count.get(sid, 0)))
    if not listed:
        print("no rides in range", file=out)
        return 0
    listed.sort()
    shown = listed if args.top == 0 else listed[:args.top]
    rows = [(code, name, o, i, "0" if net == 0 else f"{net:+d}") for net, code, name, o, i in shown]
    for line in render(("code", "station", "out", "in", "net"), rows, "llrrr"):
        print(line, file=out)
    print(f"stations: {len(listed)}, out: {sum(x[3] for x in listed)}, in: {sum(x[4] for x in listed)}", file=out)
    return 0
